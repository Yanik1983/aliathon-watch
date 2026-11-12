"""One poll cycle: fetch grid, find + confirm windows, notify, persist, render."""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from watch import config, history as history_mod, notify, pagecrypt, state as state_mod
from watch import settings as settings_mod
from watch.wording import plural, stays_summary
from watch.client import FetchError, fetch_avl
from watch.confirm import ConfirmedWindow, confirm
from watch.finder import find_windows
from watch.parser import Grid, ParseError, RoomRow, parse_grid
from watch.render import render_page
from watch.settings import Settings

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


def _finish(
    st: dict,
    grid: Grid | None,
    state_path,
    page_path,
    now: datetime,
    history: list[dict],
    settings: Settings,
) -> dict:
    st["last_checked"] = now.isoformat()
    state_mod.save(state_path, st)
    test_push = (
        pagecrypt.encrypt(config.NTFY_TOPIC, config.PAGE_PASSWORD)
        if config.NTFY_TOPIC and config.PAGE_PASSWORD
        else None
    )
    settings_card = (
        pagecrypt.encrypt(config.SETTINGS_TOKEN, config.PAGE_PASSWORD)
        if config.SETTINGS_TOKEN and config.PAGE_PASSWORD and config.GITHUB_REPOSITORY
        else None
    )
    page = render_page(
        grid,
        st["confirmed"],
        now,
        st["fail_count"],
        history,
        test_push=test_push,
        settings=settings,
        settings_card=settings_card,
        repo=config.GITHUB_REPOSITORY,
    )
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
    settings_path: str | Path | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    history_path = history_path or config.HISTORY_PATH
    st = state_mod.load(state_path)
    history = history_mod.load(history_path)
    settings = settings_mod.load(settings_path or config.SETTINGS_PATH)
    log.info(
        "settings: rooms=%s nights=%d-%d",
        ",".join(settings.rooms), settings.min_nights, settings.max_nights,
    )

    def fetch_for_guests(fromd: date, nights: int) -> str:
        return fetch(fromd, nights, adults=settings.adults, children=settings.children)

    try:
        grid = parse_grid(fetch_for_guests(settings.first_checkin, settings.total_nights))
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
        return _finish(
            st, grid_from_json(st.get("grid")), state_path, page_path, now, history, settings
        )

    st["fail_count"] = 0
    st["last_success"] = now.isoformat()
    st["grid"] = grid_to_json(grid)
    change_title, change_lines = "", []
    if history_mod.append_if_changed(history, grid, now):
        history_mod.save(history_path, history)
        log.info("price history: change recorded (%d snapshots)", len(history))
        if len(history) >= 2:
            change_title, change_lines = history_mod.summarize_change(
                history[-2],
                history[-1],
                rooms=settings.rooms,
                packages=settings.packages,
                mode=settings.price_alerts,
            )

    candidates = find_windows(
        grid,
        rooms=settings.rooms,
        min_nights=settings.min_nights,
        max_nights=settings.max_nights,
        first_checkin=settings.first_checkin,
        last_checkout=settings.last_checkout,
    )
    log.info("%d candidate window(s) from grid", len(candidates))

    previous: dict = st.get("confirmed") or {}
    confirmed_now: dict = {}
    for w in candidates:
        c = confirm(w, fetch=fetch_for_guests, adults=settings.adults, children=settings.children)
        if c is None:
            log.info("candidate %s not confirmed", w.key)
            continue
        if settings.max_price is not None and c.price > settings.max_price:
            log.info("candidate %s costs EUR %s, above the EUR %s cap", w.key, c.price, settings.max_price)
            continue
        entry = _entry(c, now)
        if w.key in previous:
            entry["first_seen"] = previous[w.key].get("first_seen", entry["first_seen"])
        confirmed_now[w.key] = entry

    new_keys = [k for k in confirmed_now if k not in previous]
    gone = [k for k in previous if k not in confirmed_now]
    if gone:
        log.info("%d window(s) no longer available: %s", len(gone), ", ".join(gone))
    _notify_poll(
        notifier,
        [confirmed_now[k] for k in new_keys],
        [previous[k] for k in gone],
        confirmed_now,
        change_title,
        change_lines,
    )

    st["confirmed"] = confirmed_now
    return _finish(st, grid, state_path, page_path, now, history, settings)


def _notify_poll(
    notifier: Notifier,
    new: list[dict],
    gone: list[dict],
    confirmed_now: dict,
    change_title: str,
    change_lines: list[str],
) -> None:
    """At most one push per poll.

    Bookable stays come first (high priority, tap opens the cheapest); stays
    that went away and per-night changes from the same poll are added to that
    one message instead of being sent separately.
    """
    sections: list[list[str]] = []
    if new:
        cheapest = min(new, key=lambda e: e["price"])
        title = f"Aliathon: {plural(len(new), 'bookable stay')}!"
        sections.append(stays_summary(new) + (["Tap to book the cheapest."] if len(new) > 1 else []))
        if gone:
            sections.append([f"No longer bookable: {plural(len(gone), 'stay')}."])
        kwargs: dict = {"click": cheapest["url"]}
    elif gone:
        left = len(confirmed_now)
        title = f"Aliathon: {plural(len(gone), 'stay')} no longer bookable"
        sections.append(stays_summary(gone) + [
            f"Still bookable: {plural(left, 'stay')}, from EUR {min(e['price'] for e in confirmed_now.values()):,}."
            if left
            else "Nothing matching your search is bookable now."
        ])
        kwargs = {"click": config.BASE_URL + "/", "priority": "default", "tags": "x"}
    elif change_lines:
        notifier(
            change_title,
            "\n".join(change_lines),
            click=config.BASE_URL + "/",
            priority="default",
            tags="chart_with_upwards_trend",
        )
        log.info("notified about %d price/availability change(s)", len(change_lines))
        return
    else:
        return
    if change_lines:
        sections.append([f"Night changes ({change_title.removeprefix('Aliathon: ')}):"] + change_lines)
    notifier(title, "\n\n".join("\n".join(sec) for sec in sections), **kwargs)
    log.info("notified: %s", title)


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
