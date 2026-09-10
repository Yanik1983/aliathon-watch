# Aliathon Availability Watch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll the WebHotelier booking engine for Aliathon Aegean every 10 minutes, alert via ntfy (push + email) when a 5–8 night stay in a One Bedroom / Superior One Bedroom Apartment becomes bookable between 2027-08-14 and 2027-08-29, and publish a GitHub Pages status page.

**Architecture:** Small Python package `watch/` of pure functions (parser, finder, render) around two I/O edges (HTTP client, ntfy notifier). `main.py` orchestrates one poll, persists `state.json`, and writes `docs/index.html`. A GitHub Actions cron workflow runs it and commits the outputs.

**Tech Stack:** Python 3.11, `requests`, `pytest`. No other dependencies.

**Spec:** `docs/superpowers/specs/2026-09-10-aliathon-availability-watch-design.md`

## Global Constraints

- Python 3.11; only `requests` at runtime, `pytest` for tests.
- Targets: rooms `1BED`, `S1BED`; nights 5..8; check-in >= 2027-08-14; check-out <= 2027-08-29; 1 room, 2 adults, 0 children, 0 infants.
- Endpoint: `POST https://aliathonaegean.reserve-online.net/avl` with desktop browser User-Agent, `X-Requested-With: XMLHttpRequest`, `Accept: application/json, */*`.
- `main.py` always exits 0.
- Never re-notify a window already in `state.confirmed`.
- Empty parse (zero rooms) is a failure, not "nothing available".

## File Structure

```
watch/__init__.py
watch/config.py      constants + env (NTFY_TOPIC, NTFY_EMAIL, NTFY_SERVER)
watch/client.py      fetch_avl(fromd, nights) -> html str ; FetchError
watch/parser.py      parse_grid(html) -> Grid ; dataclasses Grid, RoomRow
watch/finder.py      find_windows(grid, ...) -> list[Window]
watch/confirm.py     confirm(window, fetch=fetch_avl) -> ConfirmedWindow | None ; booking_url()
watch/notify.py      send(title, body, click=None, priority="high", tags="hotel,bell")
watch/state.py       load(path) / save(path, state) ; default_state()
watch/render.py      render_page(grid, confirmed, checked_at, fail_count) -> str
watch/main.py        run(fetch, notifier, state_path, page_path, now) -> State ; __main__
tests/fixtures/avl_15n.json            real 15-night response (2026-09-10)
tests/fixtures/avl_7n_studio_avl.json  real 7-night response with Studio AVL
tests/test_parser.py, test_finder.py, test_confirm.py, test_state.py, test_render.py, test_main.py
requirements.txt, requirements-dev.txt, pytest.ini
.github/workflows/poll.yml
docs/index.html  (generated), state.json (generated)
README.md
```

---

### Task 1: Project scaffold + parser

**Files:** Create `watch/__init__.py`, `watch/config.py`, `watch/parser.py`, `tests/test_parser.py`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`.

**Produces:**
```python
@dataclass
class RoomRow: code: str; name: str; status: str; nights: dict[date, int | None]
@dataclass
class Grid: dates: list[date]; rooms: dict[str, RoomRow]
class ParseError(Exception)
def parse_grid(html: str) -> Grid   # raises ParseError if zero rooms
```

- [ ] Test: fixture `avl_15n.json` -> 15 dates 2027-08-14..2027-08-28; rooms contain `1BED`,`S1BED`,`STD`; `STD.status == "AVL"`; `1BED.status == "NA"`; `1BED.nights[2027-08-20] == 280`; `1BED.nights[2027-08-14] is None`; `1BED.name == "One Bedroom Apartment"`.
- [ ] Test: `parse_grid("<table></table>")` raises `ParseError`.
- [ ] Run, see fail. Implement with `re` (no HTML lib). Run, pass. Commit `feat: parse WebHotelier availability grid`.

### Task 2: Finder

**Files:** Create `watch/finder.py`, `tests/test_finder.py`.

**Produces:**
```python
@dataclass(frozen=True)
class Window: room: str; checkin: date; nights: int; total: int
    @property checkout -> date ; @property key -> str  # "1BED|2027-08-20|5"
