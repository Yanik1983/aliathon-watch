import json
from datetime import datetime, timezone

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


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = settings.Settings(rooms=("1BSU", "2B"), min_nights=3, max_nights=10)
    settings.save(p, s, NOW)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"rooms": ["1BSU", "2B"], "min_nights": 3, "max_nights": 10, "updated": NOW.isoformat()}
    assert settings.load(p) == s


@pytest.mark.parametrize(
    "rooms,lo,hi,known",
    [
        ((), 5, 8, ()),
        (("1BED",), 0, 8, ()),
        (("1BED",), 6, 5, ()),
        (("1BED",), 5, 16, ()),
        (("1BED",), "five", 8, ()),
        (("bad code",), 5, 8, ()),
        (("XYZ",), 5, 8, ("1BED", "S1BED")),
    ],
)
def test_validate_rejects(rooms, lo, hi, known):
    with pytest.raises(ValueError):
        settings.validate(rooms, lo, hi, known)


def test_validate_normalises_and_dedupes():
    s = settings.validate(["s1bed", " 1BED ", "1BED"], "5", "8", ("1BED", "S1BED"))
    assert s == settings.Settings(rooms=("S1BED", "1BED"), min_nights=5, max_nights=8)


def test_cli_writes_file_using_state_rooms(tmp_path):
    state = _state_with_rooms(tmp_path, "1BED")
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "1BED", "--min", "5", "--max", "7", "--state", str(state), "--out", str(out)])
    assert rc == 0
    assert settings.load(out) == settings.Settings(rooms=("1BED",), min_nights=5, max_nights=7)


def test_cli_rejects_unknown_room_and_writes_nothing(tmp_path, capsys):
    state = _state_with_rooms(tmp_path, "1BED")
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "STD", "--min", "5", "--max", "7", "--state", str(state), "--out", str(out)])
    assert rc == 1
    assert not out.exists()
    assert "STD" in capsys.readouterr().err


def test_cli_without_state_accepts_any_wellformed_code(tmp_path):
    out = tmp_path / "settings.json"
    rc = settings.main(
        ["--rooms", "SW1B,2BSU", "--min", "1", "--max", "15", "--state", str(tmp_path / "none.json"), "--out", str(out)]
    )
    assert rc == 0
    assert settings.load(out).rooms == ("SW1B", "2BSU")
