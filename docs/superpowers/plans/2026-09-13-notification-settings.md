# Notification Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user pick watched room types and the stay-length range from a password-gated card on the status page; the choice drives both bookable-stay and price-change notifications.

**Architecture:** The page dispatches the new `settings.yml` workflow through the GitHub API with a fine-grained PAT that is embedded encrypted (existing `pagecrypt`). The workflow validates and commits `settings.json`; the poll loop rebases onto origin every iteration and `watch.main` reads the file through a new `watch/settings.py` module (defaults from `config.py`).

**Tech Stack:** Python 3.11, `requests`, `cryptography`, `pytest`; GitHub Actions; vanilla JS + WebCrypto in the page.

**Spec:** `docs/superpowers/specs/2026-09-13-notification-settings-design.md`

## Global Constraints

- No new runtime dependencies.
- `settings.json` schema: `{"rooms": [..], "min_nights": int, "max_nights": int, "updated": iso}`.
- Validation: at least one room; each code matches `^[A-Z0-9]{1,8}$` and, when known rooms are given, is one of them; `1 <= min <= max <= config.TOTAL_NIGHTS` (15).
- Any settings problem falls back to `config.TARGET_ROOMS`, `config.MIN_NIGHTS`, `config.MAX_NIGHTS` with a warning; `main.py` still always exits 0.
- PAT secret name `SETTINGS_TOKEN`; only Actions: read/write on this repo.
- The settings card renders only when `PAGE_PASSWORD`, `SETTINGS_TOKEN` and `GITHUB_REPOSITORY` are set.
- Commit after every task; run `pytest -q` before each commit.

## File Structure

```
watch/settings.py          Settings dataclass, defaults/validate/load/save, CLI (python -m watch.settings)
watch/config.py            + SETTINGS_PATH, SETTINGS_TOKEN, GITHUB_REPOSITORY
watch/history.py           describe_change(prev, cur, rooms=None)
watch/main.py              load settings; pass to find_windows, describe_change, render_page; encrypt token blob
watch/render.py            settings-aware text/highlighting; shared decrypt script; _settings_section
.github/workflows/settings.yml   workflow_dispatch -> write settings.json, commit, push, confirm push
.github/workflows/poll.yml       rebase first each iteration; SETTINGS_TOKEN env
README.md                  setup steps + behaviour
tests/test_settings.py, tests/test_history.py, tests/test_main.py, tests/test_render.py
```

---

### Task 1: `watch/settings.py` with validation, load/save, CLI

**Files:**
- Create: `watch/settings.py`
- Modify: `watch/config.py` (add `SETTINGS_PATH = "settings.json"`)
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `Settings(rooms: tuple[str, ...], min_nights: int, max_nights: int)`, `defaults()`, `validate(rooms, min_nights, max_nights, known_rooms=())`, `load(path) -> Settings`, `save(path, settings, now)`, `main(argv) -> int`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings.py
import json
from datetime import datetime, timezone

import pytest

from watch import config, settings

NOW = datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc)


def test_defaults_match_config():
    s = settings.defaults()
    assert s.rooms == tuple(config.TARGET_ROOMS)
    assert (s.min_nights, s.max_nights) == (config.MIN_NIGHTS, config.MAX_NIGHTS)


def test_load_missing_file_gives_defaults(tmp_path):
    assert settings.load(tmp_path / "settings.json") == settings.defaults()


def test_load_corrupt_file_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert settings.load(p) == settings.defaults()


def test_load_invalid_values_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"rooms": [], "min_nights": 5, "max_nights": 8}), encoding="utf-8")
    assert settings.load(p) == settings.defaults()


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = settings.Settings(rooms=("1BSU", "2B"), min_nights=3, max_nights=10)
    settings.save(p, s, NOW)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"rooms": ["1BSU", "2B"], "min_nights": 3, "max_nights": 10, "updated": NOW.isoformat()}
    assert settings.load(p) == s


@pytest.mark.parametrize(
    "rooms,lo,hi,known",
    [
        ((), 5, 8, ()),
        (("1BED",), 0, 8, ()),
        (("1BED",), 6, 5, ()),
        (("1BED",), 5, 16, ()),
        (("bad code",), 5, 8, ()),
        (("XYZ",), 5, 8, ("1BED", "S1BED")),
    ],
)
def test_validate_rejects(rooms, lo, hi, known):
    with pytest.raises(ValueError):
        settings.validate(rooms, lo, hi, known)