def find_windows(grid, rooms, min_nights, max_nights, first_checkin, last_checkout) -> list[Window]
```

- [ ] Tests with synthetic Grid built by helper `grid(open_dates: dict[code, set[date]])`:
  - all sold -> `[]`
  - exactly 14..18 open (5 nights) -> one window checkin 14 nights 5
  - 14..22 open (9 nights) -> windows: n=5 at 14,15,16,17,18; n=6 at 14..17; n=7 at 14..16; n=8 at 14,15 -> 14 total
  - open run ending 28 (check-out 29) allowed; check-out beyond last_checkout not produced
  - real fixture with target rooms -> `[]`
  - `total` = sum of nightly prices
- [ ] Implement, pass, commit `feat: find bookable 5-8 night windows`.

### Task 3: Client + confirm

**Files:** Create `watch/client.py`, `watch/confirm.py`, `tests/test_confirm.py`.

**Produces:**
```python
class FetchError(Exception)
def fetch_avl(fromd: date, nights: int, session=None) -> str  # html; one retry after 5s
def booking_url(checkin: date, nights: int) -> str
@dataclass(frozen=True) class ConfirmedWindow: window: Window; price: int; url: str
def confirm(window: Window, fetch=fetch_avl) -> ConfirmedWindow | None
```

- [ ] Test confirm with fake fetch returning `avl_7n_studio_avl.json` html: window room `STD` checkin 2027-08-14 nights 7 -> ConfirmedWindow with price 1820 and url containing `checkin=2027-08-14&nights=7`; room `1BED` -> None; fetch raising FetchError -> None.
- [ ] Implement; `fetch_avl` posts form, checks status 200, parses JSON, returns `data["html"]`. Commit `feat: http client and window confirmation`.

### Task 4: Notify + state

**Files:** Create `watch/notify.py`, `watch/state.py`, `tests/test_state.py`.

**Produces:**
```python
def send(title, body, click=None, priority="high", tags="hotel,bell", post=requests.post) -> None
   # POST {server}/{topic}, headers Title/Priority/Tags/Click/Email; no-op with log if topic unset
def default_state() -> dict  # {"last_checked": None, "fail_count": 0, "confirmed": {}, "grid": None}
def load(path) -> dict ; def save(path, state) -> None
```
`confirmed` = `{key: {"room","room_name","checkin","nights","price","url","first_seen"}}`; `grid` = `{"dates":[iso], "rooms":{code:{"name","status","nights":{iso: price|null}}}}`.

- [ ] Tests: load missing file -> default; save then load roundtrip; `send` with fake `post` records url + headers incl. `Email` when env set; `send` with no topic does not call post.
- [ ] Implement, commit `feat: ntfy notifier and json state`.

### Task 5: Render

**Files:** Create `watch/render.py`, `tests/test_render.py`.

**Produces:** `render_page(grid: Grid | None, confirmed: dict, checked_at: datetime | None, fail_count: int) -> str`

- [ ] Tests: contains "One Bedroom Apartment"; with empty confirmed contains "No bookable stays"; with one confirmed entry contains its url and "5 nights"; per-night cell for 1BED 2027-08-20 has class `open` and text `280`; `grid=None` renders without exception and shows "no data yet".
- [ ] Implement: inline CSS, table with 15 columns, green `open` / red `sold` cells, target rooms first then the rest, footer with UTC + Cyprus (`Europe/Nicosia` via `zoneinfo`) times, auto-refresh meta 300s. Commit `feat: static status page renderer`.

### Task 6: Main orchestration

**Files:** Create `watch/main.py`, `tests/test_main.py`.

**Produces:** `run(fetch, notifier, state_path, page_path, now) -> dict` and `if __name__ == "__main__": run(...)` with real deps.

Logic: state=load; try grid=parse(fetch(FIRST_CHECKIN, TOTAL_NIGHTS)) except -> fail_count+=1, if ==3 notifier("Aliathon watcher failing", ...), save, render, return. On success fail_count=0; windows=find_windows; confirmed_now={}; for w in windows: c=confirm(w, fetch) -> add. new = keys in confirmed_now not in state.confirmed. If new: one notification: title "Aliathon: N bookable stay(s)!", body lines "Superior One Bedroom Apartment: Fri 20 Aug -> Wed 25 Aug (5 nights) EUR 1450", click first url. state.confirmed = confirmed_now (preserve first_seen for existing). Save state, render page.

- [ ] Tests with fake fetch (returns fixture or synthetic html built by helper) and recording notifier:
  - fixture: no notification, state.grid populated, page written
  - synthetic open run: notification sent once; second run no notification
  - window disappears then reappears: notified again
  - fetch raises 3 times: exactly one failure alert; 4th failure no alert; success resets
- [ ] Implement, commit `feat: poll orchestration`.

### Task 7: Workflow, README, live smoke

**Files:** Create `.github/workflows/poll.yml`, `README.md`.

- [ ] Workflow: schedule `*/10 * * * *`, `workflow_dispatch`, `permissions: contents: write`, checkout, setup-python 3.11 with pip cache, install, `python -m watch.main` with env `NTFY_TOPIC`, `NTFY_EMAIL`, `NTFY_SERVER` from secrets/vars, then commit `state.json docs/index.html` as `github-actions[bot]` with message `chore: poll <date> [skip ci]` and push only if `git status --porcelain` non-empty; `concurrency: poll` to avoid overlap.
- [ ] README: what it does, setup (secrets, Pages), local run.
- [ ] Local smoke: `python -m watch.main` with no topic writes state.json and docs/index.html.
- [ ] Commit `feat: github actions poller and docs`.

### Task 8: Deploy

- [ ] `gh repo create aliathon-watch --public --source . --push`
- [ ] Generate topic `aliathon-<16 random hex>`; `gh secret set NTFY_TOPIC`, `gh secret set NTFY_EMAIL`.
- [ ] Enable Pages: `gh api -X POST repos/{owner}/{repo}/pages -f build_type=legacy -f source[branch]=main -f source[path]=/docs`.
- [ ] `gh workflow run poll.yml`; verify run green and page live.
- [ ] Send test ntfy message to topic so user can verify phone subscription.
