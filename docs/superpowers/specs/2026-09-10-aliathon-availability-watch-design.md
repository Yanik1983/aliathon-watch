# Aliathon Aegean availability watcher — design

Date: 2026-09-10

## Goal

Notify the user (push + email) the moment a bookable stay appears at
Aliathon Aegean (Paphos) matching:

- Room type: One Bedroom Apartment (`1BED`) or Superior One Bedroom Apartment (`S1BED`)
- Stay: 5 to 8 nights, check-in on or after 2027-08-14, check-out on or before 2027-08-29
- Guests: 2 adults, 0 children, 0 infants, 1 room

Also publish a public status page showing the current per-night availability
and any bookable windows.

## Data source

Booking engine: WebHotelier, at `https://aliathonaegean.reserve-online.net/`.

Availability endpoint (discovered from the site's JS bundle):

```
POST https://aliathonaegean.reserve-online.net/avl
Content-Type: application/x-www-form-urlencoded
X-Requested-With: XMLHttpRequest
Accept: application/json, */*
User-Agent: <desktop browser UA>   # CloudFront returns 403 for curl's default UA

fromd=YYYY-MM-DD&nights=N&rooms=1&adults=2&children=0&infants=0
```

Response: JSON `{demand, html, jsonld, price_check}`. `html` is a table:

- `<tr class="room">` then `<td class="name">Room Name</td>` and a `<th><span data-date="YYYY-MM-DD">` header per night.
- Each rate row: `<tr data-status="AVL|NA" data-room="CODE" data-rate="ID" ...>` followed by one `<td>` per night:
  `<td class="noavl">` (night sold out) or `<td class="range">&euro;280...</td>` (night open, price shown). The final `<td class="">` is the check-out column.
- `data-status="AVL"` on a row means the whole requested stay is bookable for that rate. `NA` means not bookable ("Limited availability, please contact us").

A single request with `fromd=2027-08-14&nights=15` returns per-night availability for every room for all nights 14 Aug through 28 Aug 2027 (check-out 29 Aug).

## Architecture

Python 3.11 package `watch/`, run by a GitHub Actions cron workflow. State and the
status page are committed back to the repo; GitHub Pages serves `docs/`.

```
GitHub Actions (cron */10)
  └─ python -m watch.main
       ├─ client.fetch_grid()        POST /avl, 15 nights from 2027-08-14
       ├─ parser.parse_grid(html)    -> Grid {dates, rooms{code: RoomRow}}
       ├─ finder.find_windows(grid)  -> candidate Windows (all nights open)
       ├─ confirm.confirm(window)    POST /avl with exact dates, row status AVL?
       ├─ diff vs state.json         new confirmed windows?
       ├─ notify.send(...)           ntfy topic, Email header for email copy
       ├─ write state.json
       └─ render.write_status_page() -> docs/index.html
  └─ git commit + push if state.json / docs changed
```

### Modules

- `watch/config.py` — constants: base URL, target rooms, date range, night bounds, guests. Reads `NTFY_TOPIC`, `NTFY_EMAIL`, `NTFY_SERVER` from env.
- `watch/client.py` — `fetch_avl(fromd: date, nights: int) -> str` returns the `html` string. Raises `FetchError` on non-200, non-JSON, or missing `html`. Retries once after 5 s.
- `watch/parser.py` — `parse_grid(html) -> Grid`. `Grid.dates: list[date]`; `Grid.rooms: dict[code, RoomRow]`; `RoomRow.name`, `RoomRow.status` (`AVL`/`NA` of the first rate row), `RoomRow.nights: dict[date, int | None]` (price in EUR or None when sold). Pure function.
- `watch/finder.py` — `find_windows(grid, rooms, min_nights, max_nights, first_checkin, last_checkout) -> list[Window]`. `Window(room, checkin, checkout, nights, total_price)`. Pure function. A window qualifies when every night in `[checkin, checkout)` has a price.
- `watch/confirm.py` — `confirm(window) -> ConfirmedWindow | None`. Re-fetches with the exact dates; returns the window with `booking_url` and `price` if the room's rate row has `data-status="AVL"`, else None. Booking URL: `https://aliathonaegean.reserve-online.net/?checkin=YYYY-MM-DD&nights=N&rooms=1&adults=2`.
- `watch/notify.py` — `send(title, body, click_url, priority)`. POSTs to `{NTFY_SERVER}/{NTFY_TOPIC}` with headers `Title`, `Priority`, `Tags`, `Click`, and `Email` when `NTFY_EMAIL` set.
- `watch/state.py` — load/save `state.json`: `{last_checked, fail_count, confirmed: [window keys], grid: {...}}`.
- `watch/render.py` — writes `docs/index.html` from grid + confirmed windows. Static HTML, inline CSS, no JS dependencies. Shows: last check time (UTC and Cyprus time), per-room 15-night strip (green/red cells with price), list of bookable windows with "Book" links, note when none.
- `watch/main.py` — orchestrates; exit code 0 always (failures are recorded, not raised) so the workflow can still commit the page.

### Notification rules

- Notify once per newly confirmed window (key = `room|checkin|nights`). Windows already in `state.confirmed` do not re-notify. A window that disappears is removed from `confirmed`; if it reappears it notifies again.
- One notification per poll, listing all new windows, priority `high`, tags `hotel,bell`, click = booking URL of the first window.
- On fetch/parse failure: increment `fail_count`, keep previous grid. When `fail_count` reaches 3 send one `default` priority alert "watcher failing"; do not repeat until a success resets the counter.
- Never treat an empty parse (zero rooms) as "nothing available"; treat as failure.

### Workflow

`.github/workflows/poll.yml`:

- `on: schedule: cron '*/10 * * * *'` plus `workflow_dispatch`.
- `permissions: contents: write`.
- Steps: checkout, setup-python 3.11, `pip install -r requirements.txt`, `python -m watch.main`, commit `state.json docs/index.html` with `[skip ci]` if changed, push.
- Secrets: `NTFY_TOPIC` (random string), `NTFY_EMAIL`.
- Pages: source = `main` branch, `/docs` folder.

### Testing

- `tests/fixtures/avl_15n.json` — real response captured 2026-09-10.
- `tests/test_parser.py` — dates list, room codes, per-night None/price, row status.
- `tests/test_finder.py` — synthetic grids: none open, one exact 5-night run, a 9-night run yields 5..8 windows at each offset, run outside date bounds ignored, check-out bound respected.
- `tests/test_render.py` — page contains room names, window rows, and "no bookable" message.
- `tests/test_main.py` — diff/notify rules with fake client and fake notifier: first appearance notifies, repeat does not, disappear+reappear notifies, 3 failures alert once.
- Live smoke run locally before first push.

## Out of scope

- Booking automatically.
- Other room types, other guest counts (change `config.py` if needed).
- Price tracking or history.
