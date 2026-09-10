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


def snapshot(grid: Grid, now: datetime) -> dict:
    return {
        "t": now.isoformat(),
        "rooms": {
            code: {
                "name": row.name,
                "nights": {d.isoformat(): p for d, p in row.nights.items()},
            }
            for code, row in grid.rooms.items()
        },
    }


def append_if_changed(history: list[dict], grid: Grid, now: datetime) -> bool:
    """Append a snapshot when prices/availability differ from the last one."""
    snap = snapshot(grid, now)
    if history and history[-1].get("rooms") == snap["rooms"]:
        return False
    history.append(snap)
    return True


def series(history: list[dict]) -> dict[str, dict]:
    """Per room: name plus [timestamp, lowest open-night price or None] points."""
    out: dict[str, dict] = {}
    for snap in history:
        for code, room in snap.get("rooms", {}).items():
            prices = [p for p in room.get("nights", {}).values() if p is not None]
            entry = out.setdefault(code, {"name": room.get("name", code), "points": []})
            entry["points"].append([snap["t"], min(prices) if prices else None])
    return out
