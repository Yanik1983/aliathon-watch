import json
from datetime import date, timedelta
from pathlib import Path

from watch.finder import Window, find_windows
from watch.parser import Grid, RoomRow, parse_grid

FIRST = date(2027, 8, 14)
LAST_CHECKOUT = date(2027, 8, 29)
DATES = [FIRST + timedelta(i) for i in range(15)]


def grid(open_dates: dict[str, set[date]], price: int = 100) -> Grid:
    rooms = {}
    for code in ("1BED", "S1BED"):
        opened = open_dates.get(code, set())
        rooms[code] = RoomRow(
            code=code,
            name=code,
            status="NA",
            nights={d: (price if d in opened else None) for d in DATES},
        )
    return Grid(dates=DATES, rooms=rooms)


def run(g: Grid):
    return find_windows(
        g,
        rooms=("1BED", "S1BED"),
        min_nights=5,
        max_nights=8,
        first_checkin=FIRST,
        last_checkout=LAST_CHECKOUT,
    )


def days(start: int, end_inclusive: int) -> set[date]:
    return {date(2027, 8, d) for d in range(start, end_inclusive + 1)}


def test_all_sold_gives_nothing():
    assert run(grid({})) == []


def test_exact_five_night_run():
    result = run(grid({"1BED": days(14, 18)}))
    assert result == [Window(room="1BED", checkin=date(2027, 8, 14), nights=5, total=500)]


def test_window_properties():
    w = Window(room="S1BED", checkin=date(2027, 8, 20), nights=6, total=1200)
    assert w.checkout == date(2027, 8, 26)
    assert w.key == "S1BED|2027-08-20|6"


def test_nine_night_run_yields_all_sub_windows():
    result = run(grid({"1BED": days(14, 22)}))
    assert len(result) == 14
    by_nights = {}
    for w in result:
        by_nights.setdefault(w.nights, []).append(w.checkin.day)
    assert by_nights == {
        5: [14, 15, 16, 17, 18],
        6: [14, 15, 16, 17],
        7: [14, 15, 16],
        8: [14, 15],
    }


def test_four_night_run_is_too_short():
    assert run(grid({"1BED": days(20, 23)})) == []


def test_run_ending_on_last_night_allowed():
    result = run(grid({"S1BED": days(24, 28)}))
    assert result == [Window(room="S1BED", checkin=date(2027, 8, 24), nights=5, total=500)]


def test_checkout_bound_respected():
    g = grid({"1BED": days(22, 28)})
    result = find_windows(
        g, rooms=("1BED",), min_nights=5, max_nights=8,
        first_checkin=FIRST, last_checkout=date(2027, 8, 28),
    )
    assert [(w.checkin.day, w.nights) for w in result] == [(22, 5), (23, 5), (22, 6)]


def test_first_checkin_bound_respected():
    g = grid({"1BED": days(14, 20)})
    result = find_windows(
        g, rooms=("1BED",), min_nights=5, max_nights=8,
        first_checkin=date(2027, 8, 15), last_checkout=LAST_CHECKOUT,
    )
    assert [(w.checkin.day, w.nights) for w in result] == [(15, 5), (16, 5), (15, 6)]


def test_only_requested_rooms_considered():
    g = grid({"1BED": days(14, 22), "S1BED": days(14, 22)})
    result = find_windows(
        g, rooms=("S1BED",), min_nights=5, max_nights=8,
        first_checkin=FIRST, last_checkout=LAST_CHECKOUT,
    )
    assert result and all(w.room == "S1BED" for w in result)


def test_total_sums_nightly_prices():
    g = grid({"1BED": days(14, 18)}, price=280)
    assert run(g)[0].total == 1400


def test_real_fixture_has_no_windows():
    html = json.loads(
        (Path(__file__).parent / "fixtures" / "avl_15n.json").read_text(encoding="utf-8")
    )["html"]
    assert run(parse_grid(html)) == []
