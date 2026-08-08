import uuid as uuidlib


async def test_join_waitlist_success(client):
    email = f"wl-{uuidlib.uuid4().hex[:8]}@vimana.test"
    resp = await client.post(
        "/api/waitlist", json={"email": email, "name": "Test User", "source": "hero_cta"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert body["name"] == "Test User"
    assert body["source"] == "hero_cta"


async def test_join_waitlist_normalizes_email(client):
    prefix = uuidlib.uuid4().hex[:6]
    resp = await client.post(
        "/api/waitlist", json={"email": f"  UPPER-{prefix}@Vimana.Test  "}
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == f"upper-{prefix}@vimana.test"


async def test_join_waitlist_duplicate_returns_409(client):
    email = f"dup-{uuidlib.uuid4().hex[:8]}@vimana.test"
    first = await client.post("/api/waitlist", json={"email": email})
    assert first.status_code == 201
    second = await client.post("/api/waitlist", json={"email": email})
    assert second.status_code == 409


async def test_join_waitlist_invalid_email_returns_422(client):
    resp = await client.post("/api/waitlist", json={"email": "not-an-email"})
    assert resp.status_code == 422


async def _register(client, email: str) -> dict[str, str]:
    from tests.conftest import SEED_PASSWORD

    await client.post(
        "/api/auth/register",
        json={"email": email, "password": SEED_PASSWORD, "display_name": email[:8]},
    )
    login = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _promote_to_superuser(session_maker, email: str):
    from sqlalchemy import select

    from app.models.user import User

    async with session_maker() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.role = "superuser"
        await db.commit()


async def test_list_waitlist_anonymous_is_unauthorized(client):
    """T_UX.8 pt.2 — the shared `X-Admin-Token` is gone; this is a normal session now."""
    resp = await client.get("/api/waitlist")
    assert resp.status_code == 401


async def test_list_waitlist_ordinary_user_forbidden(client):
    from tests.conftest import unique_email

    hdr = await _register(client, unique_email("wl-plain"))
    resp = await client.get("/api/waitlist", headers=hdr)
    assert resp.status_code == 403, "signing in must not be enough to read the list"


async def test_list_waitlist_superuser_reads_it(client, session_maker):
    from tests.conftest import unique_email

    admin_email = unique_email("wl-adm")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    email = f"list-{uuidlib.uuid4().hex[:8]}@vimana.test"
    await client.post("/api/waitlist", json={"email": email})

    resp = await client.get("/api/waitlist", headers=hdr)
    assert resp.status_code == 200
    body = resp.json()
    assert email in {e["email"] for e in body["items"]}
    assert "next_cursor" in body


async def test_list_waitlist_ignores_the_retired_admin_token(client):
    """A leftover header must not be a second way in — that was the whole point."""
    resp = await client.get("/api/waitlist", headers={"X-Admin-Token": "anything"})
    assert resp.status_code == 401


async def test_join_waitlist_queues_the_letters(client, monkeypatch):
    """T_UX.8 — the endpoint must hand the mail to a worker, not send it itself.

    `send_email` is synchronous smtplib; sending inline would hold this async
    endpoint for two SMTP round-trips while a stranger waits on the form.
    """
    queued = []
    from app.tasks import notifications as notif

    monkeypatch.setattr(
        notif.send_waitlist_emails, "delay", lambda entry_id: queued.append(entry_id)
    )

    email = f"queue-{uuidlib.uuid4().hex[:8]}@vimana.test"
    resp = await client.post("/api/waitlist", json={"email": email, "source": "landing"})

    assert resp.status_code == 201
    assert queued == [resp.json()["id"]]


async def test_join_waitlist_survives_a_dead_broker(client, monkeypatch):
    """A queue outage must not cost us the signup — the row is what matters."""
    from app.tasks import notifications as notif

    def _boom(entry_id):
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(notif.send_waitlist_emails, "delay", _boom)

    email = f"broker-{uuidlib.uuid4().hex[:8]}@vimana.test"
    resp = await client.post("/api/waitlist", json={"email": email})

    assert resp.status_code == 201, "the visitor must not see our broker's problems"


async def test_new_entry_starts_unanswered(client, session_maker):
    """`confirmation_sent_at` NULL is what the backfill looks for."""
    from app.models.waitlist import WaitlistEntry

    email = f"fresh-{uuidlib.uuid4().hex[:8]}@vimana.test"
    resp = await client.post("/api/waitlist", json={"email": email})
    assert resp.status_code == 201

    async with session_maker() as db:
        entry = await db.get(WaitlistEntry, resp.json()["id"])
        assert entry.confirmation_sent_at is None
