"""One poll cycle: fetch grid, find + confirm windows, notify, persist, render."""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from watch import config, history as history_mod, notify, pagecrypt, state as state_mod
from watch.client import FetchError, fetch_avl
from watch.confirm import ConfirmedWindow, confirm
from watch.finder import find_windows
from watch.parser import Grid, ParseError, RoomRow, parse_grid
from watch.render import render_page

log = logging.getLogger("watch")

Fetch = Callable[[date, int], str]
Notifier = Callable[..., bool]


def grid_to_json(grid: Grid) -> dict:
    return {
        "dates": [d.isoformat() for d in grid.dates],
        "rooms": {
            code: {
                "name": row.name,
                "status": row.status,
                "nights": {d.isoformat(): p for d, p in row.nights.items()},
            }
            for code, row in grid.rooms.items()
        },
    }


def grid_from_json(data: dict | None) -> Grid | None:
    if not data:
        return None
    return Grid(
        dates=[date.fromisoformat(d) for d in data["dates"]],
        rooms={
            code: RoomRow(
                code=code,
                name=r["name"],
                status=r["status"],
                nights={date.fromisoformat(d): p for d, p in r["nights"].items()},
            )
            for code, r in data["rooms"].items()
        },
    )


def _entry(c: ConfirmedWindow, now: datetime) -> dict:
    return {
        "room": c.window.room,
        "room_name": c.room_name,
        "checkin": c.window.checkin.isoformat(),
        "nights": c.window.nights,
        "price": c.price,
        "url": c.url,
        "first_seen": now.isoformat(),
    }


def _describe(e: dict) -> str:
    ci = date.fromisoformat(e["checkin"])
    co = ci.fromordinal(ci.toordinal() + int(e["nights"]))
    return (
        f"{e['room_name']}: {ci:%a %d %b} -> {co:%a %d %b} "
        f"({e['nights']} nights) EUR {e['price']:,}"
    )


def _finish(
    st: dict, grid: Grid | None, state_path, page_path, now: datetime, history: list[dict]
) -> dict:
    st["last_checked"] = now.isoformat()
    state_mod.save(state_path, st)
    test_push = (
        pagecrypt.encrypt(config.NTFY_TOPIC, config.PAGE_PASSWORD)
        if config.NTFY_TOPIC and config.PAGE_PASSWORD
        else None
    )
    page = render_page(grid, st["confirmed"], now, st["fail_count"], history, test_push=test_push)
    p = Path(page_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(page, encoding="utf-8")
    return st


def run(
    fetch: Fetch = fetch_avl,
    notifier: Notifier = notify.send,
    state_path: str | Path = config.STATE_PATH,
    page_path: str | Path = config.PAGE_PATH,
    now: datetime | None = None,
    history_path: str | Path | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    history_path = history_path or config.HISTORY_PATH
    st = state_mod.load(state_path)
    history = history_mod.load(history_path)

    try:
        grid = parse_grid(fetch(config.FIRST_CHECKIN, config.TOTAL_NIGHTS))
    except (FetchError, ParseError) as e:
        st["fail_count"] = int(st.get("fail_count", 0)) + 1
        log.error("poll failed (%d in a row): %s", st["fail_count"], e)
        if st["fail_count"] == config.FAIL_ALERT_AT:
            notifier(
                "Aliathon watcher failing",
                f"{st['fail_count']} consecutive polls failed. Last error: {e}",
                priority="default",
                tags="warning",
            )
        return _finish(st, grid_from_json(st.get("grid")), state_path, page_path, now, history)

    st["fail_count"] = 0
    st["last_success"] = now.isoformat()
    st["grid"] = grid_to_json(grid)
    if history_mod.append_if_changed(history, grid, now):
        history_mod.save(history_path, history)
        log.info("price history: change recorded (%d snapshots)", len(history))
        if len(history) >= 2:
            lines = history_mod.describe_change(history[-2], history[-1])
            if lines:
                notifier(
                    "Aliathon: price change",
                    "\n".join(lines),
                    click=config.BASE_URL + "/",
                    priority="default",
                    tags="chart_with_upwards_trend",
                )
                log.info("notified about %d price/availability change(s)", len(lines))

    candidates = find_windows(
        grid,
        rooms=config.TARGET_ROOMS,
        min_nights=config.MIN_NIGHTS,
        max_nights=config.MAX_NIGHTS,
        first_checkin=config.FIRST_CHECKIN,
        last_checkout=config.LAST_CHECKOUT,
    )
    log.info("%d candidate window(s) from grid", len(candidates))

    previous: dict = st.get("confirmed") or {}
    confirmed_now: dict = {}
    for w in candidates:
        c = confirm(w, fetch=fetch)
        if c is None:
            log.info("candidate %s not confirmed", w.key)
            continue
        entry = _entry(c, now)
        if w.key in previous:
            entry["first_seen"] = previous[w.key].get("first_seen", entry["first_seen"])
        confirmed_now[w.key] = entry

    new_keys = [k for k in confirmed_now if k not in previous]
    if new_keys:
        n = len(new_keys)
        title = f"Aliathon: {n} bookable stay{'s' if n != 1 else ''}!"
        body = "\n".join(_describe(confirmed_now[k]) for k in new_keys)
        notifier(title, body, click=confirmed_now[new_keys[0]]["url"])
        log.info("notified about %d new window(s)", n)
    gone = [k for k in previous if k not in confirmed_now]
    if gone:
        log.info("%d window(s) no longer available: %s", len(gone), ", ".join(gone))

    st["confirmed"] = confirmed_now
    return _finish(st, grid, state_path, page_path, now, history)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        st = run()
        log.info(
            "done: fail_count=%s confirmed=%d", st["fail_count"], len(st["confirmed"])
        )
    except Exception:  # never fail the workflow; page/state may still be committed
        log.exception("unexpected error in poll")
    return 0


if __name__ == "__main__":
    sys.exit(main())
