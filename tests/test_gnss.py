"""
Unit tests for gnss.py module.
"""

import pytest
import sys
import os
import time
import itertools
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.gnss import GnssReader
from sigmap.nmea import Fix


class TestGnssReader:
    def test_init_defaults(self):
        reader = GnssReader()
        assert reader.port == "/dev/ttyUSB0"
        assert reader.baud == 9600
        assert reader.fix_max_age_s == 5.0

    def test_init_custom(self):
        reader = GnssReader(port="/dev/ttyUSB1", baud=115200, fix_max_age_s=10.0)
        assert reader.port == "/dev/ttyUSB1"
        assert reader.baud == 115200
        assert reader.fix_max_age_s == 10.0

    def test_get_fix_returns_none_initially(self):
        reader = GnssReader()
        assert reader.get_fix() is None

    def test_start_stop(self):
        reader = GnssReader()
        reader.start()
        assert reader._thread is not None
        assert reader._thread.is_alive()
        reader.stop()
        time.sleep(0.1)
        assert not reader._thread.is_alive()

    @patch('sigmap.gnss.serial.Serial')
    def test_connect_called_on_start(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        reader = GnssReader()
        reader.start()
        time.sleep(0.1)
        reader.stop()
        
        mock_serial_class.assert_called_once()
        mock_serial.reset_input_buffer.assert_called_once()

    @patch('sigmap.gnss.serial.Serial')
    def test_read_loop_parses_gga(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        mock_serial.readline.side_effect = [gga_line, b"", b"", b"", b""]
        
        reader = GnssReader()
        reader.start()
        time.sleep(0.2)
        reader.stop()
        
        fix = reader.get_fix()
        assert fix is not None
        assert abs(fix.lat - 48.1173) < 0.0001
        assert abs(fix.lon - 11.516667) < 0.0001
        assert fix.hdop == 0.9
        assert fix.sats == 8

    @patch('sigmap.gnss.serial.Serial')
    @patch('sigmap.gnss.time.sleep', return_value=None)  # Speed up backoff
    def test_reconnect_on_serial_exception(self, mock_sleep, mock_serial_class):
        """Test that reader reconnects after SerialException."""
        import serial
        
        # Create mock serial objects
        mock_serial1 = MagicMock()
        mock_serial2 = MagicMock()
        
        # First connection: readline raises SerialException
        mock_serial1.readline.side_effect = serial.SerialException("device disconnected")
        # Second connection: returns valid GGA once, then empty lines
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        # Create an iterator that yields gga_line once, then empty lines forever
        mock_serial2.readline.side_effect = itertools.chain([gga_line], itertools.repeat(b""))
        
        # Return different mocks on each call to Serial()
        mock_serial_class.side_effect = [mock_serial1, mock_serial2]
        
        reader = GnssReader()
        reader.start()
        
        # Wait for reconnection: first readline raises exception,
        # then sleep (mocked), then reconnect (second Serial call)
        # Use real time.sleep to give the daemon thread time to process
        import time as real_time
        # Poll until Serial has been called twice (with timeout)
        deadline = real_time.monotonic() + 3.0
        while real_time.monotonic() < deadline and mock_serial_class.call_count < 2:
            real_time.sleep(0.05)
        reader.stop()
        
        # Should have tried to connect twice (mock_serial_class is the Serial mock)
        assert mock_serial_class.call_count == 2
        
        fix = reader.get_fix()
        assert fix is not None

    @patch('sigmap.gnss.serial.Serial')
    def test_stale_fix_returns_none(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        mock_serial.readline.side_effect = [gga_line, b"", b"", b""]
        
        reader = GnssReader(fix_max_age_s=0.1)
        reader.start()
        time.sleep(0.2)
        reader.stop()
        
        time.sleep(0.2)
        
        fix = reader.get_fix()
        assert fix is None

    @patch('sigmap.gnss.serial.Serial')
    def test_get_fix_with_custom_max_age(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        mock_serial.readline.side_effect = [gga_line, b"", b"", b""]
        
        reader = GnssReader(fix_max_age_s=5.0)
        reader.start()
        time.sleep(0.2)
        reader.stop()
        
        fix = reader.get_fix(max_age_s=10.0)
        assert fix is not None
        
        fix = reader.get_fix(max_age_s=0.001)
        assert fix is None

    @patch('sigmap.gnss.serial.Serial')
    def test_invalid_sentences_ignored(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        gsv_line = b"$GPGSV,2,1,07,07,79,048,42,02,51,062,43,26,36,256,42,27,27,138,42*71\n"
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        txt_line = b"$GPTXT,01,01,02,ANTENNA OK*35\n"
        
        mock_serial.readline.side_effect = [gsv_line, gga_line, txt_line, b"", b""]
        
        reader = GnssReader()
        reader.start()
        time.sleep(0.2)
        reader.stop()
        
        fix = reader.get_fix()
        assert fix is not None

    @patch('sigmap.gnss.serial.Serial')
    def test_garbage_bytes_handled(self, mock_serial_class):
        mock_serial = MagicMock()
        mock_serial_class.return_value = mock_serial
        
        garbage = b"\xff\xfe\x00garbage\n"
        gga_line = b"$GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*59\n"
        
        mock_serial.readline.side_effect = [garbage, gga_line, b"", b""]
        
        reader = GnssReader()
        reader.start()
        time.sleep(0.2)
        reader.stop()
        
        fix = reader.get_fix()
        assert fix is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
