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
   ntfy notification (push to phone, email copy if configured).
5. `state.json`, `history.json` and `docs/index.html` are committed back;
   GitHub Pages serves the page from `docs/`.

The GitHub Actions job is one long loop (poll, commit, sleep 10 minutes) that
runs for about 5 h 50 m. A fresh job starts every 3 hours and on every code
push, cancelling the previous one, so polling stays at a true 10-minute cadence
even when GitHub delays scheduled runs.

Every change in the per-night grid of a watched room (any board package: price
moved, nights opened or closed) sends one normal-priority "price change"
notification listing what changed. Bookable-stay alerts use high priority.

## Notification settings

The status page has a password-gated "Notification settings" card: tick the
room types to watch, set the minimum and maximum nights, enter the page
password and save. The browser decrypts a GitHub token embedded in the page and
starts the `settings` workflow, which validates the values, commits
`settings.json` and sends a low-priority confirmation push. The poll loop
rebases onto `main` before every poll, so the change is live within 10 minutes.
`settings.json` overrides `TARGET_ROOMS`, `MIN_NIGHTS` and `MAX_NIGHTS` from
`watch/config.py`; if the file is missing or invalid the defaults apply.

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
     secrets. Set it with `gh secret set SETTINGS_TOKEN`. It is embedded in
     the page encrypted with `PAGE_PASSWORD`, like the topic.
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

Rooms and nights range: use the "Notification settings" card on the status
page, or run the `settings` workflow from the Actions tab, or edit
`settings.json` by hand (`python -m watch.settings --rooms 1BED,S1BED --min 5 --max 8`).

Dates, guests and defaults: edit `watch/config.py`: `TARGET_ROOMS`,
`MIN_NIGHTS`, `MAX_NIGHTS`, `FIRST_CHECKIN`, `LAST_CHECKOUT`, `ADULTS`,
`CHILDREN`. Room codes seen on the site: `STD`, `SSTD`, `1BED`, `S1BED`,
`1BSU`, `SW1B`, `2B`, `2BSU`.
