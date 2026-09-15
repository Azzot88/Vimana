import uuid

from tests.conftest import make_account, unique_email


async def _register_and_login(client, email: str, password: str = "invite-pass-1"):
    reg = await make_account({"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_create_invite(client, carrier_headers):
    resp = await client.post("/api/invites", headers=carrier_headers, json={})
    assert resp.status_code == 201
    body = resp.json()
    assert "token" in body
    assert "expires_at" in body


async def test_accept_invite_creates_two_way_connection(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    friend_headers = await _register_and_login(client, unique_email("friend"))

    accept = await client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert accept.status_code == 200

    # Friend sees carrier in connections
    friend_conn = await client.get("/api/me/connections", headers=friend_headers)
    assert friend_conn.status_code == 200
    assert len(friend_conn.json()) >= 1

    # Carrier sees friend in connections
    carrier_conn = await client.get("/api/me/connections", headers=carrier_headers)
    assert carrier_conn.status_code == 200
    assert len(carrier_conn.json()) >= 1


async def test_accept_own_invite_forbidden(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    resp = await client.post(f"/api/invites/{token}/accept", headers=carrier_headers)
    assert resp.status_code == 400


async def test_accept_reused_invite_conflicts(client, carrier_headers):
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    first = await _register_and_login(client, unique_email("first"))
    ok = await client.post(f"/api/invites/{token}/accept", headers=first)
    assert ok.status_code == 200

    second = await _register_and_login(client, unique_email("second"))
    dup = await client.post(f"/api/invites/{token}/accept", headers=second)
    assert dup.status_code == 409


async def test_accept_invite_is_idempotent_for_same_user(client, carrier_headers):
    """Same user re-accepting must return 200 (not 409).

    Fixes race triggered by React StrictMode double-mount + real-world
    double-click / axios retry. The connection is already created; the second
    call should be a silent no-op.
    """
    invite = await client.post("/api/invites", headers=carrier_headers, json={})
    token = invite.json()["token"]

    friend = await _register_and_login(client, unique_email("idem"))
    first = await client.post(f"/api/invites/{token}/accept", headers=friend)
    assert first.status_code == 200
    assert first.json() == {"ok": True}

    second = await client.post(f"/api/invites/{token}/accept", headers=friend)
    assert second.status_code == 200, f"expected idempotent 200, got {second.status_code}"
    assert second.json() == {"ok": True}


async def test_accept_unknown_invite_returns_404(client, carrier_headers):
    friend_headers = await _register_and_login(client, unique_email("nobody"))
    resp = await client.post(
        "/api/invites/nonexistent-token-value/accept", headers=friend_headers
    )
    assert resp.status_code == 404


async def test_create_invite_ttl_is_14_days(client, carrier_headers):
    from datetime import datetime, timezone
    resp = await client.post("/api/invites", headers=carrier_headers, json={})
    assert resp.status_code == 201
    expires_at = datetime.fromisoformat(resp.json()["expires_at"].replace("Z", "+00:00"))
    delta = expires_at - datetime.now(timezone.utc)
    days = delta.total_seconds() / 86400
    assert 13.9 < days <= 14.0


async def test_list_my_invites_returns_pending_status(client):
    email = unique_email("inv-owner")
    headers = await _register_and_login(client, email)

    create = await client.post("/api/invites", headers=headers, json={})
    token = create.json()["token"]

    resp = await client.get("/api/invites/mine", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    mine = [i for i in body if i["token"] == token]
    assert len(mine) == 1
    assert mine[0]["status"] == "pending"
    assert mine[0]["accepted_by_display_name"] is None


async def test_list_my_invites_reflects_accepted(client):
    owner_headers = await _register_and_login(client, unique_email("inv-o"))
    create = await client.post("/api/invites", headers=owner_headers, json={})
    token = create.json()["token"]

    friend_headers = await _register_and_login(client, unique_email("inv-friend"))
    accept = await client.post(f"/api/invites/{token}/accept", headers=friend_headers)
    assert accept.status_code == 200

    resp = await client.get("/api/invites/mine", headers=owner_headers)
    assert resp.status_code == 200
    mine = [i for i in resp.json() if i["token"] == token]
    assert len(mine) == 1
    assert mine[0]["status"] == "accepted"
    assert mine[0]["accepted_by_display_name"] is not None


async def test_list_my_invites_empty_for_new_user(client):
    headers = await _register_and_login(client, unique_email("inv-empty"))
    resp = await client.get("/api/invites/mine", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []  # kept as list for backwards-compat, small bounded set


async def _account(client, prefix: str):
    """A fresh person and their headers. Shared fixtures accumulate contacts
    across the suite (`ENVIRONMENT §8`), and every assertion below is about a
    relationship existing or not — which needs two people with no history."""
    email = unique_email(prefix)
    headers = await _register_and_login(client, email)
    me = await client.get("/api/auth/me", headers=headers)
    return headers, me.json()["id"]


async def test_contact_can_be_one_way(client):
    """T3.11.24 — «Контакты могут быть и односторонними».

    Adding somebody writes one row, mine. Their list is theirs: a contact list
    that could be written into from outside is a list anybody can join.
    """
    mine, my_id = await _account(client, "keeper")
    theirs, their_id = await _account(client, "kept")

    added = await client.post(
        "/api/me/connections", headers=mine, json={"user_id": their_id}
    )
    assert added.status_code == 201, added.text
    assert added.json()["state"] == "connection"

    my_list = await client.get("/api/me/connections", headers=mine)
    assert their_id in [c["connected_user_id"] for c in my_list.json()]

    their_list = await client.get("/api/me/connections", headers=theirs)
    assert my_id not in [c["connected_user_id"] for c in their_list.json()]


async def test_adding_the_same_person_twice_is_the_same_contact(client):
    mine, _ = await _account(client, "twice")
    _, their_id = await _account(client, "target")

    first = await client.post(
        "/api/me/connections", headers=mine, json={"user_id": their_id}
    )
    second = await client.post(
        "/api/me/connections", headers=mine, json={"user_id": their_id}
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_cannot_add_yourself(client):
    mine, my_id = await _account(client, "narcissus")
    r = await client.post("/api/me/connections", headers=mine, json={"user_id": my_id})
    assert r.status_code == 400


# ── T3.12.06 · close people: asked, and answered ───────────────────────────


async def _contact(client, headers, user_id):
    r = await client.post("/api/me/connections", headers=headers, json={"user_id": user_id})
    assert r.status_code == 201, r.text


async def _close_of(client, headers, user_id):
    rows = (await client.get("/api/me/close", headers=headers)).json()
    return next((p for p in rows if p["user_id"] == user_id), None)


async def _contact_state(client, headers, user_id):
    rows = (await client.get("/api/me/connections", headers=headers)).json()
    return next(c["state"] for c in rows if c["connected_user_id"] == user_id)


async def test_close_is_asked_only_of_a_contact(client):
    """Owner, 2026-09-14: «только из друзей». The refusal lives in the API, not
    in a hidden button."""
    mine, _ = await _account(client, "stranger-close")
    _, their_id = await _account(client, "unconnected")
    r = await client.post("/api/me/close", headers=mine, json={"user_id": their_id})
    assert r.status_code == 404


async def test_close_is_a_request_until_it_is_accepted(client):
    """One person does not get to decide they are trusted by another: asking
    changes nothing about the pair until the other side answers. The person
    asked need not keep the asker in their own contacts to answer."""
    a_h, a_id = await _account(client, "close-a")
    b_h, b_id = await _account(client, "close-b")
    await _contact(client, a_h, b_id)

    asked = await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    assert asked.status_code == 201, asked.text
    assert asked.json()["state"] == "close_pending"
    assert await _contact_state(client, a_h, b_id) == "close_pending"

    incoming = await _close_of(client, b_h, a_id)
    assert incoming["state"] == "close_requested"

    accepted = await client.post(f"/api/me/close/{incoming['id']}/accept", headers=b_h)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["state"] == "close"
    assert await _contact_state(client, a_h, b_id) == "close"
    assert (await _close_of(client, b_h, a_id))["state"] == "close"


async def test_a_declined_request_leaves_them_contacts_and_can_be_asked_again(client):
    a_h, a_id = await _account(client, "decl-a")
    b_h, b_id = await _account(client, "decl-b")
    await _contact(client, a_h, b_id)
    await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    request_id = (await _close_of(client, b_h, a_id))["id"]

    declined = await client.post(f"/api/me/close/{request_id}/decline", headers=b_h)
    assert declined.status_code == 200, declined.text
    assert await _contact_state(client, a_h, b_id) == "connection"
    assert await _close_of(client, b_h, a_id) is None

    again = await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    assert again.status_code == 201
    assert again.json()["id"] != request_id


async def test_asking_back_is_accepting(client):
    a_h, a_id = await _account(client, "back-and-forth-a")
    b_h, b_id = await _account(client, "back-and-forth-b")
    await _contact(client, a_h, b_id)
    await _contact(client, b_h, a_id)
    await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})

    answered = await client.post("/api/me/close", headers=b_h, json={"user_id": a_id})
    assert answered.json()["state"] == "close"
    assert await _contact_state(client, a_h, b_id) == "close"


async def test_asking_twice_is_one_request(client):
    a_h, _ = await _account(client, "twice-a")
    _, b_id = await _account(client, "twice-b")
    await _contact(client, a_h, b_id)
    first = await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    second = await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    assert first.json()["id"] == second.json()["id"]


async def test_either_side_ends_closeness(client):
    a_h, a_id = await _account(client, "end-a")
    b_h, b_id = await _account(client, "end-b")
    await _contact(client, a_h, b_id)
    await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    await client.post(
        f"/api/me/close/{(await _close_of(client, b_h, a_id))['id']}/accept", headers=b_h
    )

    ended = await client.delete(f"/api/me/close/{a_id}", headers=b_h)
    assert ended.status_code == 204
    assert await _contact_state(client, a_h, b_id) == "connection"
    assert await _close_of(client, a_h, b_id) is None
    # Nothing left to end.
    assert (await client.delete(f"/api/me/close/{b_id}", headers=a_h)).status_code == 404


async def test_only_the_person_asked_answers(client):
    a_h, a_id = await _account(client, "ask-a")
    b_h, b_id = await _account(client, "ask-b")
    stranger, _ = await _account(client, "ask-stranger")
    await _contact(client, a_h, b_id)
    request_id = (
        await client.post("/api/me/close", headers=a_h, json={"user_id": b_id})
    ).json()["id"]

    for hdr in (a_h, stranger):
        r = await client.post(f"/api/me/close/{request_id}/accept", headers=hdr)
        assert r.status_code == 404, r.text
    assert (await _close_of(client, b_h, a_id))["state"] == "close_requested"


async def test_contacts_are_searchable_by_name(client):
    """The recipient picker has a search box above the list, and this is what it
    calls. Names, because that is what somebody remembers."""
    mine, _ = await _account(client, "searcher")
    _, their_id = await _account(client, "findme-unique")

    await client.post("/api/me/connections", headers=mine, json={"user_id": their_id})
    hit = await client.get(
        "/api/me/connections", headers=mine, params={"q": "findme-unique"}
    )
    assert [c["connected_user_id"] for c in hit.json()] == [their_id]

    miss = await client.get(
        "/api/me/connections", headers=mine, params={"q": "nobody-by-this-name"}
    )
    assert miss.json() == []


async def test_removing_a_contact_leaves_theirs_alone(client):
    a_h, a_id = await _account(client, "drop-a")
    b_h, b_id = await _account(client, "drop-b")
    await client.post("/api/me/connections", headers=a_h, json={"user_id": b_id})
    await client.post("/api/me/connections", headers=b_h, json={"user_id": a_id})

    gone = await client.delete(f"/api/me/connections/{b_id}", headers=a_h)
    assert gone.status_code == 204
    again = await client.delete(f"/api/me/connections/{b_id}", headers=a_h)
    assert again.status_code == 404

    b_list = await client.get("/api/me/connections", headers=b_h)
    assert a_id in [c["connected_user_id"] for c in b_list.json()]


# ── T3.11.24 pt.2: handle and lookup ────────────────────────────────────────


async def test_handle_is_chosen_and_normalised(client):
    """Owner's request 2026-09-07: a handle picked in the cabinet.

    `@Igor_88` and `igor_88` are the same handle — the `@` is how it is written,
    not part of the value, and case must not be able to make two accounts.
    """
    mine, _ = await _account(client, "handler")
    # Randomised, like every other handle here: a handle is unique for the life
    # of the database, and `vimana_test` is never reset (`ENVIRONMENT §8`), so a
    # fixed one passes on the run that claims it and answers 409 on every run
    # after — the account is fresh, the name is not.
    chosen = f"Vimana_{uuid.uuid4().hex[:8]}"
    r = await client.patch("/api/auth/me", headers=mine, json={"handle": f"@{chosen}"})
    assert r.status_code == 200, r.text
    assert r.json()["handle"] == chosen.lower()


async def test_handle_must_be_free(client):
    a_h, _ = await _account(client, "hand-a")
    b_h, _ = await _account(client, "hand-b")
    taken = f"taken{uuid.uuid4().hex[:8]}"
    assert (
        await client.patch("/api/auth/me", headers=a_h, json={"handle": taken})
    ).status_code == 200
    clash = await client.patch("/api/auth/me", headers=b_h, json={"handle": taken})
    assert clash.status_code == 409


async def test_keeping_your_own_handle_is_not_a_clash(client):
    """The uniqueness check excludes the caller — re-saving a profile form with
    the handle untouched must not be an error."""
    mine, _ = await _account(client, "hand-same")
    same = f"same{uuid.uuid4().hex[:8]}"
    await client.patch("/api/auth/me", headers=mine, json={"handle": same})
    again = await client.patch("/api/auth/me", headers=mine, json={"handle": same})
    assert again.status_code == 200


async def test_malformed_handle_is_refused(client):
    mine, _ = await _account(client, "hand-bad")
    for bad in ["дв", "ab", "with space", "sym!bol"]:
        r = await client.patch("/api/auth/me", headers=mine, json={"handle": bad})
        assert r.status_code == 422, f"{bad!r} was accepted"


async def test_handle_can_be_given_up(client):
    mine, _ = await _account(client, "hand-drop")
    handle = f"drop{uuid.uuid4().hex[:8]}"
    await client.patch("/api/auth/me", headers=mine, json={"handle": handle})
    cleared = await client.patch("/api/auth/me", headers=mine, json={"handle": ""})
    assert cleared.status_code == 200
    assert cleared.json()["handle"] is None


async def test_lookup_finds_by_handle_email_and_phone(client):
    """«Поиск сделаем по почте и номеру телефона указанному в личном кабинете»,
    plus the handle chosen there."""
    mine, _ = await _account(client, "seeker")
    theirs, their_id = await _account(client, "sought")
    handle = f"sought{uuid.uuid4().hex[:8]}"
    await client.patch("/api/auth/me", headers=theirs, json={"handle": handle})
    me = await client.get("/api/auth/me", headers=theirs)
    email = me.json()["email"]
    # A random Russian mobile: `9` plus nine digits is the whole national
    # pattern, so any draw is a valid number, and the space is big enough that
    # a database which is never reset (`ENVIRONMENT §8`) will not collide on the
    # unique column.
    phone = f"+79{uuid.uuid4().int % 10**9:09d}"
    await client.patch("/api/auth/me", headers=theirs, json={"phone": phone})

    for needle in (handle, f"@{handle}", email, phone):
        r = await client.get("/api/users/lookup", headers=mine, params={"q": needle})
        assert r.status_code == 200, r.text
        assert their_id in [u["id"] for u in r.json()], f"{needle!r} found nobody"

    # And what comes back is a name and a handle — never a second contact
    # detail the searcher did not already have.
    body = (
        await client.get("/api/users/lookup", headers=mine, params={"q": handle})
    ).json()[0]
    assert set(body) == {"id", "display_name", "handle"}


async def test_lookup_is_exact_not_a_prefix(client):
    """A prefix search over emails or numbers is an address-book harvester. The
    searcher must already hold the whole value."""
    mine, _ = await _account(client, "prefixer")
    theirs, their_id = await _account(client, "prefixed")
    handle = f"exact{uuid.uuid4().hex[:8]}"
    await client.patch("/api/auth/me", headers=theirs, json={"handle": handle})

    partial = await client.get(
        "/api/users/lookup", headers=mine, params={"q": handle[:-2]}
    )
    assert their_id not in [u["id"] for u in partial.json()]


async def test_lookup_never_returns_yourself(client):
    mine, my_id = await _account(client, "myself")
    handle = f"self{uuid.uuid4().hex[:8]}"
    await client.patch("/api/auth/me", headers=mine, json={"handle": handle})
    r = await client.get("/api/users/lookup", headers=mine, params={"q": handle})
    assert my_id not in [u["id"] for u in r.json()]


async def test_cancel_timeout_is_a_personal_setting(client):
    """T3.11.27 — «у обоих своя, действует меньшая» (owner, 2026-09-07).

    A cancellation nobody answered closes itself, and how long it waits belongs
    to whoever is in a hurry: a carrier flying tomorrow cannot wait a week, and
    neither can a sender whose parcel is packed. So it is a profile setting, not
    a field of the deal — one number per account, compared at the moment of
    cancelling.
    """
    mine, _ = await _account(client, "patience")

    default = await client.get("/api/auth/me", headers=mine)
    assert default.json()["cancel_timeout_hours"] == 48

    changed = await client.patch(
        "/api/auth/me", headers=mine, json={"cancel_timeout_hours": 168}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["cancel_timeout_hours"] == 168

    # A week is the ceiling the owner named, and an hour the floor: below it the
    # «wait for an answer» is not a wait.
    for bad in (0, 169):
        r = await client.patch(
            "/api/auth/me", headers=mine, json={"cancel_timeout_hours": bad}
        )
        assert r.status_code == 422, f"{bad} was accepted"

    # Null is not «no timeout» — it is a deal nobody can close by walking away.
    cleared = await client.patch(
        "/api/auth/me", headers=mine, json={"cancel_timeout_hours": None}
    )
    assert cleared.status_code == 422
