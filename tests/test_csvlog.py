"""
Unit tests for csvlog.py module.
"""

import pytest
import sys
import os
import tempfile
import csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.csvlog import CsvLogger, CSV_HEADER, create_timestamp_utc
from sigmap.nmea import Fix


class TestCsvLogger:
    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'subdir', 'signal_log.csv')
            logger = CsvLogger(path)
            logger.close()
            assert os.path.exists(path)

    def test_writes_header_on_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            logger.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert rows[0] == CSV_HEADER

    def test_does_not_duplicate_header_on_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            old_header = ['timestamp_utc', 'latitude', 'longitude', 'rssi_dbm', 'status', 'speed_kmh', 'hdop', 'satellites']
            # Create file with old header (8 columns) and one row
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(old_header)
                writer.writerow(['2026-10-20T04:00:15Z', '42.183339', '-122.709455', '-58', 'ok', '0.00', '1.0', '11'])
            
            # Open with CsvLogger (file is not empty, so no header written)
            logger = CsvLogger(path)
            logger.write('2026-10-20T04:00:16Z', 42.183340, -122.709456, -59, 'ok')
            logger.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                # Should have original header + original row + new row = 3 rows
                assert len(rows) == 3
                # Header is the old one since file was not empty
                assert rows[0] == old_header

    def test_writes_data_row(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            logger.write('2026-10-20T04:00:15Z', 42.183339, -122.709455, -58, 'ok', 0.0, 1.0, 11)
            logger.close()
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2  # header + 1 data row
                assert rows[1] == ['2026-10-20T04:00:15Z', '42.183339', '-122.709455', '-58', 'ok', '0.00', '1.0', '11', '']

    def test_writes_row_with_none_optional_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            logger.write('2026-10-20T04:00:15Z', 42.183339, -122.709455, None, 'no_response', None, None, None)
            logger.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert rows[1] == ['2026-10-20T04:00:15Z', '42.183339', '-122.709455', '', 'no_response', '', '', '', '']

    def test_write_from_fix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            
            fix = Fix(
                lat=42.183339,
                lon=-122.709455,
                utc_time="123519",
                speed_kmh=10.5,
                hdop=1.2,
                sats=8,
                valid=True,
                monotonic_ts=1000.0
            )
            from sigmap.csvlog import write_from_fix
            write_from_fix(logger, fix, -58, 'ok')
            logger.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2
                assert rows[1][0].startswith('2026-')  # timestamp
                assert rows[1][1] == '42.183339'
                assert rows[1][2] == '-122.709455'
                assert rows[1][3] == '-58'
                assert rows[1][4] == 'ok'
                assert rows[1][5] == '10.50'  # speed_kmh
                assert rows[1][6] == '1.2'   # hdop
                assert rows[1][7] == '8'     # satellites
                assert rows[1][8] == ''      # target_prefix

    def test_fsync_after_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            logger.write('2026-10-20T04:00:15Z', 42.183339, -122.709455, -58, 'ok')
            logger.close()
            
            assert os.path.exists(path)
            with open(path, 'r') as f:
                content = f.read()
                assert '42.183339' in content

    def test_context_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            with CsvLogger(path) as logger:
                logger.write('2026-10-20T04:00:15Z', 42.183339, -122.709455, -58, 'ok')
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 2

    def test_append_mode_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            
            logger1 = CsvLogger(path)
            logger1.write('2026-10-20T04:00:15Z', 42.183339, -122.709455, -58, 'ok')
            logger1.close()
            
            logger2 = CsvLogger(path)
            logger2.write('2026-10-20T04:01:15Z', 42.183340, -122.709456, -59, 'ok')
            logger2.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert len(rows) == 3
                assert rows[1][3] == '-58'
                assert rows[2][3] == '-59'

    def test_coordinates_formatted_to_6_decimal_places(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'signal_log.csv')
            logger = CsvLogger(path)
            logger.write('2026-10-20T04:00:15Z', 42.183339123, -122.709455456, -58, 'ok')
            logger.close()
            
            with open(path, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                assert rows[1][1] == '42.183339'
                assert rows[1][2] == '-122.709455'


class TestCreateTimestampUTC:
    def test_format(self):
        ts = create_timestamp_utc()
        import re
        assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', ts)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
