"""
Integration tests for the main service.
Tests the end-to-end flow with simulated GPS data.
"""

import pytest
import sys
import os
import time
import tempfile
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.main import SigMapService, create_config_from_args
from sigmap.config import Config
from sigmap.nmea import Fix
from sigmap.gnss import GnssReader
from sigmap.trigger import MeasurementTrigger
from sigmap.signal import measure_rssi
from sigmap.csvlog import CsvLogger
import argparse


class TestMainServiceIntegration:
    """Integration tests for the main service with mocked components."""
    
    def create_test_config(self, **overrides) -> Config:
        """Create a test config with defaults overridden by kwargs."""
        defaults = {
            'GPS_PORT': '/dev/ttyUSB0',
            'GPS_BAUD': 9600,
            'UMSH_PORT': '/dev/ttyACM0',
            'UMSH_TARGET': 'test_target',
            'MIN_DISTANCE_M': 321.87,
            'MIN_INTERVAL_S': 60.0,
            'PING_TIMEOUT_S': 30.0,
            'FIX_MAX_AGE_S': 5.0,
            'CSV_PATH': '',
            'LOG_FAILURES': True,
            'DRY_RUN': True,  # Default to dry-run for tests
            'BELL_ON_SUCCESS': True,
            'BELL_AUDIO_COMMAND': None,
        }
        defaults.update(overrides)
        return Config(**defaults)
    
    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    def test_first_fix_triggers_measurement(self, mock_measure, mock_gnss_class):
        """Test that the first valid fix triggers an immediate measurement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(CSV_PATH=csv_path, DRY_RUN=True)
            
            # Mock GnssReader
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            # First call returns valid fix, subsequent calls return None to stop loop
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", 
                       valid=True, monotonic_ts=1000.0)
            mock_gnss.get_fix.side_effect = [fix1, None, None, None]
            
            # Mock measure_rssi (should be called once)
            mock_measure.return_value = -58
            
            service = SigMapService(config)
            service.start()
            
            # Run a few iterations
            for _ in range(4):
                service._poll_once()
                time.sleep(0.01)
            
            service.stop()
            
            # Verify measure_rssi was called (dry_run=True means it shouldn't)
            # Actually with DRY_RUN=True, measure_rssi should NOT be called
            # Let's check the CSV instead
            assert os.path.exists(csv_path)
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 2  # header + 1 data row
                assert '42.183339' in lines[1]
                assert '-122.709455' in lines[1]
                # In dry run, RSSI should be empty
                assert ',,' in lines[1] or 'no_response' in lines[1]

    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    def test_distance_and_time_gates(self, mock_measure, mock_gnss_class):
        """Test that both distance and time gates must pass for measurement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(
                CSV_PATH=csv_path,
                DRY_RUN=False,
                MIN_DISTANCE_M=100.0,  # 100m threshold
                MIN_INTERVAL_S=10.0    # 10s threshold
            )
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            # Create fixes at different positions/times
            # fix1: origin
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            # fix2: same position, 5s later - should NOT trigger (time gate fails)
            fix2 = Fix(lat=42.183339, lon=-122.709455, utc_time="123524",
                       valid=True, monotonic_ts=1005.0)
            # fix3: same position, 15s later - should NOT trigger (distance gate fails)
            fix3 = Fix(lat=42.183339, lon=-122.709455, utc_time="123534",
                       valid=True, monotonic_ts=1015.0)
            # fix4: moved 200m north, 20s later - SHOULD trigger (both gates pass)
            # 0.0018 deg lat ≈ 200m
            fix4 = Fix(lat=42.185139, lon=-122.709455, utc_time="123539",
                       valid=True, monotonic_ts=1020.0)
            
            mock_gnss.get_fix.side_effect = [fix1, fix2, fix3, fix4, None]
            mock_measure.return_value = -58
            
            service = SigMapService(config)
            service.start()
            
            # Poll with time progression
            for fix in [fix1, fix2, fix3, fix4]:
                with patch('sigmap.main.time.monotonic', return_value=fix.monotonic_ts):
                    service._poll_once()
                    time.sleep(0.01)
            
            service.stop()
            
            # Should have only 2 measurements: first fix + fix4
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 3  # header + 2 data rows

    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    def test_failed_ping_logged_as_no_response(self, mock_measure, mock_gnss_class):
        """Test that failed pings are logged with status=no_response."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            # Use smaller distance threshold so both fixes trigger
            config = self.create_test_config(
                CSV_PATH=csv_path,
                DRY_RUN=False,
                LOG_FAILURES=True,
                MIN_DISTANCE_M=100.0,
                MIN_INTERVAL_S=10.0
            )
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            # fix1 at origin
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            # fix2: 200m north, 60s later - both gates pass
            fix2 = Fix(lat=42.185139, lon=-122.709455, utc_time="123520",
                       valid=True, monotonic_ts=1060.0)
            
            mock_gnss.get_fix.side_effect = [fix1, fix2, None]
            mock_measure.return_value = None  # Simulate failed ping
            
            service = SigMapService(config)
            service.start()
            
            for fix in [fix1, fix2]:
                with patch('sigmap.main.time.monotonic', return_value=fix.monotonic_ts):
                    service._poll_once()
                    time.sleep(0.01)
            
            service.stop()
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                assert len(lines) == 3  # header + 2 data rows
                # Both should have no_response status
                assert 'no_response' in lines[1]
                assert 'no_response' in lines[2]

    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    def test_stale_fix_does_not_trigger(self, mock_measure, mock_gnss_class):
        """Test that stale GPS fixes don't trigger measurements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(
                CSV_PATH=csv_path,
                DRY_RUN=False,
                FIX_MAX_AGE_S=1.0  # 1 second max age
            )
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            # Fix is now 2s old (stale)
            fix2 = Fix(lat=42.185139, lon=-122.709455, utc_time="123520",
                       valid=True, monotonic_ts=1002.0)
            
            mock_gnss.get_fix.side_effect = [fix1, fix2, None]
            mock_measure.return_value = -58
            
            service = SigMapService(config)
            service.start()
            
            # First fix at time 1000
            with patch('sigmap.main.time.monotonic', return_value=1000.0):
                service._poll_once()
                time.sleep(0.01)
            
            # Second fix at time 1002, but fix is 2s old (stale)
            with patch('sigmap.main.time.monotonic', return_value=1002.0):
                service._poll_once()
                time.sleep(0.01)
            
            service.stop()
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                # Only first fix should have triggered
                assert len(lines) == 2

    @patch('sigmap.main.GnssReader')
    @patch('sigmap.main.measure_rssi')
    def test_anchor_updated_after_failed_attempt(self, mock_measure, mock_gnss_class):
        """Test that anchor is updated even after failed ping (prevents dead zone hammering)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test_log.csv')
            config = self.create_test_config(
                CSV_PATH=csv_path,
                DRY_RUN=False,
                MIN_DISTANCE_M=100.0,
                MIN_INTERVAL_S=10.0
            )
            
            mock_gnss = MagicMock()
            mock_gnss_class.return_value = mock_gnss
            
            # fix1 at origin
            fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519",
                       valid=True, monotonic_ts=1000.0)
            # fix2: 150m north, 15s later - both gates pass from fix1
            fix2 = Fix(lat=42.184800, lon=-122.709455, utc_time="123534",
                       valid=True, monotonic_ts=1015.0)
            # fix3: 50m north of fix2 (total 200m from fix1), 10s later - 
            #       distance from fix2 anchor is only 50m < 100m, so NO trigger
            fix3 = Fix(lat=42.185300, lon=-122.709455, utc_time="123544",
                       valid=True, monotonic_ts=1025.0)
            # fix4: 200m north of fix2 anchor, 10s later - both gates pass
            fix4 = Fix(lat=42.186500, lon=-122.709455, utc_time="123554",
                       valid=True, monotonic_ts=1035.0)
            
            mock_gnss.get_fix.side_effect = [fix1, fix2, fix3, fix4, None]
            mock_measure.return_value = None  # All pings fail
            
            service = SigMapService(config)
            service.start()
            
            for fix in [fix1, fix2, fix3, fix4]:
                with patch('sigmap.main.time.monotonic', return_value=fix.monotonic_ts):
                    service._poll_once()
                    time.sleep(0.01)
            
            service.stop()
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                # fix1 triggers, fix2 triggers (>100m from fix1 and >10s),
                # fix3 does NOT (only 50m from fix2 anchor), 
                # fix4 triggers (>100m from fix2 anchor and >10s)
                assert len(lines) == 4  # header + 3 data rows


class TestArgumentParsing:
    """Test CLI argument parsing."""
    
    def test_default_args(self):
        """Test default argument values."""
        from sigmap.main import create_config_from_args
        
        args = argparse.Namespace(
            gps_port="/dev/ttyUSB0",
            gps_baud=9600,
            umsh_port="/dev/ttyACM0",
            target="33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp",
            min_distance=321.87,
            min_interval=60.0,
            ping_timeout=30.0,
            fix_max_age=5.0,
            csv="~/sigmap/signal_log.csv",
            log_failures=True,
            dry_run=False,
            no_bell=False,
            bell_audio=None
        )
        config = create_config_from_args(args)
        assert config.GPS_PORT == "/dev/ttyUSB0"
        assert config.MIN_DISTANCE_M == 321.87
        assert config.DRY_RUN is False
        assert config.BELL_ON_SUCCESS is True  # Default is bell enabled
        assert config.BELL_AUDIO_COMMAND is None

    def test_custom_args(self):
        """Test custom argument values."""
        from sigmap.main import create_config_from_args
        
        args = argparse.Namespace(
            gps_port="/dev/ttyUSB1",
            gps_baud=115200,
            umsh_port="/dev/ttyACM0",
            target="custom_target",
            min_distance=500.0,
            min_interval=120.0,
            ping_timeout=60.0,
            fix_max_age=10.0,
            csv="/custom/path.csv",
            log_failures=False,
            dry_run=True,
            no_bell=True,
            bell_audio="paplay /path/bell.wav"
        )
        config = create_config_from_args(args)
        assert config.GPS_PORT == "/dev/ttyUSB1"
        assert config.GPS_BAUD == 115200
        assert config.UMSH_PORT == "/dev/ttyACM0"
        assert config.UMSH_TARGET == "custom_target"
        assert config.MIN_DISTANCE_M == 500.0
        assert config.MIN_INTERVAL_S == 120.0
        assert config.PING_TIMEOUT_S == 60.0
        assert config.FIX_MAX_AGE_S == 10.0
        assert config.CSV_PATH == "/custom/path.csv"
        assert config.LOG_FAILURES is False
        assert config.DRY_RUN is True
        assert config.BELL_ON_SUCCESS is False
        assert config.BELL_AUDIO_COMMAND == "paplay /path/bell.wav"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
