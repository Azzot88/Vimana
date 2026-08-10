import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.worker import celery_app
from app.core.database import SyncSessionLocal
from app.core.email import send_email
from app.core.email_templates import DEFAULT_LOCALE
from app.core.telegram import send_telegram
from app.core.whatsapp import send_whatsapp

# The three admin tasks below call this in their "nobody to tell" fallback, and
# it was never defined: the branch raised `NameError` instead of logging. That
# branch only runs when `ADMIN_TELEGRAM_CHAT_IDS` is empty — the exact case it
# exists to cover — so the last line of defence was broken precisely when it
# was needed. Found 2026-08-08 while adding the waitlist letters.
logger = logging.getLogger(__name__)

def _send(user_or_locale, to: str, kind: str, **ctx) -> bool:
    """Render one letter in the recipient's language and hand it to SMTP.

    Takes either a `User` (reads `.locale`) or a bare locale string, because
    half these letters go to an account and half to an address that has none.

    Called by: every task in this module that sends mail.
    """
    from app.core.email_templates import render

    locale = getattr(user_or_locale, "locale", user_or_locale)
    letter = render(kind, locale, **ctx)
    return send_email(to, letter.subject, letter.text, letter.html)


def _notify_user(user, kind: str, **ctx) -> None:
    """Fan one event out to whichever channels this user has turned on.

    Only email is templated: Telegram and WhatsApp are plain-text transports,
    and they take the text part of the same letter rather than a second string
    that would drift away from it.

    Called by: `notify_deal_status`, `check_upcoming_deadlines`.
    """
    from app.core.email_templates import render

    letter = render(kind, getattr(user, "locale", None), **ctx)
    if user.notify_email and user.email:
        send_email(user.email, letter.subject, letter.text, letter.html)
    if user.notify_telegram and user.telegram_chat_id:
        send_telegram(user.telegram_chat_id, letter.text)
    if user.notify_whatsapp and user.whatsapp_number:
        send_whatsapp(user.whatsapp_number, letter.text)


@celery_app.task(name="app.tasks.notifications.notify_deal_status")
def notify_deal_status(deal_id: str, status: str) -> None:
    from app.models.deal import Deal
    from app.models.user import User

    with SyncSessionLocal() as db:
        deal = db.get(Deal, deal_id)
        if not deal:
            return
        sender = db.get(User, str(deal.sender_id))
        carrier = db.get(User, str(deal.carrier_id))

        if sender:
            _notify_user(sender, "deal_status", status=status)
        if carrier and carrier.id != (sender.id if sender else None):
            _notify_user(carrier, "deal_status", status=status)


@celery_app.task(name="app.tasks.notifications.check_upcoming_deadlines")
def check_upcoming_deadlines() -> None:
    from sqlalchemy import select, and_
    from app.models.marketplace import Order, OrderStatus
    from app.models.deal import Deal, DealStatus
    from app.models.user import User

    now = datetime.now(timezone.utc)
    window = now + timedelta(hours=24)

    with SyncSessionLocal() as db:
        stmt = (
            select(Order)
            .where(
                and_(
                    Order.deadline.isnot(None),
                    Order.deadline <= window,
                    Order.deadline >= now,
                    Order.status.notin_([OrderStatus.closed]),
                )
            )
        )
        orders = db.execute(stmt).scalars().all()

        for order in orders:
            deal = db.execute(
                select(Deal).where(
                    and_(
                        Deal.order_id == order.id,
                        Deal.status.notin_([DealStatus.closed, DealStatus.confirmed]),
                    )
                )
            ).scalar_one_or_none()
            if not deal:
                continue

            sender = db.get(User, str(deal.sender_id))
            carrier = db.get(User, str(deal.carrier_id))

            if sender:
                _notify_user(sender, "deadline_reminder")
            if carrier:
                _notify_user(carrier, "deadline_reminder")


@celery_app.task(name="app.tasks.notifications.send_verification_code")
def send_verification_code(user_id: str, code: str) -> None:
    """T3.11 — deliver an email confirmation code.

    Runs as a task rather than inline because `core.email.send_email` is
    synchronous `smtplib`: called from the request path it would block the
    FastAPI event loop for the duration of the SMTP round-trip.

    The plaintext code arrives as an argument — it exists nowhere else, the
    column holds only a bcrypt hash. `notify_email` is deliberately NOT
    consulted: this is not a notification the user opted into, it is the proof
    of address they asked for.
    """
    from app.core.email_verification import target_email
    from app.models.user import User

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return
        # A change in flight is delivered to the *new* address — sending the
        # code to the old one would ask the wrong mailbox to vouch for the new.
        recipient = target_email(user)
        if not recipient:
            return
        _send(user, recipient, "verification_code", code=code)


