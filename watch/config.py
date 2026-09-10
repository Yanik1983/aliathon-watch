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
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "")
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "")  # ntfy.sh account token; required for Email

# Output paths (relative to repo root)
STATE_PATH = "state.json"
PAGE_PATH = "docs/index.html"
