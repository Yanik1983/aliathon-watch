"""User-adjustable notification settings (rooms + nights range), stored in settings.json.

The status page's settings card dispatches the ``settings`` workflow, which runs
``python -m watch.settings`` to validate the inputs and write the file. The poll
reads it on every run and falls back to the defaults in ``config`` when the file is
missing or unusable.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from watch import config

log = logging.getLogger(__name__)

_CODE = re.compile(r"^[A-Z0-9]{1,8}$")


@dataclass(frozen=True)
class Settings:
    rooms: tuple[str, ...]
    min_nights: int
    max_nights: int


def defaults() -> Settings:
    return Settings(tuple(config.TARGET_ROOMS), config.MIN_NIGHTS, config.MAX_NIGHTS)


def validate(
    rooms: Iterable[str], min_nights, max_nights, known_rooms: Iterable[str] = ()
) -> Settings:
    """Normalise and check the inputs; raises ValueError with a human-readable message.

    Room codes are upper-cased, trimmed and de-duplicated. When ``known_rooms`` is
    non-empty every code must be one of them.
    """
    known = tuple(known_rooms)
    codes: list[str] = []
    for raw in rooms:
        code = str(raw).strip().upper()
        if not code or code in codes:
            continue
        if not _CODE.match(code):
            raise ValueError(f"bad room code: {raw!r}")
        if known and code not in known:
            raise ValueError(f"unknown room code: {code} (known: {', '.join(known)})")
        codes.append(code)
    if not codes:
        raise ValueError("select at least one room")
    try:
        lo, hi = int(min_nights), int(max_nights)
    except (TypeError, ValueError) as e:
        raise ValueError(f"nights must be whole numbers: {e}") from e
    if not 1 <= lo <= hi <= config.TOTAL_NIGHTS:
        raise ValueError(f"nights must satisfy 1 <= min <= max <= {config.TOTAL_NIGHTS}")
    return Settings(tuple(codes), lo, hi)


def load(path: str | Path) -> Settings:
    """Settings from ``path``; defaults when the file is missing or invalid."""
    p = Path(path)
    if not p.exists():
        return defaults()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return validate(data["rooms"], data["min_nights"], data["max_nights"])
    except (ValueError, OSError, KeyError, TypeError) as e:
        log.warning("settings unusable (%s); using defaults", e)
        return defaults()


def save(path: str | Path, s: Settings, now: datetime) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "rooms": list(s.rooms),
        "min_nights": s.min_nights,
        "max_nights": s.max_nights,
        "updated": now.isoformat(),
    }
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def known_rooms_from_state(path: str | Path) -> tuple[str, ...]:
    """Room codes of the last fetched grid in state.json, or () if unavailable."""
    p = Path(path)
    if not p.exists():
        return ()
    try:
        grid = json.loads(p.read_text(encoding="utf-8")).get("grid") or {}
        return tuple(grid.get("rooms", {}).keys())
    except (ValueError, OSError, AttributeError):
        return ()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate and write settings.json")
    ap.add_argument("--rooms", required=True, help="comma-separated room codes")
    ap.add_argument("--min", required=True, help="minimum nights")
    ap.add_argument("--max", required=True, help="maximum nights")
    ap.add_argument("--state", default=config.STATE_PATH, help="state.json to take known rooms from")
    ap.add_argument("--out", default=config.SETTINGS_PATH)
    a = ap.parse_args(argv)
    try:
        s = validate(a.rooms.split(","), a.min, a.max, known_rooms_from_state(a.state))
    except ValueError as e:
        print(f"invalid settings: {e}", file=sys.stderr)
        return 1
    save(a.out, s, datetime.now(timezone.utc))
    print(f"settings written: rooms={','.join(s.rooms)} nights={s.min_nights}-{s.max_nights}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
