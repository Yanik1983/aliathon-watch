"""User-adjustable watch settings, stored in settings.json.

The status page's settings card dispatches the ``settings`` workflow with one JSON
document; the workflow runs ``python -m watch.settings --json ...`` to validate it
and write the file. The poll reads the file on every run and falls back to the
defaults in ``config`` for anything missing or unusable.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

from watch import config

log = logging.getLogger(__name__)

_CODE = re.compile(r"^[A-Z0-9]{1,8}$")
_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
PRICE_ALERT_MODES = ("all", "improvements", "off")
MAX_WINDOW_NIGHTS = 30
MAX_GUESTS = 6


@dataclass(frozen=True)
class Settings:
    rooms: tuple[str, ...]
    min_nights: int
    max_nights: int
    first_checkin: date
    last_checkout: date
    adults: int
    children: int
    packages: tuple[str, ...] = ()  # rate names; empty = every package
    price_alerts: str = "all"  # one of PRICE_ALERT_MODES
    max_price: int | None = None  # cap on the total stay price; None = no cap
    updated: datetime | None = None
    client_id: str = ""  # opaque id from the page, lets it see when a save was applied

    @property
    def total_nights(self) -> int:
        return (self.last_checkout - self.first_checkin).days

    def to_dict(self) -> dict:
        return {
            "rooms": list(self.rooms),
            "min_nights": self.min_nights,
            "max_nights": self.max_nights,
            "first_checkin": self.first_checkin.isoformat(),
            "last_checkout": self.last_checkout.isoformat(),
            "adults": self.adults,
            "children": self.children,
            "packages": list(self.packages),
            "price_alerts": self.price_alerts,
            "max_price": self.max_price,
            "updated": self.updated.isoformat() if self.updated else None,
            "client_id": self.client_id,
        }


def defaults() -> Settings:
    return Settings(
        rooms=tuple(config.TARGET_ROOMS),
        min_nights=config.MIN_NIGHTS,
        max_nights=config.MAX_NIGHTS,
        first_checkin=config.FIRST_CHECKIN,
        last_checkout=config.LAST_CHECKOUT,
        adults=config.ADULTS,
        children=config.CHILDREN,
    )


def _int(value, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{name} must be a whole number") from e


def _date(value, name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as e:
        raise ValueError(f"{name} must be a date like 2027-08-14") from e


def _rooms(raw: Iterable[str], known: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(raw, str):
        raw = raw.split(",")
    codes: list[str] = []
    for item in raw:
        code = str(item).strip().upper()
        if not code or code in codes:
            continue
        if not _CODE.match(code):
            raise ValueError(f"bad room code: {item!r}")
        if known and code not in known:
            raise ValueError(f"unknown room code: {code} (known: {', '.join(known)})")
        codes.append(code)
    if not codes:
        raise ValueError("select at least one room")
    return tuple(codes)


def _packages(raw) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [p for p in raw.split(",")]
    out: list[str] = []
    for item in raw:
        name = str(item).strip()
        if not name or name in out:
            continue
        if len(name) > 80 or "\n" in name:
            raise ValueError(f"bad package name: {item!r}")
        out.append(name)
    return tuple(out)


def validate(data: dict, known_rooms: Iterable[str] = ()) -> Settings:
    """Build Settings from a dict (missing keys take defaults); ValueError on bad values."""
    if not isinstance(data, dict):
        raise ValueError("settings must be an object")
    d = defaults()
    known = tuple(known_rooms)

    rooms = _rooms(data.get("rooms", d.rooms), known)
    first = _date(data.get("first_checkin", d.first_checkin), "first_checkin")
    last = _date(data.get("last_checkout", d.last_checkout), "last_checkout")
    window = (last - first).days
    if not 1 <= window <= MAX_WINDOW_NIGHTS:
        raise ValueError(
            f"check-out must be 1 to {MAX_WINDOW_NIGHTS} nights after check-in (got {window})"
        )
    lo = _int(data.get("min_nights", d.min_nights), "min_nights")
    hi = _int(data.get("max_nights", d.max_nights), "max_nights")
    if not 1 <= lo <= hi <= window:
        raise ValueError(f"nights must satisfy 1 <= min <= max <= {window} (the date window)")
    adults = _int(data.get("adults", d.adults), "adults")
    children = _int(data.get("children", d.children), "children")
    if not 1 <= adults <= MAX_GUESTS or not 0 <= children <= MAX_GUESTS:
        raise ValueError(f"adults must be 1-{MAX_GUESTS}, children 0-{MAX_GUESTS}")
    packages = _packages(data.get("packages"))
    mode = str(data.get("price_alerts") or "all").strip().lower()
    if mode not in PRICE_ALERT_MODES:
        raise ValueError(f"price_alerts must be one of {', '.join(PRICE_ALERT_MODES)}")
    raw_max = data.get("max_price")
    max_price = None if raw_max in (None, "", 0, "0") else _int(raw_max, "max_price")
    if max_price is not None and max_price < 1:
        raise ValueError("max_price must be a positive number")
    updated = data.get("updated")
    if isinstance(updated, str) and updated:
        try:
            updated = datetime.fromisoformat(updated)
        except ValueError:
            updated = None
    elif not isinstance(updated, datetime):
        updated = None
    client_id = str(data.get("client_id") or "")
    if client_id and not _CLIENT_ID.match(client_id):
        raise ValueError("bad client_id")
    return Settings(
        rooms=rooms,
        min_nights=lo,
        max_nights=hi,
        first_checkin=first,
        last_checkout=last,
        adults=adults,
        children=children,
        packages=packages,
        price_alerts=mode,
        max_price=max_price,
        updated=updated,
        client_id=client_id,
    )


def load(path: str | Path) -> Settings:
    """Settings from ``path``; defaults when the file is missing or invalid."""
    p = Path(path)
    if not p.exists():
        return defaults()
    try:
        return validate(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError, TypeError) as e:
        log.warning("settings unusable (%s); using defaults", e)
        return defaults()


def save(path: str | Path, s: Settings, now: datetime) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    s = replace(s, updated=now)
    p.write_text(json.dumps(s.to_dict(), indent=2) + "\n", encoding="utf-8")


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


def describe(s: Settings) -> str:
    """One-paragraph human summary, used in pushes."""
    nights = (
        f"{s.min_nights} nights" if s.min_nights == s.max_nights
        else f"{s.min_nights}-{s.max_nights} nights"
    )
    parts = [
        f"Rooms: {', '.join(s.rooms)}",
        f"Stay: {nights}, {s.first_checkin:%d %b %Y} to {s.last_checkout:%d %b %Y}",
        f"Guests: {s.adults} adults, {s.children} children",
        f"Packages: {', '.join(s.packages) if s.packages else 'all'}",
        f"Price alerts: {s.price_alerts}",
        f"Max price: {'EUR ' + format(s.max_price, ',') if s.max_price else 'none'}",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate and write settings.json")
    ap.add_argument("--json", default="{}", help="settings as a JSON object")
    ap.add_argument("--rooms", help="comma-separated room codes (overrides --json)")
    ap.add_argument("--min", help="minimum nights (overrides --json)")
    ap.add_argument("--max", help="maximum nights (overrides --json)")
    ap.add_argument("--state", default=config.STATE_PATH, help="state.json to take known rooms from")
    ap.add_argument("--out", default=config.SETTINGS_PATH)
    a = ap.parse_args(argv)
    try:
        data = json.loads(a.json)
        if not isinstance(data, dict):
            raise ValueError("--json must be an object")
        if a.rooms is not None:
            data["rooms"] = a.rooms
        if a.min is not None:
            data["min_nights"] = a.min
        if a.max is not None:
            data["max_nights"] = a.max
        s = validate(data, known_rooms_from_state(a.state))
    except ValueError as e:
        print(f"invalid settings: {e}", file=sys.stderr)
        return 1
    save(a.out, s, datetime.now(timezone.utc))
    print("settings written:\n" + describe(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
