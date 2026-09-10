"""Append-only price history: one snapshot per change in the per-night grid."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from watch.parser import Grid

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


def rate_names(history: list[dict]) -> list[str]:
    """All package names seen, in first-seen order."""
    names: list[str] = []
    for snap in history:
        for room in snap.get("rooms", {}).values():
            for rate in _room_rates(room):
                if rate not in names:
                    names.append(rate)
    return names
