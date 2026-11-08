"""Append-only price history: one snapshot per change in the per-night grid."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from watch.parser import Grid
from watch.wording import date_ranges, plural

log = logging.getLogger(__name__)


def load(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        log.warning("history unreadable (%s); starting fresh", e)
        return []
    return data if isinstance(data, list) else []


def save(path: str | Path, history: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(history, separators=(",", ":")) + "\n", encoding="utf-8")


DEFAULT_RATE = "Standard Rate | Breakfast"


def snapshot(grid: Grid, now: datetime) -> dict:
    rooms = {}
    for code, row in grid.rooms.items():
        rates = row.rates or {DEFAULT_RATE: row.nights}
        rooms[code] = {
            "name": row.name,
            "nights": {d.isoformat(): p for d, p in row.nights.items()},
            "rates": {
                rate: {d.isoformat(): p for d, p in nights.items()}
                for rate, nights in rates.items()
            },
        }
    return {"t": now.isoformat(), "rooms": rooms}


def _room_rates(room: dict) -> dict[str, dict]:
    """Rates of a stored room; old snapshots (before packages) have only nights."""
    return room.get("rates") or {DEFAULT_RATE: room.get("nights", {})}


def append_if_changed(history: list[dict], grid: Grid, now: datetime) -> bool:
    """Append a snapshot when prices/availability differ from the last one."""
    snap = snapshot(grid, now)
    if history and history[-1].get("rooms") == snap["rooms"]:
        return False
    history.append(snap)
    return True


def series(history: list[dict]) -> dict[str, dict]:
    """Per room: name plus, per package, [timestamp, lowest open-night price] points.

    ``points`` keeps the first package (cheapest board) for backwards compatibility.
    """
    out: dict[str, dict] = {}
    for snap in history:
        for code, room in snap.get("rooms", {}).items():
            entry = out.setdefault(code, {"name": room.get("name", code), "points": [], "rates": {}})
            for i, (rate, nights) in enumerate(_room_rates(room).items()):
                prices = [p for p in nights.values() if p is not None]
                point = [snap["t"], min(prices) if prices else None]
                entry["rates"].setdefault(rate, []).append(point)
                if i == 0:
                    entry["points"].append(point)
    return out


def _short_rate(rate: str) -> str:
    """"Standard Rate | Breakfast" -> "Breakfast"; other rate plans keep a hint."""
    if "|" not in rate:
        return rate
    plan, board = (x.strip() for x in rate.split("|", 1))
    if plan.lower().startswith("non refundable"):
        return f"{board}, non-refundable"
    return board


def _lowest(nights: dict) -> int | None:
    prices = [p for p in nights.values() if p is not None]
    return min(prices) if prices else None


def _open_days(rates: dict[str, dict]) -> set[date]:
    return {date.fromisoformat(d) for nights in rates.values() for d, p in nights.items() if p is not None}


def _room_change(name: str, old: dict | None, new: dict, mode: str) -> tuple[str, set[str]] | None:
    """One line describing a room's change and the kinds of change it contains."""
    total = len({d for nights in new.values() for d in nights})
    open_now = _open_days(new)
    cheapest = min(
        ((p, rate) for rate, nights in new.items() if (p := _lowest(nights)) is not None),
        default=None,
    )
    if old is None:  # room (or package) newly listed
        if mode == "improvements" and not open_now:
            return None
        if not open_now:
            return f"{name}: newly listed, fully booked", {"new"}
        return (
            f"{name}: newly listed, {len(open_now)} of {plural(total, 'night')} available, "
            f"from €{cheapest[0]}/night ({_short_rate(cheapest[1])})",
            {"opened"},
        )
    if old == new:
        return None
    open_before = _open_days(old)
    opened, closed = open_now - open_before, open_before - open_now
    drops, rises = [], []
    for rate, nights in new.items():
        before, after = _lowest(old.get(rate, {})), _lowest(nights)
        if before is None or after is None or before == after:
            continue
        (drops if after < before else rises).append(f"{_short_rate(rate)} €{before} → €{after}")
    if mode == "improvements":
        closed, rises = set(), []
    kinds = {k for k, v in (("opened", opened), ("closed", closed), ("down", drops), ("up", rises)) if v}
    if not kinds:
        return None
    parts = []
    if closed:
        parts.append(f"{date_ranges(closed)} sold out" + (f" ({len(closed)} nights)" if len(closed) > 1 else ""))
    if opened:
        parts.append(f"{date_ranges(opened)} now open" + (f" ({len(opened)} nights)" if len(opened) > 1 else ""))
    if drops:
        parts.append("price down: " + ", ".join(drops))
    if rises:
        parts.append("price up: " + ", ".join(rises))
    if not open_now:
        tail = "now fully booked"
    else:
        avail = (
            f"all {total} nights" if len(open_now) == total > 1
            else f"{len(open_now)} of {plural(total, 'night')}"
        )
        tail = f"{avail} available, from €{cheapest[0]}/night ({_short_rate(cheapest[1])})"
    return f"{name}: {'; '.join(parts)}. {tail[0].upper()}{tail[1:]}.", kinds


def summarize_change(
    prev: dict,
    cur: dict,
    rooms: Iterable[str] | None = None,
    packages: Iterable[str] | None = None,
    mode: str = "all",
) -> tuple[str, list[str]]:
    """(headline, one line per changed room) between two snapshots.

    Availability is per room: a night counts as open when any watched package
    has a price for it, so a night that closes in every package is reported
    once, with its date, rather than once per package. Prices compare each
    package's cheapest open night.
    ``rooms`` limits the output to those room codes (``None`` = every room);
    ``packages`` to those rate names (``None`` or empty = every package).
    ``mode``: "all", "improvements" (only price drops and nights that opened), "off".
    """
    if mode == "off":
        return "", []
    wanted = set(rooms) if rooms is not None else None
    wanted_pkgs = set(packages) if packages else None

    def pick(rates: dict) -> dict:
        return {r: n for r, n in rates.items() if wanted_pkgs is None or r in wanted_pkgs}

    lines: list[str] = []
    kinds: set[str] = set()
    for code, room in cur.get("rooms", {}).items():
        if wanted is not None and code not in wanted:
            continue
        new = pick(_room_rates(room))
        if not new:
            continue
        old_room = prev.get("rooms", {}).get(code)
        old = pick(_room_rates(old_room)) if old_room else None
        res = _room_change(room.get("name", code), old or None, new, mode)
        if res:
            lines.append(res[0])
            kinds |= res[1]
    return _headline(kinds), lines


def _headline(kinds: set[str]) -> str:
    avail = ("opened" in kinds, "closed" in kinds)
    price = ("down" in kinds, "up" in kinds)
    a = {(True, False): "nights opened", (False, True): "nights sold out",
         (True, True): "availability changed"}.get(avail)
    p = {(True, False): "price drop", (False, True): "price rise",
         (True, True): "prices changed"}.get(price)
    words = " & ".join(x for x in (a, p) if x) or "listing changed"
    return f"Aliathon: {words}"


def describe_change(prev: dict, cur: dict, **kw) -> list[str]:
    """Lines of :func:`summarize_change` without the headline."""
    return summarize_change(prev, cur, **kw)[1]


def rate_names(history: list[dict]) -> list[str]:
    """All package names seen, in first-seen order."""
    names: list[str] = []
    for snap in history:
        for room in snap.get("rooms", {}).values():
            for rate in _room_rates(room):
                if rate not in names:
                    names.append(rate)
    return names
