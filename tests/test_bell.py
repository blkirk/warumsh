"""
Tests for the bell notification module.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, mock_open
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.bell import emit_bell, terminal_bell


class TestTerminalBell:
    """Tests for terminal_bell function."""
    
    @patch('sys.stdout')
    def test_terminal_bell_writes_bel(self, mock_stdout):
        """Test that terminal_bell writes ASCII BEL character."""
        terminal_bell()
        mock_stdout.write.assert_called_with('\a')
        mock_stdout.flush.assert_called_once()

    @patch('sys.stdout')
    def test_emit_bell_default(self, mock_stdout):
        """Test emit_bell with default terminal output."""
        emit_bell()
        mock_stdout.write.assert_called_with('\a')

    @patch('sys.stdout')
    def test_emit_bell_no_terminal(self, mock_stdout):
        """Test emit_bell with terminal bell disabled."""
        emit_bell(use_terminal=False)
        mock_stdout.write.assert_not_called()

    @patch('sigmap.bell.subprocess.run')
    @patch('sys.stdout')
    def test_emit_bell_with_audio_command(self, mock_stdout, mock_run):
        """Test emit_bell with an audio command."""
        mock_run.return_value = MagicMock(returncode=0)
        
        emit_bell(use_terminal=True, audio_command='paplay /path/to/bell.wav')
        
        mock_stdout.write.assert_called_with('\a')
        mock_run.assert_called_once()
        # Check that the command was passed as a string with shell=True
        call_args = mock_run.call_args
        assert call_args[0][0] == 'paplay /path/to/bell.wav'
        assert call_args[1]['shell'] == True

    @patch('sigmap.bell.subprocess.run')
    def test_emit_bell_audio_command_timeout(self, mock_run):
        """Test that emit_bell handles audio command timeout gracefully."""
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd='paplay', timeout=5.0)
        
        # Should not raise
        emit_bell(use_terminal=False, audio_command='paplay /path/to/bell.wav')
        mock_run.assert_called_once()

    @patch('sigmap.bell.subprocess.run')
    def test_emit_bell_audio_command_not_found(self, mock_run):
        """Test that emit_bell handles missing audio command gracefully."""
        mock_run.side_effect = FileNotFoundError("paplay not found")
        
        # Should not raise
        emit_bell(use_terminal=False, audio_command='paplay /path/to/bell.wav')
        mock_run.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
