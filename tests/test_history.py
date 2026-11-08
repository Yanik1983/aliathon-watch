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


def test_snapshot_stores_every_package():
    h = []
    history.append_if_changed(h, parse_grid(HTML), NOW)
    rates = h[0]["rooms"]["1BED"]["rates"]
    assert list(rates) == [
        "Standard Rate | Breakfast",
        "Standard Rate | Half Board Plus",
        "Standard Rate | All Inclusive",
    ]
    assert rates["Standard Rate | All Inclusive"]["2027-08-20"] == 390


def test_series_per_package_and_rate_names():
    h = []
    history.append_if_changed(h, parse_grid(HTML), NOW)
    s = history.series(h)
    assert s["1BED"]["rates"]["Standard Rate | Half Board Plus"] == [[NOW.isoformat(), 340]]
    assert s["1BED"]["points"] == [[NOW.isoformat(), 280]]
    assert history.rate_names(h) == [
        "Standard Rate | Breakfast",
        "Standard Rate | Half Board Plus",
        "Standard Rate | All Inclusive",
    ]


def test_old_snapshot_without_rates_still_works():
    old = [{"t": NOW.isoformat(), "rooms": {"1BED": {"name": "One Bedroom Apartment",
            "nights": {"2027-08-20": 280, "2027-08-21": None}}}}]
    s = history.series(old)
    assert s["1BED"]["rates"] == {history.DEFAULT_RATE: [[NOW.isoformat(), 280]]}
    assert history.rate_names(old) == [history.DEFAULT_RATE]


def test_package_price_change_appended():
    h = []
    g = parse_grid(HTML)
    history.append_if_changed(h, g, NOW)
    g.rooms["1BED"].rates["Standard Rate | All Inclusive"][date(2027, 8, 20)] = 400
    assert history.append_if_changed(h, g, NOW + timedelta(hours=1)) is True


def _snap(rooms):
    return {"t": NOW.isoformat(), "rooms": rooms}


def _room(name, nights, rate="Standard Rate | Breakfast"):
    return {"name": name, "nights": nights, "rates": {rate: nights}}


def test_describe_change_price_moved():
    prev = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 295, "2027-08-21": 295})})
    cur = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 310, "2027-08-21": 310})})
    assert history.summarize_change(prev, cur) == (
        "Aliathon: price rise",
        ["One Bedroom Apartment: price up: Breakfast €295 → €310. "
         "All 2 nights available, from €310/night (Breakfast)."],
    )


def test_describe_change_names_the_dates_that_opened_and_closed():
    prev = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 295, "2027-08-21": None, "2027-08-22": None})})
    cur = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": None, "2027-08-21": 295, "2027-08-22": 295})})
    assert history.summarize_change(prev, cur) == (
        "Aliathon: availability changed",
        ["One Bedroom Apartment: Fri 20 Aug sold out; 21-22 Aug now open (2 nights). "
         "2 of 3 nights available, from €295/night (Breakfast)."],
    )


def test_describe_change_sold_out_and_back():
    prev = _snap({"STD": _room("Studio", {"2027-08-20": 260})})
    cur = _snap({"STD": _room("Studio", {"2027-08-20": None})})
    assert history.summarize_change(prev, cur) == (
        "Aliathon: nights sold out", ["Studio: Fri 20 Aug sold out. Now fully booked."]
    )
    assert history.describe_change(cur, prev) == [
        "Studio: Fri 20 Aug now open. 1 of 1 night available, from €260/night (Breakfast)."
    ]


def test_describe_change_one_line_per_room_not_per_package():
    """A night closing in every package is one line naming the date (was 3 vague lines)."""
    nights = {f"2027-08-{d}": 295 for d in range(14, 19)}
    closed = dict(nights, **{"2027-08-15": None})
    def three(n, add=0):
        return {"name": "One Bedroom Apartment", "nights": n, "rates": {
            "Standard Rate | Breakfast": n,
            "Standard Rate | Half Board Plus": {d: p and p + 90 for d, p in n.items()},
            "Standard Rate | All Inclusive": {d: p and p + 165 for d, p in n.items()}}}
    prev, cur = _snap({"1BED": three(nights)}), _snap({"1BED": three(closed)})
    assert history.summarize_change(prev, cur) == (
        "Aliathon: nights sold out",
        ["One Bedroom Apartment: Sun 15 Aug sold out. 4 of 5 nights available, from €295/night (Breakfast)."],
    )


