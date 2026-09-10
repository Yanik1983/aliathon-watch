"""Confirm a candidate window by querying the exact dates.

Per-night prices in the 15-night grid show inventory per night, but the hotel
may still refuse a stay (minimum-stay rules, closed-to-arrival). A query with
the exact check-in and nights answers ``data-status="AVL"`` only when the stay
is truly bookable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

from watch import config
from watch.client import FetchError, fetch_avl
from watch.finder import Window
from watch.parser import ParseError, parse_grid

log = logging.getLogger(__name__)

Fetch = Callable[[date, int], str]


@dataclass(frozen=True)
class ConfirmedWindow:
    window: Window
    room_name: str
    price: int
    url: str


def booking_url(checkin: date, nights: int) -> str:
    return (
        f"{config.BASE_URL}/?checkin={checkin.isoformat()}&nights={nights}"
        f"&rooms={config.ROOMS}&adults={config.ADULTS}"
        f"&children={config.CHILDREN}&infants={config.INFANTS}"
    )


def confirm(window: Window, fetch: Fetch = fetch_avl) -> ConfirmedWindow | None:
    try:
        html = fetch(window.checkin, window.nights)
        grid = parse_grid(html)
    except (FetchError, ParseError) as e:
        log.warning("confirm %s failed: %s", window.key, e)
        return None
    row = grid.rooms.get(window.room)
    if row is None or row.status != "AVL":
        return None
    prices = [row.nights.get(d) for d in grid.dates]
    total = sum(p for p in prices if p is not None) if prices else window.total
    return ConfirmedWindow(
        window=window,
        room_name=row.name,
        price=total or window.total,
        url=booking_url(window.checkin, window.nights),
    )
