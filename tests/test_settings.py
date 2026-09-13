import json
from datetime import date, datetime, timezone

import pytest

from watch import config, settings

NOW = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)


def _state_with_rooms(tmp_path, *codes):
    state = tmp_path / "state.json"
    rooms = {c: {"name": c, "status": "NA", "nights": {}} for c in codes}
    state.write_text(json.dumps({"grid": {"dates": [], "rooms": rooms}}), encoding="utf-8")
    return state


def test_defaults_match_config():
    s = settings.defaults()
    assert s.rooms == tuple(config.TARGET_ROOMS)
    assert (s.min_nights, s.max_nights) == (config.MIN_NIGHTS, config.MAX_NIGHTS)
    assert (s.first_checkin, s.last_checkout) == (config.FIRST_CHECKIN, config.LAST_CHECKOUT)
    assert (s.adults, s.children) == (config.ADULTS, config.CHILDREN)
    assert s.packages == () and s.price_alerts == "all" and s.max_price is None
    assert s.total_nights == config.TOTAL_NIGHTS


def test_load_missing_file_gives_defaults(tmp_path):
    assert settings.load(tmp_path / "settings.json") == settings.defaults()


def test_load_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert settings.load(p) == settings.defaults()


def test_load_invalid_values_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"rooms": [], "min_nights": 5, "max_nights": 8}), encoding="utf-8")
    assert settings.load(p) == settings.defaults()


def test_load_old_three_key_file_fills_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"rooms": ["2BSU"], "min_nights": 5, "max_nights": 8}), encoding="utf-8")
    s = settings.load(p)
    assert s.rooms == ("2BSU",)
    assert s.first_checkin == config.FIRST_CHECKIN and s.adults == config.ADULTS


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = settings.Settings(
        rooms=("1BSU", "2B"), min_nights=3, max_nights=10,
        first_checkin=date(2027, 8, 10), last_checkout=date(2027, 8, 30),
        adults=3, children=1, packages=("Standard Rate | Breakfast",),
        price_alerts="improvements", max_price=4000, client_id="abc-123",
    )
    settings.save(p, s, NOW)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["updated"] == NOW.isoformat()
    assert data["first_checkin"] == "2027-08-10" and data["max_price"] == 4000
    loaded = settings.load(p)
    assert loaded == settings.Settings(**{**s.__dict__, "updated": NOW})


@pytest.mark.parametrize(
    "data,known",
    [
        ({"rooms": []}, ()),
        ({"rooms": ["1BED"], "min_nights": 0}, ()),
        ({"rooms": ["1BED"], "min_nights": 6, "max_nights": 5}, ()),
        ({"rooms": ["1BED"], "max_nights": 16}, ()),  # beyond the 15-night default window
        ({"rooms": ["1BED"], "min_nights": "five"}, ()),
        ({"rooms": ["bad code"]}, ()),
        ({"rooms": ["XYZ"]}, ("1BED", "S1BED")),
        ({"first_checkin": "2027-08-20", "last_checkout": "2027-08-20"}, ()),
        ({"first_checkin": "2027-08-01", "last_checkout": "2027-09-15"}, ()),  # 45 nights
        ({"first_checkin": "not a date"}, ()),
        ({"adults": 0}, ()),
        ({"children": 7}, ()),
        ({"price_alerts": "sometimes"}, ()),
        ({"max_price": -5}, ()),
        ({"max_price": "cheap"}, ()),
        ({"client_id": "has space"}, ()),
        ([], ()),
    ],
)
def test_validate_rejects(data, known):
    with pytest.raises(ValueError):
        settings.validate(data, known)


def test_validate_normalises_and_dedupes():
    s = settings.validate(
        {"rooms": ["s1bed", " 1BED ", "1BED"], "min_nights": "5", "max_nights": "8",
         "packages": ["Standard Rate | Breakfast", " Standard Rate | Breakfast", ""],
         "price_alerts": "Improvements", "max_price": "", "client_id": "x1"},
        ("1BED", "S1BED"),
    )
    assert s.rooms == ("S1BED", "1BED")
    assert s.packages == ("Standard Rate | Breakfast",)
    assert s.price_alerts == "improvements" and s.max_price is None and s.client_id == "x1"


def test_validate_wider_window_allows_longer_stays():
    s = settings.validate({"first_checkin": "2027-08-01", "last_checkout": "2027-08-31", "max_nights": 20})
    assert s.total_nights == 30 and s.max_nights == 20


def test_cli_json_writes_file_using_state_rooms(tmp_path):
    state = _state_with_rooms(tmp_path, "1BED")
    out = tmp_path / "settings.json"
    payload = json.dumps({"rooms": ["1BED"], "min_nights": 5, "max_nights": 7, "adults": 2, "children": 0})
    rc = settings.main(["--json", payload, "--state", str(state), "--out", str(out)])
    assert rc == 0
    s = settings.load(out)
    assert s.rooms == ("1BED",) and s.max_nights == 7 and s.children == 0
    assert s.updated is not None


def test_cli_flags_override_json(tmp_path):
    out = tmp_path / "settings.json"
    rc = settings.main(["--json", '{"rooms": ["1BED"]}', "--rooms", "SW1B,2BSU", "--min", "1", "--max", "15",
                        "--state", str(tmp_path / "none.json"), "--out", str(out)])
    assert rc == 0
    assert settings.load(out).rooms == ("SW1B", "2BSU")


def test_cli_rejects_unknown_room_and_writes_nothing(tmp_path, capsys):
    state = _state_with_rooms(tmp_path, "1BED")
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "STD", "--state", str(state), "--out", str(out)])
    assert rc == 1
    assert not out.exists()
    assert "STD" in capsys.readouterr().err


def test_describe_mentions_every_knob():
    text = settings.describe(settings.defaults())
    assert "Rooms: 1BED, S1BED" in text and "5-8 nights" in text
    assert "2 adults, 2 children" in text and "Packages: all" in text and "Max price: none" in text