def test_validate_normalises_and_dedupes():
    s = settings.validate(["s1bed", " 1BED ", "1BED"], "5", "8", ("1BED", "S1BED"))
    assert s == settings.Settings(rooms=("S1BED", "1BED"), min_nights=5, max_nights=8)


def test_cli_writes_file_using_state_rooms(tmp_path, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"grid": {"dates": [], "rooms": {"1BED": {"name": "x", "status": "NA", "nights": {}}}}}), encoding="utf-8")
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "1BED", "--min", "5", "--max", "7", "--state", str(state), "--out", str(out)])
    assert rc == 0
    assert settings.load(out) == settings.Settings(rooms=("1BED",), min_nights=5, max_nights=7)


def test_cli_rejects_unknown_room_and_writes_nothing(tmp_path, capsys):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"grid": {"dates": [], "rooms": {"1BED": {"name": "x", "status": "NA", "nights": {}}}}}), encoding="utf-8")
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "STD", "--min", "5", "--max", "7", "--state", str(state), "--out", str(out)])
    assert rc == 1
    assert not out.exists()
    assert "STD" in capsys.readouterr().err


def test_cli_without_state_accepts_any_wellformed_code(tmp_path):
    out = tmp_path / "settings.json"
    rc = settings.main(["--rooms", "SW1B,2BSU", "--min", "1", "--max", "15", "--state", str(tmp_path / "none.json"), "--out", str(out)])
    assert rc == 0
    assert settings.load(out).rooms == ("SW1B", "2BSU")
```

- [ ] **Step 2: Run** `pytest tests/test_settings.py -q` — expect ImportError.

- [ ] **Step 3: Implement**

```python
# watch/settings.py
"""User-adjustable notification settings (rooms + nights range), stored in settings.json."""
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


def validate(rooms: Iterable[str], min_nights, max_nights, known_rooms: Iterable[str] = ()) -> Settings:
    """Normalise and check; raises ValueError with a human message."""
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
    data = {"rooms": list(s.rooms), "min_nights": s.min_nights, "max_nights": s.max_nights, "updated": now.isoformat()}
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def known_rooms_from_state(path: str | Path) -> tuple[str, ...]:
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
    ap.add_argument("--min", required=True)
    ap.add_argument("--max", required=True)
    ap.add_argument("--state", default=config.STATE_PATH)
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
```

Add to `watch/config.py` after `HISTORY_PATH`: `SETTINGS_PATH = "settings.json"`.

- [ ] **Step 4: Run** `pytest -q` — all pass.
- [ ] **Step 5: Commit** `feat: settings module with validation and CLI`.

---

### Task 2: Room filter in `describe_change`

**Files:** Modify `watch/history.py` (`describe_change`), Test `tests/test_history.py`.

**Interfaces:** `describe_change(prev, cur, rooms: Iterable[str] | None = None)`; `None` = all rooms.

- [ ] **Step 1: Test**

```python
def test_describe_change_filters_rooms():
    prev = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 295}),
                  "STD": _room("Studio", {"2027-08-20": 260})})
    cur = _snap({"1BED": _room("One Bedroom Apartment", {"2027-08-20": 310}),
                 "STD": _room("Studio", {"2027-08-20": 270})})
    assert history.describe_change(prev, cur, rooms=["1BED"]) == ["One Bedroom Apartment (Breakfast): €295 → €310"]
    assert history.describe_change(prev, cur, rooms=["2B"]) == []
```

- [ ] **Step 2:** Run, expect TypeError. **Step 3:** add `rooms` param; `wanted = set(rooms) if rooms is not None else None`; `if wanted is not None and code not in wanted: continue` at top of the room loop. **Step 4:** `pytest -q`. **Step 5:** Commit `feat: describe_change can filter by room`.

---

### Task 3: `watch.main` uses settings

**Files:** Modify `watch/main.py`, `watch/config.py` (`SETTINGS_TOKEN`, `GITHUB_REPOSITORY` env), Test `tests/test_main.py`.

**Interfaces:**
- `run(..., settings_path: str | Path | None = None)`; loads `settings.load(settings_path or config.SETTINGS_PATH)`.
- Calls `render_page(grid, confirmed, now, fail_count, history, test_push=..., settings=settings, settings_card=blob)` where `blob = pagecrypt.encrypt(config.SETTINGS_TOKEN, config.PAGE_PASSWORD)` when `SETTINGS_TOKEN and PAGE_PASSWORD and GITHUB_REPOSITORY` else `None`.

- [ ] **Step 1: Tests** (in `tests/test_main.py`; `_isolate_history` fixture also sets `config.SETTINGS_PATH` to `tmp_path / "settings.json"`)

```python
def _write_settings(tmp_path, rooms, lo, hi):
    (tmp_path / "settings.json").write_text(
        json.dumps({"rooms": rooms, "min_nights": lo, "max_nights": hi}), encoding="utf-8")


