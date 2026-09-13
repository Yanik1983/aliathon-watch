"""Static configuration for the Aliathon Aegean availability watcher."""
from __future__ import annotations

import os
from datetime import date

BASE_URL = "https://aliathonaegean.reserve-online.net"
AVL_URL = f"{BASE_URL}/avl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

# Stay parameters
TARGET_ROOMS = ("1BED", "S1BED")
MIN_NIGHTS = 5
MAX_NIGHTS = 8
FIRST_CHECKIN = date(2027, 8, 14)
LAST_CHECKOUT = date(2027, 8, 29)
TOTAL_NIGHTS = (LAST_CHECKOUT - FIRST_CHECKIN).days  # 15
ROOMS = 1
ADULTS = 2
CHILDREN = 2
INFANTS = 0

# Failure alert threshold (consecutive failed polls)
FAIL_ALERT_AT = 3

# Notification (ntfy)
# "or": GitHub Actions passes an undefined repo variable as an empty string.
NTFY_SERVER = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")  # ntfy.sh account token; required for Email
# Password for the "send test push" card on the status page. The topic is embedded
# encrypted with it; without a password the card is not rendered.
PAGE_PASSWORD = os.environ.get("PAGE_PASSWORD", "")
# Fine-grained GitHub PAT (this repo only, Actions: read/write). Embedded encrypted in the
# page so the settings card can dispatch the "settings" workflow. Card needs all three.
SETTINGS_TOKEN = os.environ.get("SETTINGS_TOKEN", "")
GITHUB_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")  # "owner/repo", set by Actions

# Output paths (relative to repo root)
STATE_PATH = "state.json"
PAGE_PATH = "docs/index.html"
HISTORY_PATH = "history.json"
SETTINGS_PATH = "settings.json"
