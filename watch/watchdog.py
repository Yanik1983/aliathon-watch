"""Alert when the poll loop has gone silent.

Run by the ``watchdog`` workflow on a cron. Reads ``state.json`` as committed to
the repo; if the last poll attempt is older than ``STALE_AFTER`` (the loop polls
every 10 minutes), sends one high-priority push per run. The poll job itself
cannot report its own death, so this runs in a separate workflow.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from watch import config, notify, state as state_mod

log = logging.getLogger("watchdog")

STALE_AFTER = timedelta(minutes=30)
CYPRUS = ZoneInfo("Europe/Nicosia")


def check(
    state_path: str | Path = config.STATE_PATH,
    now: datetime | None = None,
    notifier: Callable[..., bool] = notify.send,
    stale_after: timedelta = STALE_AFTER,
) -> bool:
    """Return True when an alert was sent (the watcher looks dead)."""
    now = now or datetime.now(timezone.utc)
    st = state_mod.load(state_path)
    raw = st.get("last_checked")
    last = datetime.fromisoformat(raw) if raw else None
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and now - last < stale_after:
        log.info("watcher alive: last poll %s ago", now - last)
        return False
    if last is None:
        detail = "No poll has ever completed."
    else:
        minutes = int((now - last).total_seconds() // 60)
        detail = f"Last poll {last.astimezone(CYPRUS):%a %d %b %H:%M} Cyprus, {minutes} min ago."
    actions = (
        f"https://github.com/{config.GITHUB_REPOSITORY}/actions"
        if config.GITHUB_REPOSITORY
        else "GitHub Actions"
    )
    log.warning("watcher silent: %s", detail)
    notifier(
        "Aliathon watcher silent",
        f"{detail} The poll loop should run every 10 minutes. Check {actions} and restart it "
        "(Actions > poll > Run workflow).",
        click=actions if actions.startswith("http") else None,
        priority="high",
        tags="skull",
    )
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    check()
    return 0


if __name__ == "__main__":
    sys.exit(main())
