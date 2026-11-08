from datetime import date

from watch.wording import date_ranges, stays_summary


def test_date_ranges():
    assert date_ranges([date(2027, 8, 15)]) == "Sun 15 Aug"
    assert date_ranges([date(2027, 8, d) for d in range(15, 25)]) == "15-24 Aug"
    assert date_ranges([date(2027, 8, 15), date(2027, 8, 18), date(2027, 8, 19)]) == "15 Aug, 18-19 Aug"
    assert date_ranges([date(2027, 8, 31), date(2027, 9, 1)]) == "31 Aug-1 Sep"


def _stay(room, checkin, nights, price):
    return {"room_name": room, "checkin": checkin, "nights": nights, "price": price}


def test_few_stays_listed_one_by_one():
    lines = stays_summary([_stay("One Bedroom Apartment", "2027-08-14", 5, 2065)])
    assert lines == ["One Bedroom Apartment: Sat 14 Aug -> Thu 19 Aug (5 nights), EUR 2,065"]


def test_many_stays_summarised_per_room():
    stays = [_stay("One Bedroom Apartment", f"2027-08-{d}", n, 2065 + 100 * (n - 5))
             for d in (14, 15) for n in (5, 6, 7, 8)]
    stays.append(_stay("Superior One Bedroom Apartment", "2027-08-20", 5, 2135))
    assert stays_summary(stays) == [
        "One Bedroom Apartment: 8 stays, check-in 14-15 Aug, 5-8 nights, from EUR 2,065",
        "Superior One Bedroom Apartment: 1 stay, check-in Fri 20 Aug, 5 nights, from EUR 2,135",
    ]
