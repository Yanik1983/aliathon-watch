import json
from datetime import date
from pathlib import Path

import pytest

from watch.parser import Grid, ParseError, parse_grid

FIXTURES = Path(__file__).parent / "fixtures"


def load_html(name: str) -> str:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["html"]


@pytest.fixture(scope="module")
def grid() -> Grid:
    return parse_grid(load_html("avl_15n.json"))


def test_dates_cover_15_nights(grid):
    assert len(grid.dates) == 15
    assert grid.dates[0] == date(2027, 8, 14)
    assert grid.dates[-1] == date(2027, 8, 28)


def test_room_codes_and_names(grid):
    assert {"1BED", "S1BED", "STD"} <= set(grid.rooms)
    assert grid.rooms["1BED"].name == "One Bedroom Apartment"
    assert grid.rooms["S1BED"].name == "Superior One Bedroom Apartment"


def test_row_status(grid):
    assert grid.rooms["STD"].status == "AVL"
    assert grid.rooms["1BED"].status == "NA"


def test_per_night_prices(grid):
    nights = grid.rooms["1BED"].nights
    assert len(nights) == 15
    assert nights[date(2027, 8, 20)] == 280
    assert nights[date(2027, 8, 21)] == 280
    assert nights[date(2027, 8, 28)] == 280
    assert nights[date(2027, 8, 14)] is None
    assert nights[date(2027, 8, 22)] is None


def test_studio_all_nights_open(grid):
    assert all(v is not None for v in grid.rooms["STD"].nights.values())


def test_7_night_fixture(grid):
    g = parse_grid(load_html("avl_7n_studio_avl.json"))
    assert len(g.dates) == 7
    assert g.rooms["STD"].status == "AVL"
    assert g.rooms["STD"].nights[date(2027, 8, 14)] == 260


def test_empty_html_raises():
    with pytest.raises(ParseError):
        parse_grid("<table></table>")


def test_all_packages_parsed(grid):
    rates = grid.rooms["1BED"].rates
    assert list(rates) == [
        "Standard Rate | Breakfast",
        "Standard Rate | Half Board Plus",
        "Standard Rate | All Inclusive",
    ]
    assert rates["Standard Rate | Breakfast"][date(2027, 8, 20)] == 280
    assert rates["Standard Rate | Half Board Plus"][date(2027, 8, 20)] == 340
    assert rates["Standard Rate | All Inclusive"][date(2027, 8, 20)] == 390
    assert rates["Standard Rate | All Inclusive"][date(2027, 8, 14)] is None
    assert grid.rooms["1BED"].nights == rates["Standard Rate | Breakfast"]
