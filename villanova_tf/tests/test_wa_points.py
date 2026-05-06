"""
Tests for WA points conversion.
Verify a handful of real-world marks against published WA tables.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from villanova_tf.processing.wa_points import score, _parse_seconds, _parse_field_meters


class TestParseSeconds:
    def test_simple_seconds(self):
        assert _parse_seconds("10.48") == pytest.approx(10.48)

    def test_minutes_seconds(self):
        assert _parse_seconds("1:45.23") == pytest.approx(105.23)

    def test_hours_minutes_seconds(self):
        assert _parse_seconds("1:02:30.0") == pytest.approx(3750.0)

    def test_empty(self):
        assert _parse_seconds("") is None

    def test_invalid(self):
        assert _parse_seconds("NM") is None


class TestParseFieldMeters:
    def test_decimal(self):
        assert _parse_field_meters("8.32") == pytest.approx(8.32)

    def test_with_m_suffix(self):
        assert _parse_field_meters("8.32m") == pytest.approx(8.32)

    def test_imperial(self):
        # 6 feet 2.5 inches = 1.8923 meters
        val = _parse_field_meters("6-02.50")
        assert val == pytest.approx((6 * 12 + 2.5) * 0.0254, abs=0.001)

    def test_empty(self):
        assert _parse_field_meters("") is None


class TestScore:
    # Reference values from World Athletics published tables (approximate)
    def test_100m_men_world_class(self):
        pts = score("100m", "M", "9.58")
        assert pts is not None
        assert pts > 1200  # Bolt WR gives ~1202 pts on 2022 WA tables

    def test_100m_men_good_collegiate(self):
        pts = score("100m", "M", "10.50")
        assert pts is not None
        assert 900 < pts < 1100

    def test_100m_women(self):
        pts = score("100m", "F", "11.20")
        assert pts is not None
        assert pts > 0

    def test_400m_men(self):
        pts = score("400m", "M", "45.00")
        assert pts is not None
        assert pts > 900

    def test_1500m_men(self):
        pts = score("1500m", "M", "3:35.00")
        assert pts is not None
        assert pts > 900

    def test_shot_put_men(self):
        pts = score("shot_put", "M", "20.00")
        assert pts is not None
        assert pts > 900

    def test_high_jump_men(self):
        pts = score("high_jump", "M", "2.10")
        assert pts is not None
        assert pts > 800

    def test_combined_events(self):
        # Combined: score is the points total directly
        pts = score("decathlon", "M", "8000")
        assert pts == 8000

        pts = score("heptathlon", "F", "6500")
        assert pts == 6500

    def test_zero_for_sub_threshold(self):
        pts = score("100m", "M", "18.0")
        assert pts == 0

    def test_unknown_event(self):
        pts = score("relay_4x100", "M", "38.50")
        assert pts is None

    def test_empty_mark(self):
        assert score("100m", "M", "") is None

    def test_better_performance_higher_points_track(self):
        pts_fast = score("100m", "M", "10.00")
        pts_slow = score("100m", "M", "11.00")
        assert pts_fast > pts_slow

    def test_better_performance_higher_points_field(self):
        pts_far = score("long_jump", "M", "8.00")
        pts_near = score("long_jump", "M", "7.00")
        assert pts_far > pts_near
