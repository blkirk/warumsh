"""
Unit tests for geo.py and trigger.py modules.
"""

import pytest
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sigmap'))

from sigmap.geo import haversine_m
from sigmap.trigger import MeasurementTrigger
from sigmap.nmea import Fix


class TestHaversine:
    def test_same_point(self):
        dist = haversine_m(42.183339, -122.709455, 42.183339, -122.709455)
        assert dist == 0.0

    def test_known_distance(self):
        dist = haversine_m(42.183339, -122.709455, 42.193339, -122.709455)
        assert 1100 < dist < 1120

    def test_equator_longitude(self):
        dist = haversine_m(0.0, 0.0, 0.0, 1.0)
        assert 110000 < dist < 112000

    def test_pole_distance(self):
        dist = haversine_m(0.0, 0.0, 90.0, 0.0)
        expected = 3.14159 * 6371000 / 2
        assert abs(dist - expected) < 1000

    def test_symmetry(self):
        dist1 = haversine_m(42.0, -122.0, 43.0, -123.0)
        dist2 = haversine_m(43.0, -123.0, 42.0, -122.0)
        assert dist1 == dist2


class TestMeasurementTrigger:
    def test_first_fix_triggers(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        assert trigger.should_measure(fix, now=1000.0) is True

    def test_first_fix_marks_attempt(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        trigger.should_measure(fix, now=1000.0)
        trigger.mark_attempt(fix, now=1000.0)
        assert trigger.last_attempt_pos == (42.183339, -122.709455)
        assert trigger.last_attempt_time == 1000.0
        assert trigger.first_fix is False

    def test_time_gate_blocks(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        # Move enough to pass distance gate (>321m)
        fix2 = Fix(lat=42.215000, lon=-122.709455, utc_time="123520", valid=True, monotonic_ts=1001.0)
        
        trigger.should_measure(fix1, now=1000.0)
        trigger.mark_attempt(fix1, now=1000.0)
        
        # Only 30 seconds passed - should not trigger (time gate blocks)
        assert trigger.should_measure(fix2, now=1030.0) is False
        
        # 60 seconds passed AND distance > 321m - should trigger
        assert trigger.should_measure(fix2, now=1060.0) is True

    def test_distance_gate_blocks(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        fix2 = Fix(lat=42.184000, lon=-122.709455, utc_time="123520", valid=True, monotonic_ts=1001.0)  # ~74m away
        
        trigger.should_measure(fix1, now=1000.0)
        trigger.mark_attempt(fix1, now=1000.0)
        
        # Wait 60s but only moved ~74m - should not trigger (distance gate blocks)
        assert trigger.should_measure(fix2, now=1060.0) is False

    def test_both_gates_pass(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        # Move ~3.5 km north
        fix2 = Fix(lat=42.215000, lon=-122.709455, utc_time="123520", valid=True, monotonic_ts=1001.0)
        
        trigger.should_measure(fix1, now=1000.0)
        trigger.mark_attempt(fix1, now=1000.0)
        
        # Wait 60s AND moved > 321m - should trigger
        assert trigger.should_measure(fix2, now=1060.0) is True

    def test_invalid_fix_never_triggers(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=False, monotonic_ts=1000.0)
        assert trigger.should_measure(fix, now=1000.0) is False

    def test_mark_attempt_updates_anchor(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        fix2 = Fix(lat=42.215000, lon=-122.709455, utc_time="123520", valid=True, monotonic_ts=1001.0)
        
        trigger.should_measure(fix1, now=1000.0)
        trigger.mark_attempt(fix1, now=1000.0)
        
        assert trigger.should_measure(fix2, now=1060.0) is True
        trigger.mark_attempt(fix2, now=1060.0)
        
        assert trigger.last_attempt_pos == (42.215000, -122.709455)
        assert trigger.last_attempt_time == 1060.0

    def test_failed_attempt_still_updates_anchor(self):
        """Failed ping attempts should still update anchor to prevent hammering dead zones."""
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix1 = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        fix2 = Fix(lat=42.184000, lon=-122.709455, utc_time="123520", valid=True, monotonic_ts=1001.0)
        
        trigger.should_measure(fix1, now=1000.0)
        trigger.mark_attempt(fix1, now=1000.0)  # This simulates a failed attempt
        
        # Even though ping failed, anchor is updated
        # Next attempt should require BOTH gates from the new position
        assert trigger.should_measure(fix2, now=1060.0) is False  # Only ~74m moved
        
        fix3 = Fix(lat=42.215000, lon=-122.709455, utc_time="123521", valid=True, monotonic_ts=1002.0)
        assert trigger.should_measure(fix3, now=1060.0) is True  # >321m from fix1

    def test_reset(self):
        trigger = MeasurementTrigger(min_dist_m=321.87, min_interval_s=60.0)
        fix = Fix(lat=42.183339, lon=-122.709455, utc_time="123519", valid=True, monotonic_ts=1000.0)
        
        trigger.should_measure(fix, now=1000.0)
        trigger.mark_attempt(fix, now=1000.0)
        
        trigger.reset()
        
        assert trigger.last_attempt_pos is None
        assert trigger.last_attempt_time is None
        assert trigger.first_fix is True
        
        # Should trigger again as first fix
        assert trigger.should_measure(fix, now=1000.0) is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
