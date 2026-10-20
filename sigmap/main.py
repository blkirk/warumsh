"""
Main service for GPS-tagged signal strength logger.
Ties together GPS reading, measurement triggering, signal measurement, and CSV logging.
"""

import argparse
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from sigmap.nmea import Fix
from sigmap.gnss import GnssReader
from sigmap.trigger import MeasurementTrigger
from sigmap.signal import measure_rssi
from sigmap.csvlog import CsvLogger
from sigmap.config import Config
from sigmap.bell import emit_bell


class SigMapService:
    """
    Main service that:
    1. Reads GPS continuously via GnssReader (daemon thread)
    2. Checks trigger conditions (distance + time gates)
    3. Runs umshctl ping when triggered
    4. Logs results to CSV
    """
    
    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._shutdown = False
        
        # Initialize components
        self.gnss = GnssReader(
            port=config.GPS_PORT,
            baud=config.GPS_BAUD,
            fix_max_age_s=config.FIX_MAX_AGE_S
        )
        self.trigger = MeasurementTrigger(
            min_dist_m=config.MIN_DISTANCE_M,
            min_interval_s=config.MIN_INTERVAL_S
        )
        self.csv_logger = CsvLogger(config.CSV_PATH)
        
        # Signal handling
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\nReceived signal {signum}, shutting down...", flush=True)
        self._shutdown = True
    
    def start(self) -> None:
        """Start all components."""
        print(f"Starting sigmap service...", flush=True)
        print(f"  GPS port: {self.config.GPS_PORT} @ {self.config.GPS_BAUD}", flush=True)
        print(f"  UMSH port: {self.config.UMSH_PORT}", flush=True)
        print(f"  Target: {self.config.UMSH_TARGET}", flush=True)
        print(f"  CSV: {self.config.CSV_PATH}", flush=True)
        print(f"  Distance threshold: {self.config.MIN_DISTANCE_M} m", flush=True)
        print(f"  Time threshold: {self.config.MIN_INTERVAL_S} s", flush=True)
        print(f"  Dry run: {self.config.DRY_RUN}", flush=True)
        print(f"  Bell on success: {self.config.BELL_ON_SUCCESS}", flush=True)
        
        self.gnss.start()
        self._running = True
        
        # Emit startup bell
        if self.config.BELL_ON_SUCCESS:
            emit_bell(
                use_terminal=True,
                audio_command=self.config.BELL_AUDIO_COMMAND
            )
    
    def stop(self) -> None:
        """Stop all components."""
        print("Stopping sigmap service...", flush=True)
        self._running = False
        self.gnss.stop()
        self.csv_logger.close()
        print("Service stopped.", flush=True)
    
    def run(self) -> None:
        """Main service loop."""
        self.start()
        
        try:
            while self._running and not self._shutdown:
                self._poll_once()
                time.sleep(0.5)  # Poll every 500ms
        finally:
            self.stop()
    
    def _poll_once(self) -> None:
        """Single iteration of the main loop."""
        now = time.monotonic()
        
        # Get latest GPS fix
        fix = self.gnss.get_fix(max_age_s=self.config.FIX_MAX_AGE_S)
        if fix is None:
            return
        
        # Check if we should measure
        if not self.trigger.should_measure(fix, now):
            return
        
        # We have a valid fix and both gates pass - attempt measurement
        print(f"Triggering measurement at {fix.lat:.6f}, {fix.lon:.6f} (time: {now:.1f})", flush=True)
        
        # Record the attempt position/time BEFORE measuring (per spec)
        attempt_fix = fix
        attempt_time = now
        
        # Perform measurement
        rssi = None
        status = "no_response"
        
        if not self.config.DRY_RUN:
            rssi = measure_rssi(
                port=self.config.UMSH_PORT,
                target=self.config.UMSH_TARGET,
                timeout=self.config.PING_TIMEOUT_S
            )
        
        if rssi is not None:
            status = "ok"
            print(f"  RSSI: {rssi} dBm", flush=True)
            # Emit bell on successful ping
            if self.config.BELL_ON_SUCCESS:
                emit_bell(
                    use_terminal=True,
                    audio_command=self.config.BELL_AUDIO_COMMAND
                )
        else:
            print(f"  No response", flush=True)
        
        # Log the result
        timestamp_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # First 4 characters of target
        target_prefix = self.config.UMSH_TARGET[:4] if self.config.UMSH_TARGET else ""
        self.csv_logger.write(
            timestamp_utc=timestamp_utc,
            lat=attempt_fix.lat,
            lon=attempt_fix.lon,
            rssi_dbm=rssi,
            status=status,
            speed_kmh=attempt_fix.speed_kmh,
            hdop=attempt_fix.hdop,
            satellites=attempt_fix.sats,
            target_prefix=target_prefix
        )
        
        # IMPORTANT: Mark attempt with position/time at START of attempt
        # This prevents hammering dead zones
        self.trigger.mark_attempt(attempt_fix, attempt_time)


