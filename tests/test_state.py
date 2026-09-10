import json

from watch import notify, state


def test_load_missing_returns_default(tmp_path):
    s = state.load(tmp_path / "nope.json")
    assert s == state.default_state()
    assert s["fail_count"] == 0
    assert s["confirmed"] == {}
    assert s["grid"] is None
    assert s["last_checked"] is None


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    s = state.default_state()
    s["fail_count"] = 2
    s["confirmed"]["1BED|2027-08-20|5"] = {"room": "1BED", "price": 1400}
    state.save(p, s)
    assert json.loads(p.read_text(encoding="utf-8"))["fail_count"] == 2
    assert state.load(p) == s


def test_load_corrupt_returns_default(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json", encoding="utf-8")
    assert state.load(p) == state.default_state()


def test_send_posts_to_topic(monkeypatch):
    monkeypatch.setattr(notify.config, "NTFY_SERVER", "https://ntfy.example")
    monkeypatch.setattr(notify.config, "NTFY_TOPIC", "secret-topic")
    monkeypatch.setattr(notify.config, "NTFY_EMAIL", "me@example.com")
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append((url, data, headers))

        class R:
            status_code = 200
            text = "ok"

        return R()

    sent = notify.send("Title here", "body text", click="https://x/y", post=fake_post)
    assert sent is True
    url, data, headers = calls[0]
    assert url == "https://ntfy.example/secret-topic"
    assert data == b"body text"
    assert headers["Title"] == "Title here"
    assert headers["Priority"] == "high"
    assert headers["Click"] == "https://x/y"
    assert headers["Email"] == "me@example.com"
    assert headers["Tags"] == "hotel,bell"


def test_send_without_email_omits_header(monkeypatch):
    monkeypatch.setattr(notify.config, "NTFY_TOPIC", "t")
    monkeypatch.setattr(notify.config, "NTFY_EMAIL", "")
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(headers)

        class R:
            status_code = 200
            text = "ok"

        return R()

    notify.send("t", "b", post=fake_post)
    assert "Email" not in calls[0]
    assert "Click" not in calls[0]


def test_send_with_token_adds_bearer(monkeypatch):
    monkeypatch.setattr(notify.config, "NTFY_TOPIC", "t")
    monkeypatch.setattr(notify.config, "NTFY_EMAIL", "")
    monkeypatch.setattr(notify.config, "NTFY_TOKEN", "tk_abc")
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(headers)

        class R:
            status_code = 200
            text = "ok"

        return R()

    notify.send("t", "b", post=fake_post)
    assert calls[0]["Authorization"] == "Bearer tk_abc"


def test_send_retries_without_email_when_rejected(monkeypatch):
    monkeypatch.setattr(notify.config, "NTFY_TOPIC", "t")
    monkeypatch.setattr(notify.config, "NTFY_EMAIL", "me@example.com")
    monkeypatch.setattr(notify.config, "NTFY_TOKEN", "")
    calls = []

    def fake_post(url, data=None, headers=None, timeout=None):
        calls.append(dict(headers))

        class R:
            status_code = 400 if "Email" in headers else 200
            text = "anonymous email sending is not allowed"

        return R()

    assert notify.send("t", "b", post=fake_post) is True
    assert len(calls) == 2
    assert "Email" in calls[0] and "Email" not in calls[1]
    assert calls[1]["Title"] == "t"


def test_send_without_topic_is_noop(monkeypatch):
    monkeypatch.setattr(notify.config, "NTFY_TOPIC", "")
    called = []
    assert notify.send("t", "b", post=lambda *a, **k: called.append(1)) is False
    assert called == []
