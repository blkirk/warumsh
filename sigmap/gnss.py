"""
GNSS reader thread for continuous GPS data acquisition.
Runs as a daemon thread, reads NMEA from serial port, parses and stores latest valid fix.
"""

import threading
import time
import serial
from typing import Optional
from sigmap.nmea import Fix, parse_sentence, merge_fix, create_fix_from_parsed


class GnssReader:
    """
    Daemon thread that continuously reads NMEA sentences from a serial port,
    parses them, and maintains the latest valid GPS fix.
    
    Features:
    - Automatic reconnection with 5s backoff on serial errors
    - Thread-safe access to latest fix
    - Configurable max age for fix validity
    - Clean shutdown
    """
    
    def __init__(self, port: str = "/dev/ttyUSB0", baud: int = 9600, fix_max_age_s: float = 5.0):
        self.port = port
        self.baud = baud
        self.fix_max_age_s = fix_max_age_s
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_fix: Optional[Fix] = None
        self._last_gga: Optional[dict] = None
        self._last_rmc: Optional[dict] = None
        self._serial: Optional[serial.Serial] = None
    
    def start(self) -> None:
        """Start the reader thread."""
        if self._thread and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        """Stop the reader thread and close serial port."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._close_serial()
    
    def _close_serial(self) -> None:
        """Close serial connection if open."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
    
    def get_fix(self, max_age_s: Optional[float] = None) -> Optional[Fix]:
        """
        Get the latest valid GPS fix.
        
        Args:
            max_age_s: Maximum age of fix in seconds (uses instance default if None)
            
        Returns:
            Latest Fix if valid and not stale, None otherwise
        """
        if max_age_s is None:
            max_age_s = self.fix_max_age_s
        
        with self._lock:
            fix = self._latest_fix
        
        if fix is None:
            return None
        
        # Check if fix is stale
        now = time.monotonic()
        if now - fix.monotonic_ts > max_age_s:
            return None
        
        return fix
    
    def _run(self) -> None:
        """Main reader loop - runs in daemon thread."""
        backoff = 5.0
        
        while not self._stop_event.is_set():
            try:
                self._connect()
                self._read_loop()
            except serial.SerialException as e:
                print(f"GPS serial error: {e}", flush=True)
                self._close_serial()
                if not self._stop_event.is_set():
                    time.sleep(backoff)
            except Exception as e:
                print(f"GPS reader unexpected error: {e}", flush=True)
                self._close_serial()
                if not self._stop_event.is_set():
                    time.sleep(backoff)
    
    def _connect(self) -> None:
        """Open serial connection."""
        self._close_serial()
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=1.0,  # 1s read timeout
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
        # Clear any buffered data
        self._serial.reset_input_buffer()
    
    def _read_loop(self) -> None:
        """Read and parse NMEA sentences continuously."""
        while not self._stop_event.is_set():
            try:
                line_bytes = self._serial.readline()
                if not line_bytes:
                    continue
                
                # Decode with error handling for garbage bytes
                try:
                    line = line_bytes.decode('ascii', errors='ignore').strip()
                except Exception:
                    continue
                
                if not line:
                    continue
                
                # Parse sentence
                parsed = parse_sentence(line)
                if parsed is None:
                    continue
                
                # Merge GGA and RMC/VTG data
                if 'GGA' in line:
                    self._last_gga = parsed
                elif 'RMC' in line or 'VTG' in line:
                    self._last_rmc = parsed
                
                # Merge and create fix if we have position data
                merged = merge_fix(self._last_gga, self._last_rmc)
                if merged and 'lat' in merged and 'lon' in merged:
                    fix = create_fix_from_parsed(merged)
                    with self._lock:
                        self._latest_fix = fix
                        
            except serial.SerialException:
                # Connection lost, break to reconnect
                raise
            except Exception as e:
                # Log but continue reading
                print(f"GPS parse error: {e}", flush=True)
                continue