def test_describe_change_ignores_unchanged_and_lists_each_package():
    prev = _snap({"STD": {"name": "Studio", "nights": {"2027-08-20": 260},
                          "rates": {"Standard Rate | Breakfast": {"2027-08-20": 260},
                                    "Standard Rate | All Inclusive": {"2027-08-20": 370}}}})
    cur = _snap({"STD": {"name": "Studio", "nights": {"2027-08-20": 260},
                         "rates": {"Standard Rate | Breakfast": {"2027-08-20": 260},
                                   "Non Refundable Rate | All Inclusive": {"2027-08-20": 340},
                                   "Standard Rate | All Inclusive": {"2027-08-20": 380}}}})
    assert history.describe_change(prev, cur) == [
        "Studio: price up: All Inclusive €370 → €380. 1 of 1 night available, from €260/night (Breakfast)."
    ]


def test_describe_change_new_room_appears():
    prev = _snap({})
    cur = _snap({"STD": _room("Studio", {"2027-08-20": 260, "2027-08-21": None})})
    assert history.summarize_change(prev, cur) == (
        "Aliathon: nights opened",
        ["Studio: newly listed, 1 of 2 nights available, from €260/night (Breakfast)"],
    )


def test_describe_change_filters_rooms():
    prev = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 295}),
                  "STD": _room("Studio", {"2027-08-20": 260})})
    cur = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 310}),
                 "STD": _room("Studio", {"2027-08-20": 270})})
    lines = history.describe_change(prev, cur, rooms=["1BED"])
    assert len(lines) == 1 and lines[0].startswith("One Bedroom Apartment: price up: Breakfast €295 → €310.")
    assert history.describe_change(prev, cur, rooms=["2B"]) == []
    assert len(history.describe_change(prev, cur)) == 2


def _two_pkg(bf, ai):
    return {"name": "Studio", "nights": bf,
            "rates": {"Standard Rate | Breakfast": bf, "Standard Rate | All Inclusive": ai}}


def test_describe_change_filters_packages():
    prev = _snap({"STD": _two_pkg({"2027-08-20": 260}, {"2027-08-20": 370})})
    cur = _snap({"STD": _two_pkg({"2027-08-20": 250}, {"2027-08-20": 380})})
    assert history.describe_change(prev, cur, packages=["Standard Rate | All Inclusive"]) == [
        "Studio: price up: All Inclusive €370 → €380. 1 of 1 night available, from €380/night (All Inclusive)."
    ]
    assert history.summarize_change(prev, cur, packages=[]) == (
        "Aliathon: prices changed",
        ["Studio: price down: Breakfast €260 → €250; price up: All Inclusive €370 → €380. "
         "1 of 1 night available, from €250/night (Breakfast)."],
    )


def test_describe_change_improvements_only():
    prev = _snap({"STD": _room("Studio", {"2027-08-20": 260, "2027-08-21": None}),
                  "1BED": _room("One Bedroom Apartment", {"2027-08-20": 295}),
                  "2B": _room("Two Bedroom Apartment", {"2027-08-20": None}),
                  "SW1B": _room("Swim-Up", {"2027-08-20": 300, "2027-08-21": 300})})
    cur = _snap({"STD": _room("Studio", {"2027-08-20": 260, "2027-08-21": 260}),   # night opened
                 "1BED": _room("One Bedroom Apartment", {"2027-08-20": 310}),       # price up
                 "2B": _room("Two Bedroom Apartment", {"2027-08-20": 465}),         # sold out -> price
                 "SW1B": _room("Swim-Up", {"2027-08-20": 300, "2027-08-21": None})})  # night closed
    title, lines = history.summarize_change(prev, cur, mode="improvements")
    assert title == "Aliathon: nights opened"
    assert lines == [
        "Studio: Sat 21 Aug now open. All 2 nights available, from €260/night (Breakfast).",
        "Two Bedroom Apartment: Fri 20 Aug now open. 1 of 1 night available, from €465/night (Breakfast).",
    ]
    assert history.summarize_change(prev, cur, mode="off") == ("", [])
