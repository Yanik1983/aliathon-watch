# Notification settings from the status page — design

Date: 2026-09-13

## Goal

Let the user choose, from the public status page, which room types trigger
notifications and how long a stay (in nights) must be, without editing
`watch/config.py` or touching GitHub settings. The choice applies to both
notification kinds: bookable-stay alerts (search rooms and nights range) and
price-change pushes (only selected rooms are mentioned).

## Constraints

- The status page is static GitHub Pages; it cannot write to the repo itself.
- Any credential embedded in the page is public. It must be encrypted with
  `PAGE_PASSWORD` (existing `watch/pagecrypt.py` scheme: PBKDF2-HMAC-SHA256,
  600k iterations, AES-256-GCM) and, if cracked, must not allow code changes.
- The poll job is one long loop; settings must reach it without restarting it.
- No new Python runtime dependencies.

## Architecture

```
status page (browser)
  card: room checkboxes + min/max nights + password
  -> decrypt SETTINGS_TOKEN blob with password (WebCrypto)
  -> POST https://api.github.com/repos/<owner>/<repo>/actions/workflows/settings.yml/dispatches
     {ref: "main", inputs: {rooms, min_nights, max_nights}}

settings.yml workflow (workflow_dispatch)
  -> python -m watch.settings --rooms ... --min ... --max ...   (validate + write settings.json)
  -> git commit "chore: settings ... [skip ci]" ; push (pull --rebase on conflict)
  -> ntfy push "Aliathon: settings updated" (confirmation)

poll.yml loop (unchanged cadence)
  -> every iteration: fetch + rebase onto origin/main FIRST, then python -m watch.main
  -> watch.main loads settings.json (fallback: config defaults), uses it for
     find_windows, price-change filter, page rendering
```

### Credential

`SETTINGS_TOKEN` repository secret: a GitHub fine-grained personal access token
restricted to the `aliathon-watch` repository with the single permission
**Actions: Read and write**. That permission only allows triggering and
reading workflows; it cannot push code or read secrets. The poll workflow
passes it to `watch.main`, which embeds it in the page encrypted with
`PAGE_PASSWORD` exactly like the ntfy topic. The card renders only when
`PAGE_PASSWORD`, `SETTINGS_TOKEN` and `GITHUB_REPOSITORY` are all set.

Rejected: Contents API `PUT` from the browser (needs Contents: write, which is
a code-push capability if the blob is ever cracked, and skips server-side
validation).

### settings.json (repo root)

```json
{"rooms": ["1BED", "S1BED"], "min_nights": 5, "max_nights": 8, "updated": "2026-09-13T10:00:00+00:00"}
```

Absent, unreadable or invalid file: `watch.settings.load()` logs a warning and
returns defaults from `config.py` (`TARGET_ROOMS`, `MIN_NIGHTS`, `MAX_NIGHTS`).

### watch/settings.py

- `@dataclass(frozen=True) Settings(rooms: tuple[str, ...], min_nights: int, max_nights: int)`
- `defaults() -> Settings` from `config`.
- `validate(rooms, min_nights, max_nights, known_rooms) -> Settings`; raises
  `ValueError` when: no rooms; a room code is not in `known_rooms` (when
  `known_rooms` is non-empty) or does not match `^[A-Z0-9]{1,8}$`; nights not
  `1 <= min <= max <= config.TOTAL_NIGHTS`.
- `load(path) -> Settings` (defaults on any problem).
- `save(path, settings, now)`.
- `main(argv)` CLI: `--rooms 1BED,S1BED --min 5 --max 8 [--state state.json] [--out settings.json]`.
  Known rooms come from the grid in `--state` when it exists. Exit 1 with a
  message on invalid input, so the workflow fails visibly.

### Effects in watch.main

- `find_windows(rooms=settings.rooms, min_nights=..., max_nights=...)`.
- Price-change push: `history.describe_change(prev, cur, rooms=settings.rooms)`
  only emits lines for listed rooms; if no line survives, no push.
- `render_page(..., settings=settings, settings_card=blob_or_None)`.

### Page

- "Watching for" sentence and target highlighting (grid rows, chart line
  weight, row order) use `settings` instead of `config.TARGET_ROOMS` and the
  hardcoded "5–8 nights" text.
- New card `#settings` "Notification settings": one checkbox per room in the
  current grid (checked = selected; rooms in settings but absent from the grid
  are still listed), `min`/`max` number inputs (1..15), password field,
  "remember on this device" checkbox, Save button, status line.
