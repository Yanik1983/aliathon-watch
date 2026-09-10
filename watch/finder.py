"""Find contiguous runs of open nights that form a bookable stay."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from watch.parser import Grid


@dataclass(frozen=True)
class Window:
    room: str
    checkin: date
    nights: int
    total: int

    @property
    def checkout(self) -> date:
        return self.checkin + timedelta(days=self.nights)

    @property
    def key(self) -> str:
        return f"{self.room}|{self.checkin.isoformat()}|{self.nights}"


def find_windows(
    grid: Grid,
    rooms: Iterable[str],
    min_nights: int,
    max_nights: int,
    first_checkin: date,
    last_checkout: date,
) -> list[Window]:
    """Return every (room, checkin, nights) whose nights are all priced.

    Ordered by nights ascending, then check-in date, then room order given.
    """
    out: list[Window] = []
    for nights in range(min_nights, max_nights + 1):
        checkin = first_checkin
        while checkin + timedelta(days=nights) <= last_checkout:
            for code in rooms:
                row = grid.rooms.get(code)
                if row is None:
                    continue
                prices = [
                    row.nights.get(checkin + timedelta(days=i)) for i in range(nights)
                ]
                if all(p is not None for p in prices):
                    out.append(
                        Window(room=code, checkin=checkin, nights=nights, total=sum(prices))
                    )
            checkin += timedelta(days=1)
    return out
