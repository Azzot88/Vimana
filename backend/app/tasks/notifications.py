from datetime import datetime, timedelta, timezone

from app.worker import celery_app
from app.core.database import SyncSessionLocal
from app.core.email import send_email
from app.core.telegram import send_telegram
from app.core.whatsapp import send_whatsapp

# Human-readable status labels (soft language per DESIGNGUIDELINES §9)
_STATUS_LABELS = {
    "matched":    "Ваша сделка согласована",
    "accepted":   "Перевозчик принял условия",
    "in_transit": "Груз в пути",
    "delivered":  "Груз доставлен — ожидает подтверждения",
    "confirmed":  "Доставка подтверждена",
    "closed":     "Сделка завершена",
}


def _notify_user(user, text: str) -> None:
    if user.notify_email and user.email:
        send_email(user.email, "Vimana · Sacred Logistics", text)
    if user.notify_telegram and user.telegram_chat_id:
        send_telegram(user.telegram_chat_id, text)
    if user.notify_whatsapp and user.whatsapp_number:
        send_whatsapp(user.whatsapp_number, text)


@celery_app.task(name="app.tasks.notifications.notify_deal_status")
def notify_deal_status(deal_id: str, status: str) -> None:
    from app.models.deal import Deal
    from app.models.user import User

    label = _STATUS_LABELS.get(status, status)

    with SyncSessionLocal() as db:
        deal = db.get(Deal, deal_id)
        if not deal:
            return
        sender = db.get(User, str(deal.sender_id))
        carrier = db.get(User, str(deal.carrier_id))

        msg = f"Vimana · {label}"
        if sender:
            _notify_user(sender, msg)
        if carrier and carrier.id != (sender.id if sender else None):
            _notify_user(carrier, msg)


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
            msg = "Vimana · Напоминаем — срок доставки истекает в ближайшие 24 часа."

            if sender:
                _notify_user(sender, msg)
            if carrier:
                _notify_user(carrier, msg)


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
        send_email(
            recipient,
            "Vimana · Код подтверждения",
            f"Ваш код подтверждения: {code}\n\n"
            "Код действителен 15 минут. Если вы его не запрашивали — "
            "просто проигнорируйте это письмо.",
        )


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
        send_email(
            user.email,
            "Vimana · Использован код восстановления",
            "В аккаунт вошли по коду восстановления.\n\n"
            f"Осталось неиспользованных кодов: {remaining}.\n\n"
            "Если это были вы — ничего делать не нужно. Если нет — войдите "
            "и создайте новый набор кодов: прежние перестанут работать.",
        )


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
        send_email(
            user.email,
            "Vimana · Ключ теперь только у вас",
            "Мы удалили свою копию ключа вашего аккаунта.\n\n"
            "С этого момента подписывать записи и открывать сейфы ваших сделок "
            "можете только вы — из файла Identity Vault или через расширение "
            "Nostr. Мы не сможем сделать это за вас.\n\n"
            "Если это были не вы — войдите и верните нашу копию из своего "
            "файла Identity Vault: страница «Доступ и ключи» в профиле.",
        )
