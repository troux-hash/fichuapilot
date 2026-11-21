"""Several rooms of one type in one booking (IMP-18): search, price, checkout, inventory, messages, cancel."""
import re
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from fichua.db import db
from fichua.main import app
from fichua.services import catalog, dates

guest = TestClient(app)
CI = date.today() + timedelta(days=25)
CO = CI + timedelta(days=2)
STAY = {"check_in": CI.isoformat(), "check_out": CO.isoformat()}


def test_rooms_are_parsed_and_kept_in_links():
    ci, co = CI.isoformat(), CO.isoformat()
    three = dates.parse_stay(ci, co, 5, 3)
    assert three.rooms == 3 and three.as_params()["rooms"] == 3
    assert "rooms" not in dates.parse_stay(ci, co, 2).as_params()  # one room: links as before
    assert dates.parse_stay(ci, co, 2, 5).rooms == 2  # never more rooms than guests
    assert dates.parse_stay(ci, co, 12, 20).rooms == dates.MAX_ROOMS
    assert dates.parse_stay(ci, co, 2, "x").rooms == 1
    note = dates.adjustment(ci, co, 2, dates.parse_stay(ci, co, 2, 5), rooms=5)
    assert note == "We changed the number of rooms to 2: each room needs at least one guest."


def test_search_book_and_cancel_several_rooms():
    data = guest.get("/api/search", params={"destination": "Kigali", **STAY, "guests": 5, "rooms": 3,
                                            "free_cancellation": "1", "sort": "price"}).json()
    assert data["stay"]["rooms"] == 3 and data["results"], "expected rooms for 5 guests in 3 rooms"
    offer = data["results"][0]
    room_id = offer["room"]["id"]
    assert offer["rooms"] == 3 and offer["room"]["max_guests"] * 3 >= 5 and offer["rooms_left"] >= 3
    with db.connect() as conn:
        one = catalog.availability(conn, dates.Stay(CI, CO, 2), room_type_id=room_id)[0]
        three = catalog.availability(conn, dates.Stay(CI, CO, 5, 3), room_type_id=room_id)[0]
    assert three["total_price"] == pytest.approx(one["total_price"] * 3)  # the price is for every room

    hotel_page = guest.get(f"/hotels/{offer['hotel']['id']}", params={**STAY, "guests": 5, "rooms": 3}).text
    assert "Reserve 3 rooms" in hotel_page and "3 rooms" in hotel_page
    checkout = guest.get("/book", params={"room": room_id, **STAY, "guests": 5, "rooms": 3}).text
    assert "3 rooms × 2 nights" in checkout and f"× 3</dd>" in checkout and 'name="rooms" value="3"' in checkout

    form = {"room": room_id, **STAY, "guests": 5, "rooms": 3, "guest_name": "Group Leader",
            "guest_email": "group@example.com", "guest_phone": "+250 788 000 888", "guest_language": "en"}
    r = guest.post("/book", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text[-600:]
    ref, token = re.search(r"/pay/(FCH-\w+)\?t=(.+)", r.headers["location"]).groups()
    assert guest.post(f"/pay/{ref}", data={"t": token}, follow_redirects=False).status_code == 303
    with db.connect() as conn:
        b = conn.one("SELECT * FROM bookings WHERE reference = :r", {"r": ref})
        units = [n["units"] for n in conn.all("SELECT units FROM booking_nights WHERE booking_id = :b", {"b": b["id"]})]
        left = catalog.availability(conn, dates.Stay(CI, CO, 2), room_type_id=room_id)[0]["rooms_left"]
        msgs = {m["role"]: m["body"] for m in conn.all("SELECT role, body FROM messages WHERE booking_id = :b",
                                                       {"b": b["id"]})}
    assert (b["rooms"], b["guests"], b["total_price"]) == (3, 5, pytest.approx(three["total_price"]))
    assert units == [3, 3] and left == one["rooms_left"] - 3
    assert f"{offer['room']['name']} × 3, 5 guests" in msgs["guest"] and f"{offer['room']['name']} × 3" in msgs["hotel"]
    page = guest.get(f"/bookings/{ref}", params={"t": token}).text
    assert f"{offer['room']['name']} × 3" in page and "3 rooms · 2 nights" in page

    assert guest.post(f"/bookings/{ref}/cancel", data={"t": token}, follow_redirects=False).status_code == 303
    with db.connect() as conn:
        assert catalog.availability(conn, dates.Stay(CI, CO, 2), room_type_id=room_id)[0]["rooms_left"] == one["rooms_left"]


def test_too_few_rooms_left_is_explained():
    with db.connect() as conn:  # a live room type with fewer rooms than one booking may ask for
        room = conn.one("SELECT rt.id, rt.hotel_id, rt.total_rooms FROM room_types rt JOIN hotels h ON h.id = rt.hotel_id "
                        "WHERE h.is_active = TRUE AND rt.total_rooms < :most ORDER BY rt.total_rooms DESC, rt.id LIMIT 1",
                        {"most": dates.MAX_ROOMS})
    assert room, "the seed has small room types"
    many = room["total_rooms"] + 1
    page = guest.get(f"/hotels/{room['hotel_id']}", params={**STAY, "guests": many, "rooms": many}).text
    assert f"Fewer than {many} rooms left for these dates" in page


def test_big_groups_get_a_several_rooms_search():
    page = guest.get("/search", params={"destination": "Kigali", **STAY, "guests": 12}).text
    hint = re.search(r'href="/search\?([^"]+)">Search for 12 guests in (\d) rooms', page)
    assert hint, "expected a one-tap search with several rooms"
    follow = guest.get("/search?" + hint.group(1).replace("&amp;", "&")).text
    assert "No room" not in follow and f"{hint.group(2)} rooms" in follow
