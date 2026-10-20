"""
NMEA 0183 parser for GPS data.
Supports GGA and RMC sentences (and VTG for speed, optional).
"""

from dataclasses import dataclass
from typing import Optional
import re
import time


@dataclass
class Fix:
    """Parsed GPS fix with all relevant fields."""
    lat: float
    lon: float
    utc_time: str  # HHMMSS.ss format from NMEA
    speed_kmh: Optional[float] = None
    hdop: Optional[float] = None
    sats: Optional[int] = None
    valid: bool = True
    monotonic_ts: float = 0.0  # time.monotonic() when fix was parsed


def verify_checksum(sentence: str) -> bool:
    """
    Verify NMEA checksum (XOR of characters between $ and *).
    Returns True if valid, False otherwise.
    """
    if not sentence.startswith('$'):
        return False

    star_idx = sentence.find('*')
    if star_idx == -1:
        return False

    # Extract the part between $ and *
    data = sentence[1:star_idx]
    provided_checksum = sentence[star_idx + 1:star_idx + 3]

    # Calculate XOR checksum
    calc = 0
    for ch in data:
        calc ^= ord(ch)

    try:
        return f"{calc:02X}" == provided_checksum.upper()
    except ValueError:
        return False


def nmea_to_decimal(value: str, hemisphere: str) -> float:
    """
    Convert NMEA coordinate format (ddmm.mmmmm) to decimal degrees.
    Example: 4211.00031,N -> 42.183339
    Hemisphere: N/S for latitude, E/W for longitude.
    S and W are negative.
    """
    if not value or not hemisphere:
        raise ValueError("Empty coordinate value or hemisphere")

    # Find decimal point to split degrees and minutes
    try:
        # NMEA format: ddmm.mmmmm (lat) or dddmm.mmmmm (lon)
        # Degrees = first 2 or 3 digits, minutes = rest
        if hemisphere in ('N', 'S'):
            # Latitude: ddmm.mmmmm -> 2 digits degrees
            degrees = int(value[:2])
            minutes = float(value[2:])
        else:
            # Longitude: dddmm.mmmmm -> 3 digits degrees
            degrees = int(value[:3])
            minutes = float(value[3:])
    except (ValueError, IndexError):
        raise ValueError(f"Invalid coordinate format: {value}")

    decimal = degrees + minutes / 60.0

    if hemisphere in ('S', 'W'):
        decimal = -decimal

    return decimal


# Regex patterns for GGA and RMC sentences
GGA_PATTERN = re.compile(
    r'^\$(?:GN|GP|GL|BD|GA)GGA,'
    r'(\d{6}\.?\d*),'      # UTC time
    r'(\d{2}\d{2}\.\d+),([NS]),'  # Latitude, hemisphere
    r'(\d{3}\d{2}\.\d+),([EW]),'  # Longitude, hemisphere
    r'(\d),'                # Fix quality (0=invalid, 1=GPS, 2=DGPS)
    r'(\d+),'               # Number of satellites
    r'(\d+\.?\d*),'         # HDOP
)

RMC_PATTERN = re.compile(
    r'^\$(?:GN|GP|GL|BD|GA)RMC,'
    r'(\d{6}\.?\d*),'      # UTC time
    r'([AV]),'             # Status: A=active, V=void
    r'(\d{2}\d{2}\.\d+),([NS]),'  # Latitude, hemisphere
    r'(\d{3}\d{2}\.\d+),([EW]),'  # Longitude, hemisphere
    r'(\d+\.?\d*),'        # Speed over ground in knots
    r'(\d+\.?\d*),'        # Course over ground
    r'\d{6}',              # Date (ignored, we use UTC time from GGA)
)

VTG_PATTERN = re.compile(
    r'^\$(?:GN|GP|GL|BD|GA)VTG,'
    r'(\d+\.?\d*),T,'      # True track
    r'(\d+\.?\d*),M,'      # Magnetic track
    r'(\d+\.?\d*),N,'      # Speed in knots
    r'(\d+\.?\d*),K',      # Speed in km/h
)


