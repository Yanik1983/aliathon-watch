"""End-to-end tests of one poll cycle with fake fetch and fake notifier."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from watch import config
from watch.client import FetchError
from watch.main import run

FIXTURE_HTML = json.loads(
    (Path(__file__).parent / "fixtures" / "avl_15n.json").read_text(encoding="utf-8")
)["html"]

NOW = datetime(2026, 9, 10, 20, 0, tzinfo=timezone.utc)
FIRST = date(2027, 8, 14)


def synth_html(open_nights: dict[str, set[date]], fromd: date, nights: int, avl_rooms=()) -> str:
    """Build a minimal WebHotelier-like fragment for the requested range."""
    dates = [fromd + timedelta(i) for i in range(nights + 1)]  # nights + checkout column
    header = "".join(f'<th scope="col" class="range"><span data-date="{d.isoformat()}">x</span></th>' for d in dates)
    blocks = []
    names = {"1BED": "One Bedroom Apartment", "S1BED": "Superior One Bedroom Apartment", "STD": "Studio"}
    for code, name in names.items():
        opened = open_nights.get(code, set())
        status = "AVL" if code in avl_rooms else "NA"
        cells = []
        for d in dates[:-1]:
            if d in opened:
                cells.append('<td class="range">&euro;300<i class="fa fa-check"></i></td>')
            else:
                cells.append('<td class="noavl"><i class="fa fa-phone"></i></td>')
        cells.append('<td class="">&euro;300</td>')
        blocks.append(
            f'<tr class="room"><td class="name" colspan="2">{name}</td>{header}</tr>'
            f'<tr data-status="{status}" data-price="1" data-rate="1" data-room="{code}">'
            f'<td scope="row" class="spec status" colspan="2">rate</td>{"".join(cells)}</tr>'
        )
    return '<table class="data rmtbl"><tbody>' + "".join(blocks) + "</tbody></table>"


class FakeFetch:
    """Returns the 15-night grid for the range query and, for exact-date
    confirmation queries, marks the room AVL when all its nights are open."""

    def __init__(self, open_nights=None, fail=False):
        self.open_nights = open_nights or {}
        self.fail = fail
        self.calls = []

    def __call__(self, fromd, nights):
        self.calls.append((fromd, nights))
        if self.fail:
            raise FetchError("boom")
        if not self.open_nights:
            return FIXTURE_HTML
        avl = [
            code
            for code, opened in self.open_nights.items()
            if all(fromd + timedelta(i) in opened for i in range(nights))
        ]
        return synth_html(self.open_nights, fromd, nights, avl_rooms=avl)


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def __call__(self, title, body, click=None, priority="high", tags="hotel,bell"):
        self.sent.append({"title": title, "body": body, "click": click, "priority": priority})
        return True


def days(a, b):
    return {date(2027, 8, d) for d in range(a, b + 1)}


def paths(tmp_path):
    return tmp_path / "state.json", tmp_path / "docs" / "index.html"


@pytest.fixture(autouse=True)
def _isolate_history(tmp_path, monkeypatch):
    """Never let tests touch the repo's real history.json."""
    monkeypatch.setattr(config, "HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(config, "SETTINGS_PATH", str(tmp_path / "settings.json"))


def test_fixture_run_no_notification_and_outputs_written(tmp_path):
    sp, pp = paths(tmp_path)
    n = FakeNotifier()
    st = run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert n.sent == []
    assert st["confirmed"] == {}
    assert st["fail_count"] == 0
    assert st["grid"]["rooms"]["1BED"]["nights"]["2027-08-20"] == 280
    assert st["last_checked"] == NOW.isoformat()
    assert sp.exists() and pp.exists()
    assert "No bookable stays" in pp.read_text(encoding="utf-8")


def test_new_window_notifies_once(tmp_path):
    sp, pp = paths(tmp_path)
    f = FakeFetch({"S1BED": days(20, 24)})
    n = FakeNotifier()
    st = run(fetch=f, notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert list(st["confirmed"]) == ["S1BED|2027-08-20|5"]
    entry = st["confirmed"]["S1BED|2027-08-20|5"]
    assert entry["room_name"] == "Superior One Bedroom Apartment"
    assert entry["price"] == 1500
    assert entry["first_seen"] == NOW.isoformat()
    assert "checkin=2027-08-20&nights=5" in entry["url"]
    assert len(n.sent) == 1
    assert "1 bookable stay" in n.sent[0]["title"]
    assert "Superior One Bedroom Apartment" in n.sent[0]["body"]
    assert "Fri 20 Aug" in n.sent[0]["body"] and "5 nights" in n.sent[0]["body"]
    assert n.sent[0]["click"] == entry["url"]
    assert "Bookable now (1)" in pp.read_text(encoding="utf-8")

    # second poll, same availability: no new notification, first_seen preserved
    later = NOW + timedelta(minutes=10)
    st2 = run(fetch=f, notifier=n, state_path=sp, page_path=pp, now=later)
    assert len(n.sent) == 1
    assert st2["confirmed"]["S1BED|2027-08-20|5"]["first_seen"] == NOW.isoformat()


def test_multiple_windows_one_notification(tmp_path):
    sp, pp = paths(tmp_path)
    f = FakeFetch({"1BED": days(14, 19)})  # 6 nights open: 5@14, 5@15, 6@14
    n = FakeNotifier()
    st = run(fetch=f, notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert len(st["confirmed"]) == 3
    assert len(n.sent) == 1
    assert "3 bookable stays" in n.sent[0]["title"]


def test_disappear_then_reappear_notifies_again(tmp_path):
    sp, pp = paths(tmp_path)
    n = FakeNotifier()
    stays = lambda: [m for m in n.sent if "bookable" in m["title"]]  # noqa: E731
    run(fetch=FakeFetch({"1BED": days(20, 24)}), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert len(stays()) == 1
    st = run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert st["confirmed"] == {}
    assert len(stays()) == 1
    run(fetch=FakeFetch({"1BED": days(20, 24)}), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert len(stays()) == 2


def test_unconfirmed_candidate_not_reported(tmp_path):
    """Grid shows nights open but the exact-date query says NA."""
    sp, pp = paths(tmp_path)

    class GridOnly(FakeFetch):
        def __call__(self, fromd, nights):
            return synth_html(self.open_nights, fromd, nights, avl_rooms=())

    n = FakeNotifier()
    st = run(fetch=GridOnly({"1BED": days(20, 24)}), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert st["confirmed"] == {}
    assert n.sent == []


def test_failures_alert_once_at_threshold_and_reset(tmp_path):
    sp, pp = paths(tmp_path)
    n = FakeNotifier()
    bad = FakeFetch(fail=True)
    for i in range(1, 5):
        st = run(fetch=bad, notifier=n, state_path=sp, page_path=pp, now=NOW)
        assert st["fail_count"] == i
    assert len(n.sent) == 1
    assert "failing" in n.sent[0]["title"].lower()
    assert n.sent[0]["priority"] == "default"
    assert "4 consecutive" in pp.read_text(encoding="utf-8")

    st = run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert st["fail_count"] == 0
    assert len(n.sent) == 1


def test_failure_keeps_previous_grid(tmp_path):
    sp, pp = paths(tmp_path)
    n = FakeNotifier()
    run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW)
    st = run(fetch=FakeFetch(fail=True), notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert st["grid"]["rooms"]["1BED"]["nights"]["2027-08-20"] == 280
    assert "One Bedroom Apartment" in pp.read_text(encoding="utf-8")


def test_empty_grid_counts_as_failure(tmp_path):
    sp, pp = paths(tmp_path)
    n = FakeNotifier()
    st = run(fetch=lambda f, k: "<table></table>", notifier=n, state_path=sp, page_path=pp, now=NOW)
    assert st["fail_count"] == 1


def test_history_recorded_on_change_only(tmp_path):
    sp, pp = paths(tmp_path)
    hp = tmp_path / "history.json"
    n = FakeNotifier()
    run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW, history_path=hp)
    h1 = json.loads(hp.read_text(encoding="utf-8"))
    assert len(h1) == 1 and h1[0]["t"] == NOW.isoformat()
    assert h1[0]["rooms"]["1BED"]["nights"]["2027-08-20"] == 280
    run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW + timedelta(hours=1), history_path=hp)
    assert len(json.loads(hp.read_text(encoding="utf-8"))) == 1
    run(fetch=FakeFetch({"1BED": days(20, 24)}), notifier=n, state_path=sp, page_path=pp,
        now=NOW + timedelta(hours=2), history_path=hp)
    assert len(json.loads(hp.read_text(encoding="utf-8"))) == 2
    assert "priceChart" in pp.read_text(encoding="utf-8")


def test_history_kept_on_failure(tmp_path):
    sp, pp = paths(tmp_path)
    hp = tmp_path / "history.json"
    n = FakeNotifier()
    run(fetch=FakeFetch(), notifier=n, state_path=sp, page_path=pp, now=NOW, history_path=hp)
    run(fetch=FakeFetch(fail=True), notifier=n, state_path=sp, page_path=pp, now=NOW, history_path=hp)
    assert len(json.loads(hp.read_text(encoding="utf-8"))) == 1
    assert "priceChart" in pp.read_text(encoding="utf-8")


def test_test_push_card_rendered_when_password_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-secret-topic")
    monkeypatch.setattr(config, "PAGE_PASSWORD", "pw")
    sp, pp = paths(tmp_path)
    run(fetch=FakeFetch(), notifier=FakeNotifier(), state_path=sp, page_path=pp, now=NOW)
    page = pp.read_text(encoding="utf-8")
    assert 'id="testpush"' in page
    assert "my-secret-topic" not in page


def test_test_push_card_absent_without_password(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "my-secret-topic")
    monkeypatch.setattr(config, "PAGE_PASSWORD", "")
    sp, pp = paths(tmp_path)
    run(fetch=FakeFetch(), notifier=FakeNotifier(), state_path=sp, page_path=pp, now=NOW)
    assert 'id="testpush"' not in pp.read_text(encoding="utf-8")


def test_price_change_notifies(tmp_path):
    sp, pp = paths(tmp_path)
    notifier = FakeNotifier()
    before = {"1BED": days(20, 21), "STD": days(20, 22)}
    run(fetch=FakeFetch(before), notifier=notifier, state_path=sp, page_path=pp, now=NOW)
    assert notifier.sent == []  # first snapshot: nothing to compare with
    run(fetch=FakeFetch(before), notifier=notifier, state_path=sp, page_path=pp, now=NOW + timedelta(minutes=10))
    assert notifier.sent == []  # unchanged
    after = {"1BED": days(20, 22), "STD": days(21, 22)}
    run(fetch=FakeFetch(after), notifier=notifier, state_path=sp, page_path=pp, now=NOW + timedelta(minutes=20))
    assert len(notifier.sent) == 1
    n = notifier.sent[0]
    assert n["title"] == "Aliathon: price change"
    assert n["priority"] == "default"
    # STD also changed but is not a watched room, so it is not mentioned.
    assert n["body"] == "One Bedroom Apartment (Rate 1): €300, 1 night opened"


def _write_settings(tmp_path, rooms, lo, hi):
    (tmp_path / "settings.json").write_text(
        json.dumps({"rooms": rooms, "min_nights": lo, "max_nights": hi}), encoding="utf-8"
    )


def test_settings_change_rooms_and_nights(tmp_path):
    sp, pp = paths(tmp_path)
    _write_settings(tmp_path, ["STD"], 3, 3)
    notifier = FakeNotifier()
    fetch = FakeFetch({"STD": days(20, 22), "1BED": days(20, 27)})
    st = run(fetch=fetch, notifier=notifier, state_path=sp, page_path=pp, now=NOW)
    assert list(st["confirmed"]) == ["STD|2027-08-20|3"]
    assert len(notifier.sent) == 1 and "Studio" in notifier.sent[0]["body"]


def test_price_change_only_mentions_selected_rooms(tmp_path):
    sp, pp = paths(tmp_path)
    _write_settings(tmp_path, ["1BED"], 5, 8)
    notifier = FakeNotifier()
    before = {"1BED": days(20, 21), "STD": days(20, 22)}
    run(fetch=FakeFetch(before), notifier=notifier, state_path=sp, page_path=pp, now=NOW)
    after = {"1BED": days(20, 21), "STD": days(21, 22)}
    run(fetch=FakeFetch(after), notifier=notifier, state_path=sp, page_path=pp, now=NOW + timedelta(minutes=10))
    assert notifier.sent == []  # only STD changed
    after2 = {"1BED": days(20, 22), "STD": days(21, 22)}
    run(fetch=FakeFetch(after2), notifier=notifier, state_path=sp, page_path=pp, now=NOW + timedelta(minutes=20))
    assert [n["body"] for n in notifier.sent] == ["One Bedroom Apartment (Rate 1): €300, 1 night opened"]


def test_settings_card_rendered_when_token_password_repo_set(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAGE_PASSWORD", "pw")
    monkeypatch.setattr(config, "SETTINGS_TOKEN", "github_pat_x")
    monkeypatch.setattr(config, "GITHUB_REPOSITORY", "me/repo")
    sp, pp = paths(tmp_path)
    run(fetch=FakeFetch(), notifier=FakeNotifier(), state_path=sp, page_path=pp, now=NOW)
    page = pp.read_text(encoding="utf-8")
    assert 'id="settings"' in page
    assert "github_pat_x" not in page
    assert "me/repo" in page


def test_settings_card_absent_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAGE_PASSWORD", "pw")
    monkeypatch.setattr(config, "SETTINGS_TOKEN", "")
    monkeypatch.setattr(config, "GITHUB_REPOSITORY", "me/repo")
    sp, pp = paths(tmp_path)
    run(fetch=FakeFetch(), notifier=FakeNotifier(), state_path=sp, page_path=pp, now=NOW)
    assert 'id="settings"' not in pp.read_text(encoding="utf-8")
