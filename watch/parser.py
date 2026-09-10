"""Parse the HTML fragment returned by WebHotelier's /avl endpoint.

The fragment is a table. For each room there is a ``<tr class="room">`` with
``<td class="name">`` and one ``<th><span data-date="...">`` per night, then
one or more rate rows ``<tr data-status="AVL|NA" data-room="CODE" ...>`` with
one ``<td>`` per night: ``class="noavl"`` (sold) or ``class="range"`` with a
price (open). The last ``<td class="">`` is the check-out column.
"""
from __future__ import annotations

import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import date


class ParseError(Exception):
    """Raised when the response does not look like an availability grid."""


@dataclass
class RoomRow:
    code: str
    name: str
    status: str  # "AVL" or "NA" from the first rate row
    nights: dict[date, int | None] = field(default_factory=dict)


@dataclass
class Grid:
    dates: list[date]
    rooms: dict[str, RoomRow]


_ROOM_SPLIT = re.compile(r'<tr class="room">')
_NAME = re.compile(r'<td class="name"[^>]*>(.*?)</td>', re.S)
_DATE = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"')
_RATE_ROW = re.compile(r'<tr\s+data-status="([^"]*)"(.*?)</tr>', re.S)
_ROOM_CODE = re.compile(r'data-room="([^"]+)"')
_CELL = re.compile(r'<td class="(noavl|range|)"[^>]*>(.*?)</td>', re.S)
_PRICE = re.compile(r"(?:&euro;|€)\s*([\d.,]+)")


def _price(cell_html: str) -> int | None:
    m = _PRICE.search(cell_html)
    if not m:
        return None
    return int(round(float(m.group(1).replace(",", ""))))


def parse_grid(html: str) -> Grid:
    blocks = _ROOM_SPLIT.split(html)[1:]
    if not blocks:
        raise ParseError("no room rows found")

    rooms: dict[str, RoomRow] = {}
    dates: list[date] = []
    for block in blocks:
        name_m = _NAME.search(block)
        rate_m = _RATE_ROW.search(block)
        if not name_m or not rate_m:
            continue
        block_dates = [date.fromisoformat(d) for d in _DATE.findall(block)]
        if not block_dates:
            continue
        # Header lists each night plus the check-out day; nights = all but last.
        night_dates = block_dates[:-1] if len(block_dates) > 1 else block_dates
        if not dates:
            dates = night_dates

        status = rate_m.group(1)
        row_html = rate_m.group(2)
        code_m = _ROOM_CODE.search(row_html)
        if not code_m:
            continue
        code = code_m.group(1)
        # Cells: the row starts with the rate description <td scope="row" ...>,
        # which does not match _CELL (class is "spec status"). Remaining cells
        # are nights followed by the check-out column.
        cells = _CELL.findall(row_html)
        night_cells = cells[: len(night_dates)]
        nights: dict[date, int | None] = {}
        for d, (cls, inner) in zip(night_dates, night_cells):
            nights[d] = None if cls == "noavl" else _price(inner)
        for d in night_dates[len(night_cells):]:
            nights[d] = None

        name = htmllib.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip()
        rooms[code] = RoomRow(code=code, name=name, status=status, nights=nights)

    if not rooms:
        raise ParseError("no parseable room rows")
    return Grid(dates=dates, rooms=rooms)
