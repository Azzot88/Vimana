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


async def test_close_requires_being_a_contact_first(client):
    """The refusal lives in the API, not in a hidden button: a rule enforced by
    a disabled control holds only for the client that draws it."""
    mine, _ = await _account(client, "stranger-close")
    _, their_id = await _account(client, "unconnected")

    r = await client.patch(
        f"/api/me/connections/{their_id}", headers=mine, json={"tier": "close"}
    )
    assert r.status_code == 404


async def test_close_is_mutual_or_it_is_pending(client):
    """T3.11.24 — «Близкие только двухсторонние».

    One side calling the other close stores the tier and changes nothing about
    the pair: the state reads `close_pending` until the answer comes back. One
    person does not get to decide they are trusted by another.
    """
    a_h, a_id = await _account(client, "close-a")
    b_h, b_id = await _account(client, "close-b")
    await client.post("/api/me/connections", headers=a_h, json={"user_id": b_id})
    await client.post("/api/me/connections", headers=b_h, json={"user_id": a_id})

    said = await client.patch(
        f"/api/me/connections/{b_id}", headers=a_h, json={"tier": "close"}
    )
    assert said.status_code == 200, said.text
    assert said.json()["tier"] == "close"
    assert said.json()["state"] == "close_pending"

    # And the other side does not see themselves as close either.
    b_list = await client.get("/api/me/connections", headers=b_h)
    row = next(c for c in b_list.json() if c["connected_user_id"] == a_id)
    assert row["state"] == "connection"

    answered = await client.patch(
        f"/api/me/connections/{a_id}", headers=b_h, json={"tier": "close"}
    )
    assert answered.json()["state"] == "close"
    a_list = await client.get("/api/me/connections", headers=a_h)
    row = next(c for c in a_list.json() if c["connected_user_id"] == b_id)
    assert row["state"] == "close"


async def test_stepping_back_from_close_breaks_it_for_both(client):
    """Closeness needs both halves, so withdrawing one is enough to end it —
    and the other side's own tier is left alone, because it is theirs."""
    a_h, a_id = await _account(client, "back-a")
    b_h, b_id = await _account(client, "back-b")
    await client.post("/api/me/connections", headers=a_h, json={"user_id": b_id})
    await client.post("/api/me/connections", headers=b_h, json={"user_id": a_id})
    await client.patch(
        f"/api/me/connections/{b_id}", headers=a_h, json={"tier": "close"}
    )
    await client.patch(
        f"/api/me/connections/{a_id}", headers=b_h, json={"tier": "close"}
    )

    stepped = await client.patch(
        f"/api/me/connections/{b_id}", headers=a_h, json={"tier": "connection"}
    )
    assert stepped.json()["state"] == "connection"
    b_list = await client.get("/api/me/connections", headers=b_h)
    row = next(c for c in b_list.json() if c["connected_user_id"] == a_id)
    assert row["tier"] == "close"
    assert row["state"] == "close_pending"


async def test_unknown_tier_is_refused(client):
    mine, _ = await _account(client, "tier-typo")
    _, their_id = await _account(client, "tier-target")
    await client.post("/api/me/connections", headers=mine, json={"user_id": their_id})
    r = await client.patch(
        f"/api/me/connections/{their_id}", headers=mine, json={"tier": "family"}
    )
    assert r.status_code == 422


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