@celery_app.task(name="app.tasks.notifications.send_recovery_code_used")
def send_recovery_code_used(user_id: str, remaining: int) -> None:
    """T3.16 — tell the owner that a recovery code was spent.

    Sent regardless of `notify_email`, like the confirmation code and for the
    same reason: this is not a notification anyone opted into, it is the one
    signal that says someone used a code — and if it was not the owner, this
    letter is how they find out at all.

    Nothing here can be undone by replying, so the letter says what to do
    instead: sign in and replace the set. The remaining count is included
    because "how many are left" is the first question after "was that me?".
    """
    from app.models.user import User

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.email:
            return
        _send(user, user.email, "recovery_code_used", remaining=remaining)


@celery_app.task(name="app.tasks.notifications.send_platform_copy_deleted")
def send_platform_copy_deleted(user_id: str) -> None:
    """T3.17 — the account asked us to stop holding its key, and we did.

    Sent regardless of `notify_email`, like the confirmation code: this is not a
    subscription, it is the record of an irreversible change. If it was not the
    owner who did it, this letter is how they find out — and while the action
    cannot be undone, an account with a copy of its Identity Vault can hand one
    back, which is what the letter says instead of "sorry".
    """
    from app.models.user import User

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.email:
            return
        _send(user, user.email, "platform_copy_deleted")


@celery_app.task(name="app.tasks.notifications.send_archive_window_opened")
def send_archive_window_opened(user_id: str, ends_at_iso: str) -> None:
    """T3.19 — the identity was retired; here is the one decision left, and its date.

    The modal says all of this too, but the modal only reaches someone who signs
    in. This letter exists for the case the modal cannot cover: an owner who
    lost the key *and* stopped opening the site. For them the default applies —
    the archive stays visible — and they deserve to learn that from us rather
    than from a search engine.

    Sent regardless of `notify_email`, like the recovery-code letter and for the
    same reason: nobody subscribes to being told their identity ended, and the
    date after which the choice fixes is not something to leave to a
    preference toggle.

    The date is passed in rather than recomputed here. It comes from
    `core.permissions.archive_window_ends_at`, the single source for this
    deadline — a second calculation in a Celery task is how the letter and the
    screen start disagreeing about the day.
    """
    from app.models.user import User

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.email:
            return
        _send(user, user.email, "archive_window_opened", deadline=ends_at_iso)


def _send_waitlist_pair(db, entry) -> bool:
    """Write to the visitor, then to the owner. Returns True if the visitor got mail.

    Order matters: the confirmation is the promise we made on the landing page,
    the owner's copy is bookkeeping. If SMTP is down we would rather fail on
    the one that matters and retry it than mark the row done because our own
    notification went through.

    The owner's letter is sent regardless of the confirmation's outcome — if
    the visitor's address bounces, that is precisely the thing worth knowing.

    Languages differ by recipient on purpose: the visitor is written to in the
    language the landing was in when they signed up (`entry.locale`, NULL for
    rows older than T_UX.9 → English), the owner in their own account language.

    Called by: `send_waitlist_emails`, `send_pending_waitlist_confirmations`.
    """
    from app.core.superuser import USER_ZERO_EMAIL
    from app.models.user import User
    from app.models.waitlist import WaitlistEntry

    delivered = False
    try:
        delivered = _send(entry.locale, entry.email, "waitlist_confirmation")
    except Exception:
        logger.exception("waitlist confirmation failed for %s", entry.email)

    if delivered:
        entry.confirmation_sent_at = datetime.now(timezone.utc)
        db.commit()

    owner = db.execute(
        select(User).where(User.email == USER_ZERO_EMAIL)
    ).scalar_one_or_none()
    strings = _catalogue_for(owner)
    try:
        _send(
            owner or DEFAULT_LOCALE,
            USER_ZERO_EMAIL,
            "waitlist_admin",
            email=entry.email,
            name=entry.name or "—",
            source=entry.source or "—",
            when=entry.created_at,
            total=db.execute(select(func.count(WaitlistEntry.id))).scalar(),
            confirmation=(
                strings["confirmation_sent"] if delivered
                else strings["confirmation_failed"]
            ),
        )
    except Exception:
        logger.exception("waitlist owner notification failed for %s", entry.email)

    return delivered


