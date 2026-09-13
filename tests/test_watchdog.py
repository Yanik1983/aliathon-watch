import json
from datetime import datetime, timedelta, timezone

from watch import watchdog

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def __call__(self, title, body, click=None, priority="high", tags=""):
        self.sent.append({"title": title, "body": body, "priority": priority, "tags": tags})
        return True


def _state(tmp_path, last_checked):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"last_checked": last_checked, "fail_count": 0, "confirmed": {}}), encoding="utf-8")
    return p


def test_recent_poll_is_quiet(tmp_path):
    n = FakeNotifier()
    assert watchdog.check(_state(tmp_path, (NOW - timedelta(minutes=12)).isoformat()), NOW, n) is False
    assert n.sent == []


def test_stale_poll_alerts_with_age(tmp_path):
    n = FakeNotifier()
    assert watchdog.check(_state(tmp_path, (NOW - timedelta(minutes=95)).isoformat()), NOW, n) is True
    assert n.sent[0]["title"] == "Aliathon watcher silent"
    assert "95 min ago" in n.sent[0]["body"]
    assert n.sent[0]["priority"] == "high"


def test_missing_state_alerts(tmp_path):
    n = FakeNotifier()
    assert watchdog.check(tmp_path / "none.json", NOW, n) is True
    assert "No poll has ever completed" in n.sent[0]["body"]


def test_threshold_is_configurable(tmp_path):
    n = FakeNotifier()
    p = _state(tmp_path, (NOW - timedelta(minutes=12)).isoformat())
    assert watchdog.check(p, NOW, n, stale_after=timedelta(minutes=10)) is True