def create_config_from_args(args: argparse.Namespace) -> Config:
    """Create Config object from parsed arguments."""
    return Config(
        GPS_PORT=args.gps_port,
        GPS_BAUD=args.gps_baud,
        UMSH_PORT=args.umsh_port,
        UMSH_TARGET=args.target,
        MIN_DISTANCE_M=args.min_distance,
        MIN_INTERVAL_S=args.min_interval,
        PING_TIMEOUT_S=args.ping_timeout,
        FIX_MAX_AGE_S=args.fix_max_age,
        CSV_PATH=args.csv,
        DRY_RUN=args.dry_run,
        LOG_FAILURES=args.log_failures,
        BELL_ON_SUCCESS=not args.no_bell,
        BELL_AUDIO_COMMAND=args.bell_audio
    )


def main():
    parser = argparse.ArgumentParser(
        description="GPS-tagged signal strength logger (sigmap)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # GPS settings
    parser.add_argument(
        "--gps-port", default="/dev/ttyUSB0",
        help="GPS serial port"
    )
    parser.add_argument(
        "--gps-baud", type=int, default=9600,
        help="GPS baud rate"
    )
    
    # UMSH settings
    parser.add_argument(
        "--umsh-port", default="/dev/ttyACM0",
        help="UMSH serial port (default: /dev/ttyACM0)"
    )
    parser.add_argument(
        "--target", default="33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp",
        help="Target node ID"
    )
    
    # Trigger thresholds
    parser.add_argument(
        "--min-distance", type=float, default=321.87,
        help="Minimum distance between measurements (meters)"
    )
    parser.add_argument(
        "--min-interval", type=float, default=60.0,
        help="Minimum time between measurements (seconds)"
    )
    
    # Timeouts
    parser.add_argument(
        "--ping-timeout", type=float, default=30.0,
        help="umshctl ping timeout (seconds)"
    )
    parser.add_argument(
        "--fix-max-age", type=float, default=5.0,
        help="Maximum age of GPS fix to consider valid (seconds)"
    )
    
    # Output
    parser.add_argument(
        "--csv", default="~/sigmap/signal_log.csv",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--log-failures", action="store_true", default=True,
        help="Log failed pings as rows with empty RSSI"
    )
    parser.add_argument(
        "--no-log-failures", action="store_false", dest="log_failures",
        help="Skip logging failed pings"
    )
    
    # Bell notification
    parser.add_argument(
        "--no-bell", action="store_true",
        help="Disable terminal bell on successful ping and startup"
    )
    parser.add_argument(
        "--bell-audio", default=None,
        help="Audio command to play on successful ping and startup (e.g., 'paplay /path/bell.wav')"
    )
    
    # Dry run
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run without executing umshctl ping (for testing)"
    )
    
    args = parser.parse_args()
    
    config = create_config_from_args(args)
    service = SigMapService(config)
    service.run()


if __name__ == "__main__":
    main()