def _catalogue_for(user) -> dict:
    """The `waitlist_admin` strings in the owner's language.

    The delivered/failed verdict is a value inside a fact row, not a template
    branch, so it has to be looked up before rendering rather than chosen by
    the layout.

    Called by: `_send_waitlist_pair`.
    """
    from app.core.email_templates import DEFAULT_LOCALE as _d
    from app.core.email_templates import _catalogue

    tag = (getattr(user, "locale", None) or _d).split("-")[0].lower()
    cat = _catalogue(tag).get("waitlist_admin", {})
    fallback = _catalogue(_d)["waitlist_admin"]
    return {**fallback, **cat}


@celery_app.task(name="app.tasks.notifications.send_waitlist_emails")
def send_waitlist_emails(entry_id: str) -> None:
    """T_UX.8 — confirm to the person who signed up, and tell the owner.

    Runs as a task rather than inline for the reason `send_verification_code`
    does: `core.email.send_email` is synchronous `smtplib`, and the endpoint it
    is dispatched from is async — called in the request path it would hold the
    event loop for two SMTP round-trips while a stranger waits on a form.

    Idempotent by `confirmation_sent_at`: a redelivered task does not write to
    the same person twice.
    """
    from app.models.waitlist import WaitlistEntry

    with SyncSessionLocal() as db:
        entry = db.get(WaitlistEntry, entry_id)
        if not entry or entry.confirmation_sent_at:
            return
        _send_waitlist_pair(db, entry)


@celery_app.task(name="app.tasks.notifications.send_pending_waitlist_confirmations")
def send_pending_waitlist_confirmations(dry_run: bool = False) -> dict:
    """T_UX.8 — write to everyone who signed up before the letters existed.

    Run by hand, once, after deploy. There is no schedule behind it: it exists
    to close a backlog, and a recurring job that mails strangers is not
    something to leave ticking unattended.

    `dry_run=True` returns the addresses without sending. Mail cannot be
    unsent, and the list is small enough to read before committing to it.

    Safe to run twice: `confirmation_sent_at` is set per row as each letter
    lands, so a second run finds only what the first one failed to deliver.
    """
    from app.models.waitlist import WaitlistEntry

    with SyncSessionLocal() as db:
        pending = (
            db.execute(
                select(WaitlistEntry)
                .where(WaitlistEntry.confirmation_sent_at.is_(None))
                .order_by(WaitlistEntry.created_at)
            )
            .scalars()
            .all()
        )
        addresses = [e.email for e in pending]

        if dry_run:
            logger.info("waitlist backfill dry run: %s pending %s", len(pending), addresses)
            return {"pending": len(pending), "sent": 0, "failed": 0, "addresses": addresses}

        sent = 0
        for entry in pending:
            if _send_waitlist_pair(db, entry):
                sent += 1

        result = {
            "pending": len(pending),
            "sent": sent,
            "failed": len(pending) - sent,
            "addresses": addresses,
        }
        logger.info("waitlist backfill: %s", result)
        return result


@celery_app.task(name="app.tasks.notifications.send_password_reset")
def send_password_reset(user_id: str, token: str) -> None:
    """T_SEC.5 — deliver the reset link.

    Like the confirmation code, `notify_email` is not consulted: this is not a
    subscription, it is the answer to a request the person just made, and it is
    also how an owner learns that someone else asked.

    The token travels as an argument. It exists nowhere else in plaintext — the
    column holds a hash — and it must not be recomputed here, or the letter and
    the database would be able to disagree.

    Called by: `api/auth.forgot_password`.
    """
    import os

    from app.core.password_reset import reset_target
    from app.models.user import User

    base = os.getenv("VIMANA_PUBLIC_URL", "https://vimana.dealvault.club").rstrip("/")

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            return
        recipient = reset_target(user)
        if not recipient:
            return
        _send(
            user,
            recipient,
            "password_reset",
            cta_url=f"{base}/reset-password?token={token}",
        )


