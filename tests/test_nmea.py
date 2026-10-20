"""
Unit tests for nmea.py module.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.nmea import (
    verify_checksum,
    nmea_to_decimal,
    parse_gga,
    parse_rmc,
    parse_vtg,
    parse_sentence,
    merge_fix,
    create_fix_from_parsed,
    Fix,
)


class TestVerifyChecksum:
    def test_valid_gga_checksum(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59"
        assert verify_checksum(sentence) is True

    def test_valid_rmc_checksum(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        assert verify_checksum(sentence) is True

    def test_invalid_checksum(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00"
        assert verify_checksum(sentence) is False

    def test_no_checksum(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,"
        assert verify_checksum(sentence) is False

    def test_no_dollar_sign(self):
        sentence = "GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
        assert verify_checksum(sentence) is False


class TestNmeaToDecimal:
    def test_latitude_north(self):
        assert abs(nmea_to_decimal("4807.038", "N") - 48.1173) < 0.0001

    def test_latitude_south(self):
        assert abs(nmea_to_decimal("4807.038", "S") - (-48.1173)) < 0.0001

    def test_longitude_east(self):
        assert abs(nmea_to_decimal("01131.000", "E") - 11.516667) < 0.0001

    def test_longitude_west(self):
        assert abs(nmea_to_decimal("01131.000", "W") - (-11.516667)) < 0.0001

    def test_example_from_outline(self):
        assert abs(nmea_to_decimal("4211.00031", "N") - 42.183339) < 0.0001
        assert abs(nmea_to_decimal("12242.56732", "W") - (-122.709455)) < 0.0001

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            nmea_to_decimal("", "N")
        with pytest.raises(ValueError):
            nmea_to_decimal("123", "X")


class TestParseGGA:
    def test_valid_gga(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59"
        result = parse_gga(sentence)
        assert result is not None
        assert abs(result['lat'] - 48.1173) < 0.0001
        assert abs(result['lon'] - 11.516667) < 0.0001
        assert result['utc_time'] == "123519"
        assert result['hdop'] == 0.9
        assert result['sats'] == 8

    def test_gga_fix_quality_0_invalid(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,0,08,0.9,545.4,M,46.9,M,,*48"
        result = parse_gga(sentence)
        assert result is None

    def test_gga_fix_quality_2_dgps(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,2,08,0.9,545.4,M,46.9,M,,*4B"
        result = parse_gga(sentence)
        assert result is not None

    def test_gga_zero_coords(self):
        sentence = "$GNGGA,123519,0000.000,N,00000.000,E,1,08,0.9,545.4,M,46.9,M,,*42"
        result = parse_gga(sentence)
        assert result is None


class TestParseRMC:
    def test_valid_rmc(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        result = parse_rmc(sentence)
        assert result is not None
        assert abs(result['lat'] - 48.1173) < 0.0001
        assert abs(result['lon'] - 11.516667) < 0.0001
        assert result['utc_time'] == "123519"
        assert abs(result['speed_kmh'] - (22.4 * 1.852)) < 0.01

    def test_rmc_status_void(self):
        sentence = "$GPRMC,123519,V,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6B"
        result = parse_rmc(sentence)
        assert result is None

    def test_rmc_zero_coords(self):
        sentence = "$GPRMC,123519,A,0000.000,N,00000.000,E,022.4,084.4,230394,003.1,W*66"
        result = parse_rmc(sentence)
        assert result is None


class TestParseVTG:
    def test_valid_vtg(self):
        sentence = "$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*48"
        speed = parse_vtg(sentence)
        assert speed is not None
        assert abs(speed - 10.2) < 0.01


class TestParseSentence:
    def test_parse_gga_sentence(self):
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59"
        result = parse_sentence(sentence)
        assert result is not None
        assert 'lat' in result
        assert 'lon' in result

    def test_parse_rmc_sentence(self):
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
        result = parse_sentence(sentence)
        assert result is not None
        assert 'lat' in result
        assert 'lon' in result
        assert 'speed_kmh' in result

    def test_parse_vtg_sentence(self):
        sentence = "$GPVTG,054.7,T,034.4,M,005.5,N,010.2,K*48"
        result = parse_sentence(sentence)
        assert result is not None
        assert result.get('speed_kmh') == 10.2

    def test_ignore_gsv(self):
        sentence = "$GPGSV,2,1,07,07,79,048,42,02,51,062,43,26,36,256,42,27,27,138,42*71"
        result = parse_sentence(sentence)
        assert result is None

    def test_ignore_gsa(self):
        sentence = "$GPGSA,A,3,07,02,26,27,,,,,,,,,3.9,2.1,3.2*35"
        result = parse_sentence(sentence)
        assert result is None

    def test_ignore_txt(self):
        sentence = "$GPTXT,01,01,02,ANTENNA OK*35"
        result = parse_sentence(sentence)
        assert result is None

    def test_empty_line(self):
        assert parse_sentence("") is None
        assert parse_sentence("   ") is None

    def test_truncated_line(self):
        sentence = "$GNGGA,123519,4807.038,N"
        result = parse_sentence(sentence)
        assert result is None

    def test_bad_checksum_returns_none(self):
        # parse_sentence should return None for bad checksum
        sentence = "$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*00"
        result = parse_sentence(sentence)
        assert result is None


class TestMergeFix:
    def test_merge_gga_rmc(self):
        gga = {'lat': 48.1173, 'lon': 11.516667, 'utc_time': '123519', 'hdop': 0.9, 'sats': 8, 'speed_kmh': None}
        rmc = {'lat': 48.1173, 'lon': 11.516667, 'utc_time': '123519', 'speed_kmh': 41.5, 'hdop': None, 'sats': None}
        merged = merge_fix(gga, rmc)
        assert merged['speed_kmh'] == 41.5
        assert merged['hdop'] == 0.9
        assert merged['sats'] == 8

    def test_merge_primary_none(self):
        rmc = {'lat': 48.1173, 'lon': 11.516667, 'speed_kmh': 41.5}
        merged = merge_fix(None, rmc)
        assert merged == rmc

    def test_merge_secondary_none(self):
        gga = {'lat': 48.1173, 'lon': 11.516667, 'hdop': 0.9}
        merged = merge_fix(gga, None)
        assert merged == gga


class TestCreateFixFromParsed:
    def test_create_fix(self):
        parsed = {'lat': 48.1173, 'lon': 11.516667, 'utc_time': '123519', 'speed_kmh': 41.5, 'hdop': 0.9, 'sats': 8}
        fix = create_fix_from_parsed(parsed)
        assert isinstance(fix, Fix)
        assert fix.lat == 48.1173
        assert fix.lon == 11.516667
        assert fix.utc_time == '123519'
        assert fix.speed_kmh == 41.5
        assert fix.hdop == 0.9
        assert fix.sats == 8
        assert fix.valid is True
        assert fix.monotonic_ts > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
