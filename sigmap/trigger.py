"""
Measurement trigger logic.
Decides when to take a signal strength measurement based on distance and time gates.
"""

import time
from typing import Optional
from sigmap.nmea import Fix


class MeasurementTrigger:
    """
    Determines when to trigger a measurement based on:
    - Minimum distance moved since last attempt (default 321.87 m = 0.2 mile)
    - Minimum time elapsed since last attempt (default 60 s)
    
    The first valid fix always triggers an immediate measurement.
    After every attempt (successful or not), the anchor point is updated to
    the position and time at the START of the attempt.
    """
    
    def __init__(self, min_dist_m: float = 321.87, min_interval_s: float = 60.0):
        self.min_dist_m = min_dist_m
        self.min_interval_s = min_interval_s
        self.last_attempt_pos: Optional[tuple[float, float]] = None  # (lat, lon)
        self.last_attempt_time: Optional[float] = None  # time.monotonic()
        self.first_fix = True
    
    def should_measure(self, fix: Fix, now: Optional[float] = None) -> bool:
        """
        Returns True if a measurement should be attempted.
        
        Args:
            fix: Current GPS fix
            now: Optional monotonic time (defaults to time.monotonic())
            
        Returns:
            True if both distance and time thresholds are met, or if this is the first fix.
        """
        if not fix.valid:
            return False
        
        if now is None:
            now = time.monotonic()
        
        # First valid fix always triggers
        if self.first_fix:
            return True
        
        # Check if we have a previous attempt position
        if self.last_attempt_pos is None or self.last_attempt_time is None:
            return True
        
        # Check time gate
        time_elapsed = now - self.last_attempt_time
        if time_elapsed < self.min_interval_s:
            return False
        
        # Check distance gate
        from sigmap.geo import haversine_m
        distance = haversine_m(
            fix.lat, fix.lon,
            self.last_attempt_pos[0], self.last_attempt_pos[1]
        )
        if distance < self.min_dist_m:
            return False
        
        return True
    
    def mark_attempt(self, fix: Fix, now: Optional[float] = None) -> None:
        """
        Update the anchor point to the current fix position and time.
        Called after EVERY attempt (successful or failed).
        
        Args:
            fix: The GPS fix at the start of the attempt
            now: Optional monotonic time (defaults to time.monotonic())
        """
        if now is None:
            now = time.monotonic()
        
        self.last_attempt_pos = (fix.lat, fix.lon)
        self.last_attempt_time = now
        self.first_fix = False
    
    def reset(self) -> None:
        """Reset trigger state (useful for testing)."""
        self.last_attempt_pos = None
        self.last_attempt_time = None
        self.first_fix = True