@celery_app.task(name="app.tasks.notifications.send_telegram_chat")
def send_telegram_chat(chat_id: str, kind: str, locale: str | None = None) -> None:
    """T_UX.12 pt.2 — answer someone who just talked to the bot.

    A task rather than an inline call from the webhook handler: `send_telegram`
    is synchronous `httpx`, and the handler is async — Telegram would be kept
    waiting on our round-trip to Telegram.

    Called by: `api/telegram.telegram_webhook`.
    """
    from app.core.email_templates import chat_message

    send_telegram(chat_id, chat_message(kind, locale))


@celery_app.task(name="app.tasks.notifications.notify_admins_scanner_down")
def notify_admins_scanner_down(detail: str) -> None:
    """T3.8 — the malware scanner is not answering; files are being queued.

    Goes to the administrators, not to the uploader: the person sending a photo
    has no action available and no reason to be told that our infrastructure is
    unwell. The throttle lives at the call site (`file_validation`), because
    that is where the storm would originate.
    """
    import os

    from app.core.telegram import send_telegram

    chat_ids = [c.strip() for c in os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    if not chat_ids:
        logger.warning("clamav down (%s) and no ADMIN_TELEGRAM_CHAT_IDS to tell", detail)
        return
    for chat_id in chat_ids:
        send_telegram(
            chat_id,
            "⚠️ Vimana · сканер загрузок не отвечает\n\n"
            f"{detail}\n\n"
            "Загрузки продолжают приниматься и складываются в очередь на "
            "проверку. Файлы в очереди доступны участникам непроверенными — "
            "это принятый размен, но чем дольше очередь, тем он дороже.",
        )


@celery_app.task(name="app.tasks.notifications.notify_admins_infected_file")
def notify_admins_infected_file(attachment_id: str, deal_id: str, signature: str) -> None:
    """T3.8 — a deferred scan found something in a file that is already stored.

    Owner's decision 2026-08-02: mark and tell a human, do not block the
    download automatically. So this message is the whole mechanism — if it is
    not read, nothing happens — and it says what to look at rather than what we
    did about it.
    """
    import os

    from app.core.telegram import send_telegram

    chat_ids = [c.strip() for c in os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    if not chat_ids:
        logger.error(
            "infected attachment %s in deal %s (%s) and no admin chat configured",
            attachment_id, deal_id, signature,
        )
        return
    for chat_id in chat_ids:
        send_telegram(
            chat_id,
            "🦠 Vimana · отложенная проверка нашла заражённый файл\n\n"
            f"Вложение: {attachment_id}\n"
            f"Сделка: {deal_id}\n"
            f"Сигнатура: {signature}\n\n"
            "Скачивание **не** заблокировано автоматически — решение за вами. "
            "Файл остаётся в хранилище: он часть цепи доказательств, и его "
            "удаление сделало бы проверку сделки неотличимой от подмены.",
        )


@celery_app.task(name="app.tasks.notifications.notify_admins_zap_findings")
def notify_admins_zap_findings(high: list[str], medium_count: int) -> None:
    """T_TEST.7 pt.1 — the passive scan found something at High.

    Dispatched by `app.cli.zap_report`, which is run by hand from
    `.zap/baseline.sh`. There is no schedule behind it on purpose: a scan needs
    a human to have chosen a target and a moment, and a weekly cron against
    production would be an unattended active-ish crawl nobody reads.

    The message carries the findings themselves, not a count and a link to a
    report file — the report lives on whichever machine ran the scan, and a
    pointer to a path on somebody's laptop is not an alert.
    """
    import os

    from app.core.telegram import send_telegram

    chat_ids = [c.strip() for c in os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "").split(",") if c.strip()]
    listing = "\n".join(f"• {item}" for item in high[:10])
    if len(high) > 10:
        listing += f"\n• …ещё {len(high) - 10}"

    if not chat_ids:
        logger.error("ZAP found %s High and no admin chat is configured:\n%s", len(high), listing)
        return

    for chat_id in chat_ids:
        send_telegram(
            chat_id,
            "🛡 Vimana · ZAP baseline нашёл High\n\n"
            f"{listing}\n\n"
            f"Medium в этом же прогоне: {medium_count}.\n"
            "Baseline — пассивный скан: это то, что видно снаружи без единого "
            "атакующего запроса.",
        )
