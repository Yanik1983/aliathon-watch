import json
from datetime import date
from pathlib import Path

import pytest

from watch.client import FetchError
from watch.confirm import ConfirmedWindow, booking_url, confirm
from watch.finder import Window

FIXTURE = Path(__file__).parent / "fixtures" / "avl_7n_studio_avl.json"
HTML = json.loads(FIXTURE.read_text(encoding="utf-8"))["html"]


def fake_fetch_ok(fromd, nights):
    assert fromd == date(2027, 8, 14)
    assert nights == 7
    return HTML


def test_booking_url():
    url = booking_url(date(2027, 8, 14), 7)
    assert url.startswith("https://aliathonaegean.reserve-online.net/")
    assert "checkin=2027-08-14" in url
    assert "nights=7" in url
    assert "adults=2" in url


def test_confirm_avl_room():
    w = Window(room="STD", checkin=date(2027, 8, 14), nights=7, total=1820)
    c = confirm(w, fetch=fake_fetch_ok)
    assert isinstance(c, ConfirmedWindow)
    assert c.window == w
    assert c.price == 1820
    assert c.room_name == "Studio"
    assert "checkin=2027-08-14" in c.url and "nights=7" in c.url


def test_confirm_na_room_returns_none():
    w = Window(room="1BED", checkin=date(2027, 8, 14), nights=7, total=1960)
    assert confirm(w, fetch=fake_fetch_ok) is None


def test_confirm_unknown_room_returns_none():
    w = Window(room="NOPE", checkin=date(2027, 8, 14), nights=7, total=0)
    assert confirm(w, fetch=fake_fetch_ok) is None


def test_confirm_fetch_error_returns_none():
    def boom(fromd, nights):
        raise FetchError("down")

    w = Window(room="STD", checkin=date(2027, 8, 14), nights=7, total=1820)
    assert confirm(w, fetch=boom) is None


def test_confirm_garbage_html_returns_none():
    w = Window(room="STD", checkin=date(2027, 8, 14), nights=7, total=1820)
    assert confirm(w, fetch=lambda f, n: "<p>nope</p>") is None
