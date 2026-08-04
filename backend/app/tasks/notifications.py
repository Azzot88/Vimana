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
        send_email(
            user.email,
            "Vimana · Личность завершена. Что теперь",
            "Ключ вашей личности объявлен утраченным. Подписывать новые записи "
            "вы больше не можете, но вход в аккаунт работает, а всё "
            "подписанное раньше остаётся в силе и проверяется.\n\n"
            "Осталось одно решение: сохранять ли вашу публичную страницу.\n\n"
            f"Если ничего не делать, {ends_at_iso} она останется открытой, и "
            "выбор зафиксируется. Если хотите её закрыть — войдите и выберите "
            "это до указанной даты; отменить закрытие потом будет нельзя.\n\n"
            "Ничего не удаляется ни в одном случае: цепь, подписи и события "
            "сделок остаются, потому что они наполовину принадлежат вашим "
            "контрагентам. Закрывается только витрина.\n\n"
            "Если вы потеряете и доступ к аккаунту, выбирать будет некому и "
            "сработает то же самое: страница останется.",
        )


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
