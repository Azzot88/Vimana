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
    from app.models.user import User

    with SyncSessionLocal() as db:
        user = db.get(User, user_id)
        if not user or not user.email:
            return
        send_email(
            user.email,
            "Vimana · Код подтверждения",
            f"Ваш код подтверждения: {code}\n\n"
            "Код действителен 15 минут. Если вы его не запрашивали — "
            "просто проигнорируйте это письмо.",
        )
