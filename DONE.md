# Completed Tasks Log

## 2026-10-19 - Project Initialization
- Created DONE.md for tracking completed work
- Reviewed OUTLINE.md project plan (8 work packages, 4 phases)
- No existing codebase found (empty directory except OUTLINE.md and example-ping.txt)

---

## Phase 1: Parallel Work Packages (WP1, WP3, WP4, WP5)
*Status: COMPLETED ✅*

### WP1: NMEA parsing (`sigmap/nmea.py`) ✅ COMPLETED
- [x] `verify_checksum(sentence) -> bool`
- [x] `parse_sentence(line) -> dict | None` handling GGA and RMC (and VTG for speed, optional)
- [x] `nmea_to_decimal(value: str, hemisphere: str) -> float`
- [x] `Fix` dataclass: `lat, lon, utc_time, speed_kmh, hdop, sats, valid, monotonic_ts`
- [x] Unit tests in `tests/test_nmea.py` - All 32 tests passing

### WP3: Geo and trigger logic (`sigmap/geo.py`, `sigmap/trigger.py`) ✅ COMPLETED
- [x] `haversine_m(lat1, lon1, lat2, lon2)`
- [x] `MeasurementTrigger(min_dist_m, min_interval_s)` with `should_measure(fix, now) -> bool` and `mark_attempt(fix, now)`
- [x] Tests for trigger scenarios in `tests/test_geo_trigger.py` - All 14 tests passing

### WP4: Signal strength (`sigmap/signal.py`) ✅ COMPLETED
- [x] `measure_rssi(port, target, timeout) -> int | None`
- [x] `parse_rssi(stdout: str) -> int | None` implementing the grep/cut logic in pure Python
- [x] Tests mock `subprocess.run` in `tests/test_signal.py` - All 13 tests passing

### WP5: CSV writer (`sigmap/csvlog.py`) ✅ COMPLETED
- [x] `CsvLogger(path)` with `write(row)`: creates directory and header if needed, appends, flushes, and fsyncs
- [x] Header written exactly once across restarts
- [x] Test with temp directory in `tests/test_csvlog.py` - All 11 tests passing

---

## Phase 2: WP2 (needs WP1)
*Status: COMPLETED ✅*

### WP2: GNSS reader (`sigmap/gnss.py`) ✅ COMPLETED
- [x] `GnssReader(port, baud)` daemon thread
- [x] `get_fix(max_age_s) -> Fix | None`
- [x] Reconnect logic on SerialException (5 s backoff)
- [x] Clean `stop()`
- [x] Unit tests in `tests/test_gnss.py` - All 13 tests passing (including reconnect)

---

## Phase 3: WP6 (needs WP2–WP5)
*Status: COMPLETED ✅*

### WP6: Main service (`sigmap/main.py`, `__main__.py`) ✅ COMPLETED
- [x] Main loop polling every ~0.5 s
- [x] CLI flags override config (`--csv`, `--gps-port`, `--dry-run`)
- [x] Graceful SIGINT/SIGTERM handling
- [x] End-to-end tests with simulated GPS stream in `tests/test_main_integration.py` - All tests passing
- [x] Configuration module (`sigmap/config.py`)
- [x] Package entry point (`sigmap/__main__.py`)

---

## Phase 4: WP7, WP8, integration test
*Status: COMPLETED ✅*

### WP7: Deployment (`deploy/`) ✅ COMPLETED
- [x] `sigmap.service` systemd unit
- [x] `README.md` with install/run instructions

### WP8: Google Maps import guide (inside README) ✅ COMPLETED
- [x] Steps for Google My Maps import in README.md
- [x] Optional `split_csv.py` helper in README.md

---

## Feature Additions

### Bell Notification ✅
- [x] `sigmap/bell.py` module with `emit_bell(use_terminal, audio_command)` and `terminal_bell()`
- [x] Terminal bell (ASCII `\a`) at service startup and on successful ping
- [x] Optional audio command via `--bell-audio` CLI flag
- [x] Enable/disable via `--bell`/`--no-bell` CLI flags and `BELL_ON_SUCCESS` config
- [x] Unit tests in `tests/test_bell.py` - All 6 tests passing
- [x] Integration tests in `tests/test_bell_integration.py` - All 4 tests passing

### CSV Target Prefix ✅
- [x] Added 9th CSV column `target_prefix` containing first 4 chars of UMSH_TARGET
- [x] Default target `33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp` → prefix `33Es`
- [x] Written only on new rows, does not modify existing CSV data
- [x] `CsvLogger.write()` accepts `target_prefix` parameter
- [x] Module-level `write_from_fix()` passes `target_prefix` through
- [x] `main.py` computes `UMSH_TARGET[:4]` and passes to CSV logger
- [x] Updated tests for 9-column header and backward compatibility

