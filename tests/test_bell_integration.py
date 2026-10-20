"""
Integration tests for bell notification in main service.
"""

import pytest
import sys
import os
import time
import tempfile
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.main import SigMapService
from sigmap.config import Config
from sigmap.nmea import Fix


class TestBellIntegration:
    """Tests for bell notification in the main service."""
    
    def create_test_config(self, **overrides) -> Config:
        defaults = {
            'GPS_PORT': '/dev/ttyUSB0',
            'GPS_BAUD': 9600,
            'UMSH_PORT': '/dev/ttyACM1',
            'UMSH_TARGET': 'test_target',
            'MIN_DISTANCE_M': 100.0,
            'MIN_INTERVAL_S': 10.0,
            'PING_TIMEOUT_S': 30.0,
            'FIX_MAX_AGE_S': 5.0,
            'CSV_PATH': '',
            'LOG_FAILURES': True,
            'DRY_RUN': False,
            'BELL_ON_SUCCESS': True,
            'BELL_AUDIO_COMMAND': None,
        }
        defaults.update(overrides)
        return Config(**defaults)
    
    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    @patch('sigmap.main.emit_bell')
    def test_bell_emitted_on_successful_ping(self, mock_emit_bell, mock_measure, mock_gnss_class):
        """Test that bell is emitted on successful ping (plus startup)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(CSV_PATH=csv_path)
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            fix2 = Fix(lat=42.185139, lon=-122.709455, utc_time="123520",
                       valid=True, monotonic_ts=1060.0)
            
            mock_gnss.get_fix.side_effect = [fix1, fix2, None]
            mock_measure.return_value = -58  # Successful ping
            
            service = SigMapService(config)
            service.start()
            
            for fix in [fix1, fix2]:
                with patch('sigmap.main.time.monotonic', return_value=fix.monotonic_ts):
                    service._poll_once()
                    time.sleep(0.01)
            
            service.stop()
            
            # Bell should be emitted 3 times: once at startup + 2 successful pings
            assert mock_emit_bell.call_count == 3
            mock_emit_bell.assert_called_with(use_terminal=True, audio_command=None)
    
    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    @patch('sigmap.main.emit_bell')
    def test_bell_not_emitted_on_failed_ping(self, mock_emit_bell, mock_measure, mock_gnss_class):
        """Test that bell is NOT emitted on failed ping (but is at startup)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(CSV_PATH=csv_path)
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            
            mock_gnss.get_fix.side_effect = [fix1, None]
            mock_measure.return_value = None  # Failed ping
            
            service = SigMapService(config)
            service.start()
            
            with patch('sigmap.main.time.monotonic', return_value=1000.0):
                service._poll_once()
                time.sleep(0.01)
            
            service.stop()
            
            # Bell should be emitted once at startup, not for failed ping
            assert mock_emit_bell.call_count == 1
    
    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    @patch('sigmap.main.emit_bell')
    def test_bell_disabled_via_config(self, mock_emit_bell, mock_measure, mock_gnss_class):
        """Test that bell is not emitted when BELL_ON_SUCCESS is False (not even at startup)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(CSV_PATH=csv_path, BELL_ON_SUCCESS=False)
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            
            mock_gnss.get_fix.side_effect = [fix1, None]
            mock_measure.return_value = -58  # Successful ping
            
            service = SigMapService(config)
            service.start()
            
            with patch('sigmap.main.time.monotonic', return_value=1000.0):
                service._poll_once()
                time.sleep(0.01)
            
            service.stop()
            
            # Bell should NOT be emitted at all when disabled
            mock_emit_bell.assert_not_called()
    
    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    @patch('sigmap.main.emit_bell')
    def test_bell_audio_command_passed(self, mock_emit_bell, mock_measure, mock_gnss_class):
        """Test that audio command is passed to emit_bell (startup + ping)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            audio_cmd = "paplay /path/to/bell.wav"
            config = self.create_test_config(CSV_PATH=csv_path, BELL_AUDIO_COMMAND=audio_cmd)
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            
            mock_gnss.get_fix.side_effect = [fix1, None]
            mock_measure.return_value = -58
            
            service = SigMapService(config)
            service.start()
            
            with patch('sigmap.main.time.monotonic', return_value=1000.0):
                service._poll_once()
                time.sleep(0.01)
            
            service.stop()
            
            # 2 calls: startup + 1 successful ping
            assert mock_emit_bell.call_count == 2
            for call in mock_emit_bell.call_args_list:
                call_kwargs = call[1]
                assert call_kwargs['audio_command'] == audio_cmd


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
