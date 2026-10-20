"""
CSV logger for signal strength measurements.
Creates directory and header if needed, appends, flushes, and fsyncs.
"""

import os
import csv
from datetime import datetime, timezone
from typing import Optional
from sigmap.nmea import Fix


CSV_HEADER = [
    'timestamp_utc',
    'latitude',
    'longitude',
    'rssi_dbm',
    'status',
    'speed_kmh',
    'hdop',
    'satellites',
    'target_prefix'
]


class CsvLogger:
    """
    CSV logger that writes signal measurement rows.
    
    Features:
    - Creates parent directory if needed
    - Writes header only once (on first write or if file is new/empty)
    - Flushes and fsyncs after each row for durability
    - Opens file in append mode to survive restarts
    """
    
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self._file = None
        self._writer = None
        self._header_written = False
        self._ensure_directory()
        self._open_file()
    
    def _ensure_directory(self) -> None:
        """Create parent directory if it doesn't exist."""
        dirname = os.path.dirname(self.path)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
    
    def _open_file(self) -> None:
        """Open file in append mode, check if header needs writing."""
        # Open in append mode with no buffering for immediate fsync
        self._file = open(self.path, 'a', newline='', buffering=1)
        self._writer = csv.writer(self._file)
        
        # Check if file is new or empty (header needs to be written)
        self._file.seek(0, os.SEEK_END)
        if self._file.tell() == 0:
            self._write_header()
    
    def _write_header(self) -> None:
        """Write CSV header row."""
        self._writer.writerow(CSV_HEADER)
        self._header_written = True
        self._file.flush()
        os.fsync(self._file.fileno())
    
    def write(self, timestamp_utc: str, lat: float, lon: float,
              rssi_dbm: Optional[int], status: str,
              speed_kmh: Optional[float] = None,
              hdop: Optional[float] = None,
              satellites: Optional[int] = None,
              target_prefix: Optional[str] = None) -> None:
        """
        Write a measurement row to CSV.

        Args:
            timestamp_utc: ISO format timestamp (e.g., 2026-10-20T04:00:15Z)
            lat: Latitude in decimal degrees (6 decimal places)
            lon: Longitude in decimal degrees (6 decimal places)
            rssi_dbm: RSSI in dBm as integer, or None
            status: 'ok' or 'no_response'
            speed_kmh: Speed in km/h (optional)
            hdop: Horizontal dilution of precision (optional)
            satellites: Number of satellites (optional)
            target_prefix: First 4 characters of target node ID (optional)
        """
        if self._file is None or self._file.closed:
            self._open_file()

        # Format coordinates to 6 decimal places
        lat_str = f"{lat:.6f}" if lat is not None else ""
        lon_str = f"{lon:.6f}" if lon is not None else ""
        
        # Format target prefix (first 4 chars if provided)
        target_str = target_prefix if target_prefix is not None else ""

        # Format optional fields
        rssi_str = str(rssi_dbm) if rssi_dbm is not None else ""
        speed_str = f"{speed_kmh:.2f}" if speed_kmh is not None else ""
        hdop_str = f"{hdop:.1f}" if hdop is not None else ""
        sats_str = str(satellites) if satellites is not None else ""

        row = [
            timestamp_utc,
            lat_str,
            lon_str,
            rssi_str,
            status,
            speed_str,
            hdop_str,
            sats_str,
            target_str
        ]

        self._writer.writerow(row)
        self._file.flush()
        os.fsync(self._file.fileno())
    
    def close(self) -> None:
        """Close the CSV file."""
        if self._file and not self._file.closed:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._file = None
            self._writer = None
    
    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - close file."""
        self.close()
        return False


def create_timestamp_utc() -> str:
    """Generate current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_from_fix(logger: CsvLogger, fix: Fix, rssi_dbm: Optional[int], status: str,
                   target_prefix: Optional[str] = None) -> None:
    """
    Convenience function to write a row from a Fix object.
    """
    timestamp_utc = create_timestamp_utc()
    logger.write(
        timestamp_utc=timestamp_utc,
        lat=fix.lat,
        lon=fix.lon,
        rssi_dbm=rssi_dbm,
        status=status,
        speed_kmh=fix.speed_kmh,
        hdop=fix.hdop,
        satellites=fix.sats,
        target_prefix=target_prefix
    )