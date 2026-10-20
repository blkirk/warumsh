"""
Bell notification module for sigmap service.
Emits a bell sound on successful umshctl ping results.
"""

import sys
import subprocess
from typing import Optional


def emit_bell(use_terminal: bool = True, audio_command: Optional[str] = None) -> None:
    """
    Emit a bell sound to signal a successful measurement.

    Args:
        use_terminal: Whether to emit terminal bell (ASCII \\a)
        audio_command: Optional command to play a sound file (e.g., 'paplay /path/bell.wav')
    """
    if use_terminal:
        # Emit terminal bell character (ASCII BEL)
        sys.stdout.write('\a')
        sys.stdout.flush()

    if audio_command:
        try:
            subprocess.run(
                audio_command,
                shell=True,
                capture_output=True,
                timeout=5.0,
                check=False
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass


def terminal_bell() -> None:
    """Emit a simple terminal bell."""
    sys.stdout.write('\a')
    sys.stdout.flush()
