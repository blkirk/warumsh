"""
Signal strength measurement module.
Runs umshctl ping command and parses RSSI from output.
"""

import subprocess
import re
import shutil
import os
from typing import Optional


def find_umshctl():
    """Resolve the umshctl binary path from PATH, with cargo bin fallback."""
    found = shutil.which("umshctl")
    if found:
        return found
    cargo_bin = os.path.expanduser("~/.cargo/bin/umshctl")
    return cargo_bin


def parse_rssi(stdout: str) -> Optional[int]:
    """
    Parse RSSI from umshctl ping output.

    Expected format:
    seq 1: reply in 0.42 s, 1 hop, -58 dBm, snr 8.8 dBm

    Returns RSSI as integer (e.g., -58) or None if not found.
    """
    if not stdout:
        return None

    # Find the first line containing "seq 1:"
    for line in stdout.splitlines():
        if 'seq 1:' in line:
            # Split on comma and take field index 2 (0-based)
            parts = line.split(',')
            if len(parts) >= 3:
                rssi_field = parts[2].strip()  # "-58 dBm"
                # Extract integer with regex
                match = re.search(r'(-?\d+)\s*dBm', rssi_field)
                if match:
                    return int(match.group(1))
            break

    return None


def measure_rssi(port: str, target: str, timeout: float = 30.0) -> Optional[int]:
    """
    Run umshctl ping command and return RSSI in dBm.

    Args:
        port: Serial port for umsh device (e.g., /dev/ttyACM1)
        target: Target node ID
        timeout: Command timeout in seconds

    Returns:
        RSSI in dBm as integer, or None if command failed/timed out/no response
    """
    umshctl = find_umshctl()
    cmd = [umshctl, '-p', port, 'ping', '--flood', '--flood-hops', '1', target]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False  # Don't raise on non-zero exit
        )

        # Check for command errors
        if result.returncode != 0:
            return None

        return parse_rssi(result.stdout)

    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        # umshctl not found
        return None
    except Exception:
        # Any other error (permission, etc.)
        return None
