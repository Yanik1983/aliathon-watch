# Aliathon Aegean availability watcher

Polls the Aliathon Aegean (Paphos) booking engine every 10 minutes and sends a
push notification plus an email copy the moment a matching stay becomes
bookable. A public status page shows per-night availability and any bookable
stays.

**Watching for (defaults):** One Bedroom Apartment or Superior One Bedroom
Apartment, 5 to 8 nights, check-in on or after 14 Aug 2027, check-out on or
before 29 Aug 2027, 1 room, 2 adults, 2 children. Rooms and the nights range
can be changed from the status page (see "Notification settings" below).

## How it works

1. One request to the booking engine's `/avl` endpoint returns a per-night
   grid for every room type across 14 to 28 Aug 2027.
2. Every run of open nights in a watched room whose length is inside the
   nights range becomes a candidate.
3. Each candidate is confirmed with a second request using those exact dates;
   only rows the hotel marks `AVL` count (this catches minimum-stay rules).
4. New confirmed stays that were not present in the previous poll trigger one
   ntfy notification (push to phone, email copy if configured). Stays that
   disappear again trigger a normal-priority "no longer bookable" push.
5. `state.json`, `history.json` and `docs/index.html` are committed back;
   GitHub Pages serves the page from `docs/`.

The GitHub Actions job is one long loop (poll, commit, sleep 10 minutes) that
runs for about 5 h 50 m. A fresh job starts every 3 hours and on every code
push, cancelling the previous one, so polling stays at a true 10-minute cadence
even when GitHub delays scheduled runs.

Every change in the per-night grid of a watched room (price moved, nights
opened or closed) sends one normal-priority "price change" notification
listing what changed. The settings card can limit this to chosen board
packages, to improvements only (price down or nights opened), or switch it
off. Bookable-stay alerts use high priority.

If three polls fail in a row, one warning notification is sent. A separate
`watchdog` workflow runs hourly and sends a high-priority "watcher silent" push
when `state.json` shows no poll attempt for 30 minutes (GitHub may delay it).

## Notification settings

The status page has a password-gated "Notification settings" card with every
knob: room types, check-in / check-out window (1 to 30 nights), minimum and
maximum nights, adults and children, a cap on the total stay price, and the
price-change push mode and packages. Enter the page password and Save. The
browser decrypts a GitHub token embedded in the page and starts the `settings`
workflow, which validates the values, commits `settings.json`, polls once (so
the page and any bookable-stay alert reflect the change within about a minute)
and sends a low-priority confirmation push. The card shows the settings
currently applied and reloads the page by itself until a save is live. The
"Poll now" button restarts the poll job for an immediate check.

`settings.json` overrides the search values in `watch/config.py`; if the file
is missing or invalid the defaults apply. It can also be written by hand:
`python -m watch.settings --json '{"rooms":["1BED"],"max_nights":7}'`.
Only a 15-night window has been tested against the booking engine; if a wider
window makes polls fail, the failure alert fires after 3 polls and the card
can narrow it again.

If three polls fail in a row, one warning notification is sent.

## Setup

1. Install the [ntfy](https://ntfy.sh/) app on your phone and subscribe to a
   topic. Treat the topic name as a password.
2. Repository secrets (Settings > Secrets and variables > Actions):
   - `NTFY_TOPIC` — the topic name
   - `NTFY_EMAIL` — address for the email copy (optional)
   - `NTFY_TOKEN` — ntfy.sh access token. ntfy.sh only relays email for
     signed-in users, so the email copy needs a free ntfy.sh account: sign up
     at https://ntfy.sh/signup, then Account > Access tokens > Create. Without
     the token the push still goes out; the email copy is skipped.
   - `PAGE_PASSWORD` — optional. Enables a "Test notification" card on the
     status page: enter this password and the page sends a test push through
     the same topic. The topic is embedded in the page encrypted with the
     password (PBKDF2 + AES-GCM, decrypted in the browser only), so it is
     never visible in the repo or the page source. Use a long passphrase:
     the encrypted blob is public and can be brute-forced offline.
   - `SETTINGS_TOKEN` — optional, needs `PAGE_PASSWORD`. Enables the
     "Notification settings" card. Create a GitHub fine-grained personal
     access token (Settings > Developer settings > Personal access tokens >
     Fine-grained tokens): repository access = only this repository,
     repository permission Actions = Read and write, nothing else. That
     permission can only start workflows; it cannot push code or read
     secrets. Set it with `gh secret set SETTINGS_TOKEN`, or run
     `bash scripts/settings-token-wizard.sh`, which walks through creating
     the token, stores the secret, restarts the poll job and waits for the
     card to appear. It is embedded in the page encrypted with
     `PAGE_PASSWORD`, like the topic.
   - `HEALTHCHECK_URL` — optional. A ping URL from https://healthchecks.io
     (free; create a check with period 10 min, grace 20 min, and add an ntfy
     integration there). Every poll pings it, so you get an alert even if
     GitHub Actions as a whole stops running the job. The built-in `watchdog`
     workflow covers the common case without this.
   - optional repository variable `NTFY_SERVER` for a self-hosted ntfy
3. GitHub Pages: Settings > Pages > Source: Deploy from a branch, branch
   `main`, folder `/docs`.
4. Trigger the workflow once manually (Actions > poll > Run workflow).

## Local run

```
pip install -r requirements-dev.txt
pytest
NTFY_TOPIC=your-topic python -m watch.main
```

Without `NTFY_TOPIC` the poll still runs and writes `state.json` and
`docs/index.html`, but only logs what it would have sent.

## Changing the search

Use the "Notification settings" card on the status page, or run the
`settings` workflow from the Actions tab with a JSON object, or
`python -m watch.settings --json '{...}'` locally and commit `settings.json`.

Defaults live in `watch/config.py`: `TARGET_ROOMS`, `MIN_NIGHTS`,
`MAX_NIGHTS`, `FIRST_CHECKIN`, `LAST_CHECKOUT`, `ADULTS`, `CHILDREN`. Room
codes seen on the site: `STD`, `SSTD`, `1BED`, `S1BED`, `1BSU`, `SW1B`, `2B`,
`2BSU`.
