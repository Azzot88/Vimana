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


# ── T_UX.9 pt.2 · mail console ───────────────────────────────────────────────


async def test_mail_console_is_superuser_only(client):
    from tests.conftest import unique_email

    assert (await client.get("/api/admin/email/status")).status_code == 401
    hdr = await _register(client, unique_email("mail-plain"))
    assert (await client.get("/api/admin/email/status", headers=hdr)).status_code == 403


async def test_mail_status_never_returns_a_password(client, session_maker):
    from tests.conftest import unique_email

    admin_email = unique_email("mail-adm")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    resp = await client.get("/api/admin/email/status", headers=hdr)
    assert resp.status_code == 200
    body = resp.json()
    assert "live" in body and "preview" in body
    assert "password" not in str(body).lower(), (
        "a read-only console has no use for the credential"
    )


async def test_templates_render_without_touching_smtp(client, session_maker, monkeypatch):
    """The page must work with mail completely broken — that is the separation."""
    from tests.conftest import unique_email

    from app.core.config import settings

    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "PREVIEW_SMTP_HOST", "")

    admin_email = unique_email("mail-tpl")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    resp = await client.get(
        "/api/admin/email/templates", headers=hdr, params={"locale": "fr"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["locale"] == "fr"
    assert len(body["letters"]) == 8
    assert all(letter["subject"] and letter["html"] for letter in body["letters"])


async def test_templates_unknown_locale_degrades_like_a_real_delivery(
    client, session_maker
):
    from tests.conftest import unique_email

    admin_email = unique_email("mail-loc")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    resp = await client.get(
        "/api/admin/email/templates", headers=hdr, params={"locale": "kl"}
    )
    assert resp.status_code == 200
    english = await client.get(
        "/api/admin/email/templates", headers=hdr, params={"locale": "en"}
    )
    assert resp.json()["letters"][0]["subject"] == english.json()["letters"][0]["subject"]


async def test_test_send_refuses_when_preview_circuit_is_off(
    client, session_maker, monkeypatch
):
    """Silence would be the failure mode this whole area was fixed to stop."""
    from tests.conftest import unique_email

    from app.core.config import settings

    monkeypatch.setattr(settings, "PREVIEW_SMTP_HOST", "")

    admin_email = unique_email("mail-test")
    hdr = await _register(client, admin_email)
    await _promote_to_superuser(session_maker, admin_email)

    resp = await client.post(
        "/api/admin/email/test", headers=hdr, json={"to": "x@y.test"}
    )
    assert resp.status_code == 503
