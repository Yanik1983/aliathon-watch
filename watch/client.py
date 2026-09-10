"""HTTP access to the WebHotelier /avl endpoint."""
from __future__ import annotations

import logging
import time
from datetime import date

import requests

from watch import config

log = logging.getLogger(__name__)


class FetchError(Exception):
    """Network failure, non-200 status, or a response without an html grid."""


_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, */*",
    "Referer": config.BASE_URL + "/",
    "Origin": config.BASE_URL,
}


def fetch_avl(
    fromd: date,
    nights: int,
    session: requests.Session | None = None,
    retries: int = 1,
    retry_delay: float = 5.0,
    timeout: float = 30.0,
) -> str:
    """POST the availability form and return the html fragment."""
    form = {
        "fromd": fromd.isoformat(),
        "nights": str(nights),
        "rooms": str(config.ROOMS),
        "adults": str(config.ADULTS),
        "children": str(config.CHILDREN),
        "infants": str(config.INFANTS),
        "voucher": "",
    }
    sess = session or requests.Session()
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = sess.post(config.AVL_URL, data=form, headers=_HEADERS, timeout=timeout)
            if resp.status_code != 200:
                raise FetchError(f"HTTP {resp.status_code} from /avl")
            try:
                data = resp.json()
            except ValueError as e:
                raise FetchError(f"non-JSON response: {e}") from e
            html = data.get("html") if isinstance(data, dict) else None
            if not html:
                raise FetchError("response has no html grid")
            return html
        except (requests.RequestException, FetchError) as e:
            last_err = e
            log.warning("fetch attempt %d failed: %s", attempt + 1, e)
            if attempt < retries:
                time.sleep(retry_delay)
    raise FetchError(str(last_err))
