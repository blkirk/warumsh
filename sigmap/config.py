"""
Configuration module for sigmap service.
Holds all configurable parameters with defaults.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Service configuration with all tunable parameters."""
    
    # GPS settings
    GPS_PORT: str = "/dev/ttyUSB0"
    GPS_BAUD: int = 9600
    
    # UMSH settings
    UMSH_PORT: str = "/dev/ttyACM0"
    UMSH_TARGET: str = "33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp"
    
    # Trigger thresholds
    MIN_DISTANCE_M: float = 321.87  # 0.2 mile
    MIN_INTERVAL_S: float = 60.0    # 60 seconds
    
    # Timeouts
    PING_TIMEOUT_S: float = 30.0
    FIX_MAX_AGE_S: float = 5.0
    
    # Output
    CSV_PATH: str = "~/sigmap/signal_log.csv"
    LOG_FAILURES: bool = True
    
    # Bell notification on successful ping
    BELL_ON_SUCCESS: bool = True
    BELL_AUDIO_COMMAND: Optional[str] = None
    
    # Dry run mode (for testing)
    DRY_RUN: bool = False
