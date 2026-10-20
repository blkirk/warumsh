# Project Plan: GPS-Tagged Signal Strength Logger

## 1. Goal

A long-running Python service on an Ubuntu laptop that:

1. Continuously reads NMEA from `/dev/ttyUSB0` (9600 baud) to track current position.
2. Triggers a signal-strength measurement via `umshctl` only when **both** conditions hold:
   - the device has moved **at least 0.2 mile (321.87 m)** since the last measurement attempt, and
   - **at least 60 seconds** have elapsed since the last attempt.
3. Appends `timestamp, lat, lon, rssi` to a CSV file suitable for import into Google Maps (My Maps).

## 2. Key design decisions (all agents must follow)

| Topic | Decision |
|---|---|
| Language | Python 3.10+, standard library plus `pyserial` only |
| Layout | Package `sigmap/` with the modules in section 4, plus `tests/` |
| Coordinates | Decimal degrees, WGS84. `ddmm.mmmmm` → `dd + mm/60`; `S` and `W` are negative. Example: `4211.00031,N` → `42.183339`, `12242.56732,W` → `-122.709455` |
| Position source | Prefer `$GNGGA`/`$GPGGA` (fix quality > 0, i.e. `1` or `2`), cross-check with `$GNRMC`/`$GPRMC` (status `A`). Ignore all other sentences. Accept any talker ID prefix (`GN`, `GP`, `GL`, `BD`) |
| Validity | Verify the NMEA checksum (XOR of the characters between `$` and `*`) and discard sentences that fail. Discard positions with no fix, empty fields, or lat/lon of exactly 0,0 |
| Distance | Haversine, Earth radius 6,371,000 m. Threshold `MIN_DISTANCE_M = 321.87` |
| Time gate | `MIN_INTERVAL_S = 60`, measured with `time.monotonic()` from the **start of the previous attempt** |
| Trigger logic | `if now - last_attempt_time >= 60 and haversine(current, last_attempt_pos) >= 321.87: measure`. The very first valid fix triggers an immediate measurement |
| Anchor point | After every attempt, successful or not, set `last_attempt_pos` and `last_attempt_time` to the position and time **at the start of the attempt**. This prevents hammering a dead zone |
| Command | Run `umshctl -p /dev/ttyACM1 ping 33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp` via `subprocess.run` (list args, **no shell**) with a timeout (default 30 s). Replicate `grep "seq 1:" | cut -d, -f3` in Python: find the first line containing `seq 1:`, split on `,`, take field index 2, regex `(-?\d+)\s*dBm` → integer |
| Concurrency | GPS reader runs in its own thread and continuously updates a thread-safe "latest fix" object. The ping runs in the main loop, so GPS reading is never blocked. Use the position captured at the **start** of the ping as the recorded location |
| Failed ping | Command error, timeout, or no `seq 1:` line → still write a row with an empty `rssi_dbm` and `status=no_response`. This is useful for mapping dead zones. Controlled by config flag `LOG_FAILURES = True` |
| Stale GPS | If the last valid fix is older than 5 s, treat the position as unavailable and do not trigger |
| Robustness | The service must never crash on bad input. Serial disconnects trigger reopen with a 5 s backoff. All errors are logged to stderr/journal |
| CSV | Append mode, header written only if the file is new or empty. `flush()` and `os.fsync()` after each row. Default path `~/sigmap/signal_log.csv` |

### CSV schema

```
timestamp_utc,latitude,longitude,rssi_dbm,status,speed_kmh,hdop,satellites
2026-10-20T04:00:15Z,42.183339,-122.709455,-56,ok,0.00,1.0,11
```

- `latitude` and `longitude` use 6 decimal places and are plain decimal columns, which My Maps recognizes as the location columns on import.
- `rssi_dbm` is an integer with no unit.
- `status` is `ok` or `no_response`.
- `speed_kmh` comes from RMC/VTG, `hdop` and `satellites` from GGA. They are informational and may be empty.

## 3. Configuration

A `config.py` (or a TOML file plus defaults) holds:

- `GPS_PORT="/dev/ttyUSB0"`, `GPS_BAUD=9600`
- `UMSH_PORT="/dev/ttyACM1"`, `UMSH_TARGET="33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp"`
- `MIN_DISTANCE_M=321.87`, `MIN_INTERVAL_S=60`
- `PING_TIMEOUT_S=30`, `FIX_MAX_AGE_S=5`
- `CSV_PATH`, `LOG_FAILURES`

## 4. Work packages

### WP1: NMEA parsing (`sigmap/nmea.py`)
**Deliverables**
- `verify_checksum(sentence) -> bool`
- `parse_sentence(line) -> dict | None` handling GGA and RMC (and VTG for speed, optional)
- `nmea_to_decimal(value: str, hemisphere: str) -> float`
- A `Fix` dataclass: `lat, lon, utc_time, speed_kmh, hdop, sats, valid, monotonic_ts`

**Acceptance**
- Correctly parses the sample sentences from the task (GGA → 42.183339, -122.709455, 11 sats, HDOP 1.0).
- Returns `None` for non-position sentences, bad checksums, truncated lines, and empty fields.
- Unit tests in `tests/test_nmea.py` cover every sample line given, including the `$GPTXT` and `$GPGSV` lines, which must be ignored without error.