- Shared decrypt helper script emitted once (`aliathonDecrypt(blob, password)`),
  used by both the test push card and the settings card.
- After a 204 from GitHub: "Saved. The watcher picks it up within 10 minutes."
  Any other status: shown with the response text. Wrong password: same handling
  as the test push card (clear remembered value).
- Remembered value: the decrypted token in `localStorage` under its own key,
  matching the test push card behaviour.

### Workflows

- `.github/workflows/settings.yml`: `workflow_dispatch` with string inputs
  `rooms`, `min_nights`, `max_nights`; `permissions: contents: write`;
  `concurrency: settings` (separate from `poll`, so it never cancels the poll
  loop). Steps: checkout, setup-python, `pip install -r requirements.txt`,
  run `python -m watch.settings`, commit + push (retry once after
  `git pull --rebase`), then `python -c` call to `watch.notify.send` with a
  one-line summary (only when `NTFY_TOPIC` is set).
- `.github/workflows/poll.yml`: move the fetch/rebase step to the top of each
  iteration and make it unconditional (`git fetch`; if origin/main moved,
  `git pull --rebase -X theirs`, with the existing reset fallback). After the
  poll commit, push as today. Add `SETTINGS_TOKEN` to the step env. The
  `push` trigger paths stay unchanged, so a settings commit does not restart
  the loop.

## Error handling

- Invalid inputs never reach `settings.json`: the CLI rejects them, the
  workflow run fails, and the page shows nothing new (the user sees the
  failure only in Actions; acceptable because the page validates the same
  rules client-side before sending).
- A settings change that deselects a room drops its confirmed windows from
  `state.confirmed` on the next poll (logged as "no longer available"). If it
  is re-selected later, the stay is announced again. Acceptable.

## Testing

- `tests/test_settings.py`: defaults when file absent/corrupt/invalid;
  validate accepts/rejects; CLI writes file and exits 1 on bad input.
- `tests/test_main.py`: settings file changes the rooms searched and the
  nights range; price-change push omits unselected rooms and is skipped when
  only unselected rooms changed.
- `tests/test_history.py`: `describe_change(rooms=...)` filter.
- `tests/test_render.py`: card present with blob, absent without; page text
  reflects settings; checkbox for every grid room, checked state right.

## Setup (README)

1. GitHub > Settings > Developer settings > Personal access tokens >
   Fine-grained tokens > Generate: repository access = only `aliathon-watch`,
   Repository permissions: Actions = Read and write. Expiry: choose long.
2. `gh secret set SETTINGS_TOKEN` with the token.
3. Push once (or run the poll workflow) so the page renders the card.

## Addendum (2026-09-13, later the same day): items 1–6

Approved after the first version went live.

1. **Dead-watcher alert.** `watch/watchdog.py` + `.github/workflows/watchdog.yml`
   (hourly cron, `workflow_dispatch`). If `state.json` shows no poll attempt in
   30 minutes: high-priority push "Aliathon watcher silent" with the age and a
   link to Actions. Optional `HEALTHCHECK_URL` secret: the poll loop pings it
   after every poll for an external dead-man switch.
2. **Instant apply.** The `settings` workflow runs `python -m watch.main` after
   writing `settings.json` and commits state, history and page too. The card
   has a "Poll now" button that dispatches the `poll` workflow.
3. **Gone push.** Stays present in the previous poll but not confirmed now
   trigger "Aliathon: N stay(s) no longer bookable" (default priority).
4. **Price-change control.** Settings gain `packages` (rate names; empty = all)
   and `price_alerts` (`all` | `improvements` | `off`). `describe_change`
   takes both; "improvements" keeps lines where the lowest price fell (or went
   from sold out to priced) or nights opened.
5. **Applied state.** Card shows a "Current: …, applied HH:MM Cyprus" line.
   Each save carries a random `client_id`; the page embeds the applied one in
   `data-client-id`. After a save the browser keeps the id in `localStorage`
   and reloads every 30 s until the page carries it.
6. **More knobs.** `first_checkin`, `last_checkout` (window 1–30 nights),
   `adults` (1–6), `children` (0–6), `max_price` (total stay cap, null = none).
   The grid fetch, confirmation queries and Book links use them.

Settings JSON is one `workflow_dispatch` input named `settings`. Old
three-key files still load (missing keys take config defaults).
