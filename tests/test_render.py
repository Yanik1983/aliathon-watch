import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from watch.parser import parse_grid
from watch.render import render_page

HTML = json.loads(
    (Path(__file__).parent / "fixtures" / "avl_15n.json").read_text(encoding="utf-8")
)["html"]
GRID = parse_grid(HTML)
NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)

CONFIRMED = {
    "S1BED|2027-08-20|5": {
        "room": "S1BED",
        "room_name": "Superior One Bedroom Apartment",
        "checkin": "2027-08-20",
        "nights": 5,
        "price": 1450,
        "url": "https://aliathonaegean.reserve-online.net/?checkin=2027-08-20&nights=5",
        "first_seen": "2026-09-10T19:50:00+00:00",
    }
}


def test_page_lists_rooms_and_dates():
    page = render_page(GRID, {}, NOW, 0)
    assert "One Bedroom Apartment" in page
    assert "Superior One Bedroom Apartment" in page
    assert "Aug 14" in page and "Aug 28" in page


def test_page_no_windows_message():
    page = render_page(GRID, {}, NOW, 0)
    assert "No bookable stays" in page


def test_page_lists_confirmed_window():
    page = render_page(GRID, CONFIRMED, NOW, 0)
    assert html.escape(CONFIRMED["S1BED|2027-08-20|5"]["url"]) in page
    assert "5 nights" in page
    assert "1,450" in page or "1450" in page
    assert "No bookable stays" not in page


def test_open_cell_shows_price_and_class():
    page = render_page(GRID, {}, NOW, 0)
    # 1BED row, 2027-08-20 is open at 280
    m = re.search(r'<td class="open" data-room="1BED" data-date="2027-08-20">([^<]*)</td>', page)
    assert m and "280" in m.group(1)
    assert re.search(r'<td class="sold" data-room="1BED" data-date="2027-08-14">', page)


def test_target_rooms_first():
    page = render_page(GRID, {}, NOW, 0)
    assert page.index("One Bedroom Apartment") < page.index("Studio")


def test_no_grid_yet():
    page = render_page(None, {}, None, 0)
    assert "no data yet" in page.lower()


def test_failure_banner():
    page = render_page(GRID, {}, NOW, 3)
    assert "3 consecutive" in page


def test_times_shown():
    page = render_page(GRID, {}, NOW, 0)
    assert "2026-09-10 20:00 UTC" in page
    assert "23:00" in page  # Cyprus is UTC+3 in September


def test_no_history_section_placeholder():
    page = render_page(GRID, {}, NOW, 0, history=[])
    assert "Price history" in page
    assert "No history yet" in page
    assert "priceChart" not in page


def test_history_chart_embedded():
    from watch import history as history_mod

    h = []
    history_mod.append_if_changed(h, GRID, NOW)
    page = render_page(GRID, {}, NOW, 0, history=h)
    assert '<canvas id="priceChart">' in page
    assert "cdnjs.cloudflare.com/ajax/libs/Chart.js" in page
    assert '"label": "One Bedroom Apartment"' in page
    assert '"y": 280' in page
    assert "1 change(s) recorded" in page
    # one dataset per room x package, only the first package visible at load
    assert page.count('"rate": "Standard Rate | All Inclusive"') == 8
    assert page.count('"hidden": false') == 8
    assert page.count('"hidden": true') == 16
    # package buttons
    assert 'data-rate="Standard Rate | Breakfast">Breakfast</button>' in page
    assert 'data-rate="Standard Rate | All Inclusive">All Inclusive</button>' in page
    # table: Studio 260 / 320 (+60) / 370 (+110)
    assert "<td>€260</td><td>€320 <small>(+60)</small></td><td>€370 <small>(+110)</small></td>" in page
    assert "<th>Half Board Plus<br><small>vs Breakfast</small></th>" in page


def test_history_table_shows_change_since_first():
    from watch import history as history_mod

    h = []
    history_mod.append_if_changed(h, GRID, NOW)
    old = {"t": "2026-09-01T00:00:00+00:00", "rooms": {"STD": {"name": "Studio",
           "rates": {"Standard Rate | Breakfast": {"2027-08-20": 250}}}}}
    page = render_page(GRID, {}, NOW, 0, history=[old] + h)
    assert "<td>€260 <small>(+10 since first)</small></td>" in page