def parse_gga(sentence: str) -> Optional[dict]:
    """Parse GGA sentence, return dict with fix data or None."""
    match = GGA_PATTERN.match(sentence)
    if not match:
        return None

    utc_time, lat_val, lat_hemi, lon_val, lon_hemi, fix_quality, sats, hdop = match.groups()

    # Check fix quality (must be > 0)
    if fix_quality not in ('1', '2'):
        return None

    try:
        lat = nmea_to_decimal(lat_val, lat_hemi)
        lon = nmea_to_decimal(lon_val, lon_hemi)

        # Validate non-zero coordinates
        if lat == 0.0 and lon == 0.0:
            return None

        return {
            'utc_time': utc_time,
            'lat': lat,
            'lon': lon,
            'hdop': float(hdop) if hdop else None,
            'sats': int(sats) if sats else None,
            'speed_kmh': None,  # Will be filled from RMC/VTG
        }
    except ValueError:
        return None


def parse_rmc(sentence: str) -> Optional[dict]:
    """Parse RMC sentence, return dict with fix data or None."""
    match = RMC_PATTERN.match(sentence)
    if not match:
        return None

    utc_time, status, lat_val, lat_hemi, lon_val, lon_hemi, speed_knots, course = match.groups()

    # Check status (must be 'A' = active)
    if status != 'A':
        return None

    try:
        lat = nmea_to_decimal(lat_val, lat_hemi)
        lon = nmea_to_decimal(lon_val, lon_hemi)

        # Validate non-zero coordinates
        if lat == 0.0 and lon == 0.0:
            return None

        speed_kmh = float(speed_knots) * 1.852 if speed_knots else None

        return {
            'utc_time': utc_time,
            'lat': lat,
            'lon': lon,
            'speed_kmh': speed_kmh,
            'hdop': None,
            'sats': None,
        }
    except ValueError:
        return None


def parse_vtg(sentence: str) -> Optional[float]:
    """Parse VTG sentence, return speed in km/h or None."""
    match = VTG_PATTERN.match(sentence)
    if not match:
        return None
    try:
        return float(match.group(4))
    except (ValueError, IndexError):
        return None


def parse_sentence(line: str) -> Optional[dict]:
    """
    Parse a single NMEA sentence line.
    Returns a dict with fix data (lat, lon, utc_time, speed_kmh, hdop, sats)
    or None if sentence is not a valid position sentence or has bad checksum.
    """
    line = line.strip()
    if not line:
        return None

    # Verify checksum first
    if not verify_checksum(line):
        return None

    # Try GGA first (preferred for fix quality and HDOP/sats)
    if 'GGA' in line:
        return parse_gga(line)

    # Try RMC
    if 'RMC' in line:
        return parse_rmc(line)

    # Try VTG (speed only)
    if 'VTG' in line:
        speed = parse_vtg(line)
        if speed is not None:
            return {'speed_kmh': speed}

    # Ignore all other sentences (GSV, GSA, TXT, etc.)
    return None


def merge_fix(primary: Optional[dict], secondary: Optional[dict]) -> Optional[dict]:
    """
    Merge two parsed fixes (e.g., GGA + RMC/VTG).
    Primary is preferred for position/quality, secondary fills in missing fields.
    """
    if not primary:
        return secondary
    if not secondary:
        return primary

    result = primary.copy()
    for key in ('speed_kmh', 'hdop', 'sats'):
        if result.get(key) is None and secondary.get(key) is not None:
            result[key] = secondary[key]
    return result


def create_fix_from_parsed(parsed: dict) -> Fix:
    """Create a Fix dataclass from parsed dict, adding monotonic timestamp."""
    return Fix(
        lat=parsed['lat'],
        lon=parsed['lon'],
        utc_time=parsed.get('utc_time', ''),
        speed_kmh=parsed.get('speed_kmh'),
        hdop=parsed.get('hdop'),
        sats=parsed.get('sats'),
        valid=True,
        monotonic_ts=time.monotonic(),
    )
