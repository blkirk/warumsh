"""
Unit tests for signal.py module.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.signal import parse_rssi, measure_rssi, find_umshctl
from unittest.mock import patch, MagicMock


class TestParseRSSI:
    def test_parse_example_ping(self):
        stdout = """administrator:9xYPLk1jj7tYfkJabgf6GpmXFq48bw8KjpyVcf9Xm4kU
target:       33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp
shape:        8 bytes echo, mic 8, 5 flood hops
seq 1: reply in 0.42 s, 1 hop, -58 dBm, snr 8.8 dBm
replies:      1 of 1 (0% loss)
rtt:          min/avg/max 0.42/0.42/0.42 s"""
        rssi = parse_rssi(stdout)
        assert rssi == -58

    def test_parse_positive_rssi(self):
        stdout = "seq 1: reply in 0.42 s, 1 hop, 45 dBm, snr 8.8 dBm"
        rssi = parse_rssi(stdout)
        assert rssi == 45

    def test_parse_negative_rssi_various(self):
        test_cases = [
            ("seq 1: reply in 0.42 s, 1 hop, -58 dBm, snr 8.8 dBm", -58),
            ("seq 1: reply in 0.42 s, 1 hop, -120 dBm, snr 8.8 dBm", -120),
            ("seq 1: reply in 0.42 s, 1 hop, -0 dBm, snr 8.8 dBm", 0),
        ]
        for stdout, expected in test_cases:
            assert parse_rssi(stdout) == expected

    def test_multiple_seq_lines_uses_first(self):
        stdout = """seq 1: reply in 0.42 s, 1 hop, -58 dBm, snr 8.8 dBm
seq 2: reply in 0.43 s, 1 hop, -60 dBm, snr 8.5 dBm"""
        rssi = parse_rssi(stdout)
        assert rssi == -58

    def test_no_seq_line_returns_none(self):
        stdout = "administrator:9xYPLk1jj7tYfkJabgf6GpmXFq48bw8KjpyVcf9Xm4kU\ntarget: 33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp"
        assert parse_rssi(stdout) is None

    def test_empty_stdout_returns_none(self):
        assert parse_rssi("") is None
        assert parse_rssi(None) is None

    def test_malformed_rssi_field(self):
        stdout = "seq 1: reply in 0.42 s, 1 hop, no_rssi_here, snr 8.8 dBm"
        assert parse_rssi(stdout) is None

    def test_rssi_with_extra_spaces(self):
        stdout = "seq 1: reply in 0.42 s, 1 hop,   -58   dBm  , snr 8.8 dBm"
        assert parse_rssi(stdout) == -58


class TestMeasureRSSI:
    @patch('sigmap.signal.subprocess.run')
    def test_successful_measurement(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "seq 1: reply in 0.42 s, 1 hop, -58 dBm, snr 8.8 dBm"
        mock_run.return_value = mock_result

        rssi = measure_rssi('/dev/ttyACM1', '33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp')
        assert rssi == -58
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == [find_umshctl(), '-p', '/dev/ttyACM1', 'ping', '--flood', '--flood-hops', '1', '33Esi6D3bJfqQM4n9LYTirdzecBteAKNvgscfvjBd2Tp']

    @patch('sigmap.signal.subprocess.run')
    def test_command_failure_returns_none(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "Error: device not found"
        mock_run.return_value = mock_result

        rssi = measure_rssi('/dev/ttyACM1', 'target')
        assert rssi is None

    @patch('sigmap.signal.subprocess.run')
    def test_timeout_returns_none(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('umshctl', 30)

        rssi = measure_rssi('/dev/ttyACM1', 'target')
        assert rssi is None

    @patch('sigmap.signal.subprocess.run')
    def test_umshctl_not_found_returns_none(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        rssi = measure_rssi('/dev/ttyACM1', 'target')
        assert rssi is None

    @patch('sigmap.signal.subprocess.run')
    def test_no_seq_line_returns_none(self, mock_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Some other output without seq line"
        mock_run.return_value = mock_result

        rssi = measure_rssi('/dev/ttyACM1', 'target')
        assert rssi is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
