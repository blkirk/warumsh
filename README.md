# sigmap: GPS-Tagged Signal Strength Logger

A Python service that logs GPS-tagged signal strength measurements from mesh network nodes.

## Overview

The sigmap service continuously reads GPS data from a serial port and triggers signal strength measurements via `umshctl ping` when both distance and time thresholds are met:
- Minimum distance: 321.87 meters (0.2 mile)  
- Minimum time: 60 seconds

Results are logged to a CSV file suitable for import into Google Maps My Maps.

## Features

- Reads NMEA sentences from GPS (`$GNGGA`, `$GPRMC`, etc.)
- Verifies NMEA checksums
- Merges GGA (position/quality) and RMC (speed/validity) sentences
- Implements distance/time gating to avoid redundant measurements
- Logs failed pings (optional)
- CSV output with header: `timestamp_utc,latitude,longitude,rssi_dbm,status,speed_kmh,hdop,satellites`
- Graceful shutdown on SIGINT/SIGTERM
- Dry-run mode for testing

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install pyserial
   ```
3. Install `umshctl` (from the UMSH.dev project) and ensure it's in your PATH

## Usage

Run the service:
```bash
python -m sigmap [options]
```

### Options

```
--gps-port PORT       GPS serial port (default: /dev/ttyUSB0)
--gps-baud BAUD       GPS baud rate (default: 9600)
--umsh-port PORT      UMSH serial port (default: /dev/ttyACM0)
--target ID           Target node ID (default: 33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp)
--min-distance METERS Minimum distance between measurements (default: 321.87)
--min-interval SECONDS Minimum time between measurements (default: 60.0)
--ping-timeout SECONDS umshctl ping timeout (default: 30.0)
--fix-max-age SECONDS Max GPS fix age to consider valid (default: 5.0)
--csv PATH            Output CSV file path (default: ~/sigmap/signal_log.csv)
--log-failures        Log failed pings as rows with empty RSSI (default: True)
--no-log-failures     Skip logging failed pings
--dry-run             Run without executing umshctl ping (for testing)
```

## CSV Output Format

The CSV file contains one row per measurement attempt:

| Column | Description |
|--------|-------------|
| timestamp_utc | UTC timestamp of measurement (ISO 8601) |
| latitude | Latitude in decimal degrees (WGS84) |
| longitude | Longitude in decimal degrees (WGS84) |
| rssi_dbm | Signal strength in dBm, or empty if failed |
| status | "ok" for successful ping, "no_response" for failed |
| speed_kmh | Current speed in km/h from GPS, or empty |
| hdop | Horizontal dilution of precision from GPS, or empty |
| satellites | Number of satellites in fix, or empty |

Example row:
```
2026-10-20T14:30:15Z,42.183326,-122.709488,-58,ok,0.0,1.2,8
```

## Importing to Google Maps My Maps

1. Open [Google My Maps](https://www.google.com/maps/d/u/0/)
2. Create a new map
3. Click "Import" and select your CSV file
4. Choose `latitude` and `longitude` columns for position placement
5. The other columns will appear as data in point markers

## Systemd Service

For automatic startup on Linux, copy `deploy/sigmap.service` to `/etc/systemd/system/`:
```bash
sudo cp deploy/sigmap.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sigmap
sudo systemctl start sigmap
```

Check status with:
```bash
sudo journalctl -u sigmap -f
```

## Development

### Running Tests
```bash
source venv/bin/activate
pytest tests/ -v
```

### Project Structure
```
sigmap/
├── __init__.py      # Package exports
├── __main__.py      # Entry point: python -m sigmap
├── config.py        # Configuration dataclass
├── csvlog.py        # CSV logger with fsync
├── geo.py           # Haversine distance calculation
├── gnss.py          # GPS reader daemon thread
├── main.py          # Main service loop
├── nmea.py          # NMEA sentence parser
├── signal.py        # RSSI parsing and measurement
└── trigger.py       # Distance/time gating logic
tests/
├── test_csvlog.py   # CSV logger tests
├── test_geo_trigger.py # Haversine and trigger tests
├── test_gnss.py     # GPS reader tests
├── test_main_integration.py # End-to-end tests
├── test_nmea.py     # NMEA parser tests
└── test_signal.py   # Signal strength tests
```

## License

MIT

## Contact

Ben Kirkpatrick &lt;blkirk@gmail.com&gt;
