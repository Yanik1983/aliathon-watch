import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from watch import history
from watch.parser import Grid, RoomRow, parse_grid

NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)
HTML = json.loads(
    (Path(__file__).parent / "fixtures" / "avl_15n.json").read_text(encoding="utf-8")
)["html"]


def small_grid(price_a=280, price_b=None):
    d1, d2 = date(2027, 8, 20), date(2027, 8, 21)
    return Grid(
        dates=[d1, d2],
        rooms={
            "1BED": RoomRow("1BED", "One Bedroom Apartment", "NA", {d1: price_a, d2: price_b}),
            "STD": RoomRow("STD", "Studio", "AVL", {d1: 260, d2: 250}),
        },
    )


def test_load_missing_is_empty(tmp_path):
    assert history.load(tmp_path / "h.json") == []


def test_first_snapshot_appended():
    h = []
    assert history.append_if_changed(h, small_grid(), NOW) is True
    assert len(h) == 1
    assert h[0]["t"] == NOW.isoformat()
    assert h[0]["rooms"]["1BED"]["nights"] == {"2027-08-20": 280, "2027-08-21": None}
    assert h[0]["rooms"]["1BED"]["name"] == "One Bedroom Apartment"


def test_unchanged_grid_not_appended():
    h = []
    history.append_if_changed(h, small_grid(), NOW)
    assert history.append_if_changed(h, small_grid(), NOW + timedelta(minutes=10)) is False
    assert len(h) == 1


def test_price_change_appended():
    h = []
    history.append_if_changed(h, small_grid(280), NOW)
    assert history.append_if_changed(h, small_grid(290), NOW + timedelta(hours=1)) is True
    assert len(h) == 2


def test_availability_change_appended():
    h = []
    history.append_if_changed(h, small_grid(280, None), NOW)
    assert history.append_if_changed(h, small_grid(280, 280), NOW) is True


def test_save_load_roundtrip(tmp_path):
    p = tmp_path / "history.json"
    h = []
    history.append_if_changed(h, small_grid(), NOW)
    history.save(p, h)
    assert history.load(p) == h


def test_series_lowest_price_per_room():
    h = []
    history.append_if_changed(h, small_grid(280, 300), NOW)
    history.append_if_changed(h, small_grid(None, None), NOW + timedelta(days=1))
    s = history.series(h)
    assert s["1BED"]["name"] == "One Bedroom Apartment"
    assert s["1BED"]["points"] == [[NOW.isoformat(), 280], [(NOW + timedelta(days=1)).isoformat(), None]]
    assert s["STD"]["points"][0][1] == 250


def test_series_from_real_fixture():
    h = []
    history.append_if_changed(h, parse_grid(HTML), NOW)
    s = history.series(h)
    assert s["1BED"]["points"] == [[NOW.isoformat(), 280]]
    assert s["STD"]["points"] == [[NOW.isoformat(), 260]]