### WP2: GNSS reader (`sigmap/gnss.py`)
**Depends on:** WP1
**Deliverables**
- `GnssReader(port, baud)` runs a daemon thread that reads lines, parses them, and stores the latest valid fix behind a lock.
- `get_fix(max_age_s) -> Fix | None`
- Reconnect logic on `SerialException`/missing device (5 s backoff).
- Decode with `errors="ignore"` and tolerate garbage bytes.
- Clean `stop()`.

**Acceptance**
- Works against a fake serial source (injected stream) in tests.
- Returns `None` when the fix is stale or invalid.
- Survives the port being unplugged and replugged (manual test notes).

### WP3: Geo and trigger logic (`sigmap/geo.py`, `sigmap/trigger.py`)
**Deliverables**
- `haversine_m(lat1, lon1, lat2, lon2)`
- `MeasurementTrigger(min_dist_m, min_interval_s)` with `should_measure(fix, now) -> bool` and `mark_attempt(fix, now)`. The clock is injectable for testing.

**Acceptance**
- Tests: first fix triggers; moving 400 m in 30 s does **not** trigger; standing still for 5 min does **not** trigger; moving 400 m after 61 s **does** trigger; 300 m after 120 s does not trigger.
- Sanity test: 0.2 mi ≈ 321.87 m via haversine against a known coordinate pair.

### WP4: Signal strength (`sigmap/signal.py`)
**Deliverables**
- `measure_rssi(port, target, timeout) -> int | None`
- `parse_rssi(stdout: str) -> int | None` implementing the grep/cut logic in pure Python.

**Acceptance**
- `parse_rssi` handles: normal output with a `seq 1:` line, `" -56 dBm"` → `-56`, no `seq 1:` line → `None`, missing `dBm`, multiple lines, and positive values.
- `subprocess.TimeoutExpired`, `FileNotFoundError`, and non-zero exit codes are caught and return `None`.
- Tests mock `subprocess.run`. Ask the user for a sample of full `umshctl ping` output to create a realistic fixture. Until then, build a fixture based on the documented format and flag it as an assumption.

### WP5: CSV writer (`sigmap/csvlog.py`)
**Deliverables**
- `CsvLogger(path)` with `write(row)`: creates the directory and header if needed, appends, flushes, and fsyncs.

**Acceptance**
- Header is written exactly once across restarts.
- Output opens cleanly in a spreadsheet and matches the schema above.
- Test with a temp directory.

### WP6: Main service (`sigmap/main.py`, `__main__.py`)
**Depends on:** WP2–WP5
**Deliverables**
- Main loop, polling every ~0.5 s:
  1. `fix = gnss.get_fix()`
  2. If there is no fix, continue.
  3. If `trigger.should_measure(fix)`: call `trigger.mark_attempt(fix)` **before** the ping, run `measure_rssi`, then write the CSV row using the pre-ping fix.
- Structured logging to stderr (INFO for each recorded row, WARNING for failures).
- Graceful SIGINT/SIGTERM handling.
- CLI flags override config (`--csv`, `--gps-port`, `--dry-run`, which skips the real `umshctl` call and logs what would run).

**Acceptance**
- End-to-end test using a simulated GPS stream and a mocked ping, producing the expected CSV rows.
- Runs for 10+ minutes in a manual soak test without memory growth or crashes.

### WP7: Deployment (`deploy/`)
**Deliverables**
- A `sigmap.service` systemd unit: `Restart=always`, `RestartSec=5`, runs as the user, with the user in the `dialout` group.
- `README.md`: install steps (`pip install pyserial`), run instructions, config reference, the CSV schema, and how to import into Google Maps.

**Acceptance:** a fresh Ubuntu laptop can go from clone to running service by following the README.

### WP8: Google Maps import guide (inside README)
- Steps for **Google My Maps** → Import CSV → choose `latitude`/`longitude` as position columns → choose a title column.
- Optional: add a `label` column to the CSV or recommend `rssi_dbm`, and describe styling by data column (color-code by signal strength ranges, e.g. > -70 good, -70 to -90 fair, < -90 poor; thresholds are a suggestion).
- Note that My Maps imports are limited to 2,000 rows per layer (verify the current limit), and suggest splitting by date if exceeded. Optionally provide a small `split_csv.py` helper.

## 5. Execution order and parallelism

```
Phase 1 (parallel):  WP1, WP3, WP4, WP5
Phase 2:             WP2 (needs WP1)
Phase 3:             WP6 (needs WP2–WP5)
Phase 4 (parallel):  WP7, WP8, integration test and review
```

## 6. Interface contract (so parallel agents stay compatible)

```python
@dataclass
class Fix:
    lat: float; lon: float
    utc_time: str | None
    speed_kmh: float | None
    hdop: float | None
    sats: int | None
    monotonic_ts: float   # time.monotonic() when parsed

def get_fix(max_age_s: float) -> Fix | None
def should_measure(fix: Fix, now: float) -> bool
def mark_attempt(fix: Fix, now: float) -> None
def measure_rssi(port: str, target: str, timeout: float) -> int | None
def write(row: dict) -> None
```

## 7. Definition of done

- All unit tests pass (`pytest`).
- The 4 trigger scenarios and the sample NMEA data pass.
- The service has run unattended for 30+ minutes in a real or simulated drive without crashing.
- No shell invocation anywhere, and no hard-coded secrets beyond the configurable target ID.
- The README is complete.
