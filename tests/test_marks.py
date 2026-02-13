from compute.marks import parse_mark


def test_parse_track_time():
    r = parse_mark("1:48.25", "800m")
    assert round(r.mark_value, 2) == 108.25
    assert r.mark_units == "seconds"


def test_parse_field_feet_inches():
    r = parse_mark("26' 2\"", "Long Jump", "+1.4")
    assert r.mark_units == "meters"
    assert r.mark_value is not None and r.mark_value > 7.9
    assert r.wind_legal is True


def test_parse_points():
    r = parse_mark("5821", "Heptathlon")
    assert r.mark_value == 5821
    assert r.mark_units == "points"


def test_invalid_mark():
    r = parse_mark("DNF", "400m")
    assert r.mark_value is None
    assert r.confidence == "LOW"


def test_wind_illegal():
    r = parse_mark("10.20", "100m", "+2.5")
    assert r.wind_legal is False
    assert "wind_illegal_tailwind" in r.issues


def test_altitude_flag():
    r = parse_mark("7.85^", "Long Jump", "+0.4")
    assert r.altitude_flag is True