def test_settings_change_rooms_and_nights(tmp_path):
    sp, pp = paths(tmp_path)
    _write_settings(tmp_path, ["STD"], 3, 3)
    notifier = FakeNotifier()
    st = run(fetch=FakeFetch({"STD": days(20, 22), "1BED": days(20, 27)}), notifier=notifier, state_path=sp, page_path=pp, now=NOW)
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
    assert 'id="settings"' in page and "github_pat_x" not in page and "me/repo" in page


def test_settings_card_absent_without_token(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAGE_PASSWORD", "pw")
    monkeypatch.setattr(config, "SETTINGS_TOKEN", "")
    sp, pp = paths(tmp_path)
    run(fetch=FakeFetch(), notifier=FakeNotifier(), state_path=sp, page_path=pp, now=NOW)
    assert 'id="settings"' not in pp.read_text(encoding="utf-8")
```

- [ ] **Step 2:** run, fail. **Step 3:** implement per Interfaces (main + config + render signature stub accepting the new kwargs — Task 4 fills in the rendering). **Step 4:** `pytest -q`. **Step 5:** Commit `feat: poll honours settings.json for rooms and nights`.

---

### Task 4: Page renders settings and the settings card

**Files:** Modify `watch/render.py`, Test `tests/test_render.py`.

**Interfaces:**
- `render_page(grid, confirmed, checked_at, fail_count, history=None, test_push=None, settings: Settings | None = None, settings_card: dict | None = None)`; `settings=None` → `settings_mod.defaults()`.
- `_watch_text(settings, grid)`: "Watching for 5–8 nights in One Bedroom Apartment or Superior One Bedroom Apartment, check-in from Sat 14 Aug 2027, check-out by Sun 29 Aug 2027." (names from grid, code when unknown).
- `_settings_section(grid, settings, blob)`: `<section class="card" id="settings">` with `<input type="checkbox" name="room" value="CODE" checked>` per room (grid order, target first; settings rooms missing from grid appended), `<input type="number" id="st-min" min="1" max="15" value=..>`, `st-max`, password `st-pw`, remember `st-remember`, button `st-save`, message `st-msg`. JS decrypts with shared `aliathonDecrypt`, validates client-side (same rules), POSTs to `https://api.github.com/repos/{repo}/actions/workflows/settings.yml/dispatches` with headers `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `X-GitHub-Api-Version: 2022-11-28`, body `{"ref":"main","inputs":{"rooms":"A,B","min_nights":"5","max_nights":"8"}}`. 204 → "Saved. The watcher picks it up within 10 minutes."
- Shared script `_DECRYPT_JS` defined once before the cards: `window.aliathonDecrypt = function(blob, password) {...}` (moved from the test push card).

- [ ] **Step 1: Tests**

```python
from watch.settings import Settings

def test_page_text_and_highlight_follow_settings():
    page = render_page(GRID, {}, NOW, 0, settings=Settings(("STD",), 3, 4))
    assert "Watching for 3–4 nights in Studio" in page
    assert re.search(r'<tr class="target"><td class="room">Studio</td>', page)
    assert page.index("Studio") < page.index("One Bedroom Apartment")


def test_settings_card_lists_grid_rooms_with_checked_state():
    blob = {"salt": "a", "iv": "b", "ct": "c", "iter": 1}
    page = render_page(GRID, {}, NOW, 0, settings=Settings(("1BED",), 5, 8), settings_card=blob, repo="me/repo")
    assert 'id="settings"' in page
    assert re.search(r'name="room" value="1BED" checked', page)
    assert re.search(r'name="room" value="STD"(?! checked)', page)
    assert 'id="st-min" min="1" max="15" value="5"' in page
    assert "api.github.com/repos/me/repo/actions/workflows/settings.yml/dispatches" in page


def test_no_settings_card_without_blob():
    assert 'id="settings"' not in render_page(GRID, {}, NOW, 0)
```

(`render_page` gains `repo: str = ""` too; `main` passes `config.GITHUB_REPOSITORY`.)

- [ ] **Step 2:** run, fail. **Step 3:** implement (replace every `config.TARGET_ROOMS` in render with `settings.rooms`; `_windows_section(confirmed, settings, grid)`; `_grid_section(grid, settings)`; `_history_section(history, now, settings)`; add CSS for `#settings` reusing `#testpush` rules via a shared selector `.gated`). **Step 4:** `pytest -q`. **Step 5:** Commit `feat: settings card and settings-aware status page`.

---

### Task 5: Workflows

**Files:** Create `.github/workflows/settings.yml`; Modify `.github/workflows/poll.yml`.

- [ ] **Step 1: settings.yml**

```yaml
name: settings

on:
  workflow_dispatch:
    inputs:
      rooms:
        description: "Comma-separated room codes"
        required: true
        type: string
      min_nights:
        description: "Minimum nights"
        required: true
        type: string
      max_nights:
        description: "Maximum nights"
        required: true
        type: string

permissions:
  contents: write

concurrency:
  group: settings

jobs:
  save:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - name: Validate and write settings.json
        run: python -m watch.settings --rooms "${{ inputs.rooms }}" --min "${{ inputs.min_nights }}" --max "${{ inputs.max_nights }}"
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add settings.json
          if git diff --cached --quiet; then echo "no change"; exit 0; fi
          git commit -q -m "chore: settings $(date -u +'%Y-%m-%d %H:%M UTC') [skip ci]"
          for i in 1 2 3; do
            git push -q origin HEAD:main && break
            git pull -q --rebase -X ours origin main || { git rebase --abort; exit 1; }
          done
      - name: Confirmation push
        if: success()
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
          NTFY_TOKEN: ${{ secrets.NTFY_TOKEN }}
          NTFY_SERVER: ${{ vars.NTFY_SERVER }}
        run: |
          python - <<'EOF'
          from watch import notify, settings
          s = settings.load("settings.json")
          notify.send("Aliathon: settings updated",
                      f"Rooms: {', '.join(s.rooms)}\nStay: {s.min_nights}-{s.max_nights} nights",
                      priority="low", tags="gear")
          EOF
```

Note: `-X ours` during a rebase keeps the commit being replayed (our settings.json) on conflict.

- [ ] **Step 2: poll.yml** — add `SETTINGS_TOKEN: ${{ secrets.SETTINGS_TOKEN }}` to the env of "Poll loop"; restructure the loop body:

```bash
n=$((n + 1))
echo "::group::poll #$n $(date -u +'%Y-%m-%d %H:%M UTC')"
# Pick up settings.json (and anything else) committed meanwhile.
git fetch -q origin main
if [ "$(git rev-list --count HEAD..origin/main)" -gt 0 ]; then
  local_head=$(git rev-parse HEAD)
  if ! git pull -q --rebase -X theirs origin main; then
    git rebase --abort || true
    git reset -q --hard origin/main
    git checkout "$local_head" -- state.json history.json docs/index.html 2>/dev/null || true
    git commit -q -m "chore: poll $(date -u +'%Y-%m-%d %H:%M UTC') [skip ci]" || true
  fi
fi
python -m watch.main || echo "poll exited non-zero"
git add state.json history.json docs/index.html
if git diff --cached --quiet; then echo "no changes"; else git commit -q -m "chore: poll $(date -u +'%Y-%m-%d %H:%M UTC') [skip ci]"; fi
if [ "$(git rev-list --count origin/main..HEAD)" -gt 0 ]; then
  git push -q origin HEAD:main || echo "push failed; will retry next iteration"
fi
echo "::endgroup::"
```

- [ ] **Step 3:** `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/poll.yml','.github/workflows/settings.yml']]"` (or `pip install pyyaml` in scratch) — both parse. **Step 4:** Commit `ci: settings workflow; poll loop rebases before each poll`.

---

### Task 6: README, memory, verification

- [ ] README: "Watching for" paragraph → says defaults and that the page card overrides; Setup adds `SETTINGS_TOKEN` (fine-grained PAT, repo `aliathon-watch` only, Actions: Read and write); "Changing the search" section mentions the card for rooms/nights and `config.py` for dates/guests.
- [ ] Update memory file: PAGE_PASSWORD set on 2026-09-11; SETTINGS_TOKEN pending.
- [ ] `pytest -q` green; `python -m watch.main` local dry run renders page with card absent (no token) and no crash.
- [ ] Commit `docs: settings card setup`; push; tell the user the one manual step.
