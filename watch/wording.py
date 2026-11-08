"""Short, readable text for push notifications."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

LIST_LIMIT = 4  # up to this many stays are listed one by one; more are summarised per room


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def date_ranges(days: Iterable[date]) -> str:
    """Compact list of dates: "Sun 15 Aug", "15-24 Aug", "15 Aug, 18-19 Aug"."""
    ds = sorted(set(days))
    runs: list[list[date]] = []
    for d in ds:
        if runs and d - runs[-1][-1] == timedelta(days=1):
            runs[-1].append(d)
        else:
            runs.append([d])
    if len(runs) == 1 and len(runs[0]) == 1:
        return f"{runs[0][0]:%a} {runs[0][0].day} {runs[0][0]:%b}"
    parts = []
    for r in runs:
        a, b = r[0], r[-1]
        if a == b:
            parts.append(f"{a.day} {a:%b}")
        elif a.month == b.month:
            parts.append(f"{a.day}-{b.day} {b:%b}")
        else:
            parts.append(f"{a.day} {a:%b}-{b.day} {b:%b}")
    return ", ".join(parts)


def _checkout(e: dict) -> date:
    return date.fromisoformat(e["checkin"]) + timedelta(days=int(e["nights"]))


def stay_line(e: dict) -> str:
    ci = date.fromisoformat(e["checkin"])
    co = _checkout(e)
    return (
        f"{e['room_name']}: {ci:%a} {ci.day} {ci:%b} -> {co:%a} {co.day} {co:%b} "
        f"({e['nights']} nights), EUR {e['price']:,}"
    )


def _span(values: list[int]) -> str:
    lo, hi = min(values), max(values)
    return f"{lo}" if lo == hi else f"{lo}-{hi}"


def stays_summary(entries: list[dict]) -> list[str]:
    """One line per stay when there are few, otherwise one line per room."""
    if len(entries) <= LIST_LIMIT:
        return [stay_line(e) for e in sorted(entries, key=lambda e: (e["room_name"], e["checkin"], e["nights"]))]
    by_room: dict[str, list[dict]] = {}
    for e in entries:
        by_room.setdefault(e["room_name"], []).append(e)
    lines = []
    for name, es in by_room.items():
        checkins = [date.fromisoformat(e["checkin"]) for e in es]
        lines.append(
            f"{name}: {plural(len(es), 'stay')}, check-in {date_ranges(checkins)}, "
            f"{_span([int(e['nights']) for e in es])} nights, from EUR {min(e['price'] for e in es):,}"
        )
    return lines
