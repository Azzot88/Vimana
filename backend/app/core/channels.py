"""T3.26/T3.27 — one way to ask "send this code there", for every channel.

Five transports, one signature. The abstraction is written whole; which
channels are *live* is a matter of environment variables, because that depends
on external accounts and A2P registrations rather than on architecture. Email
works today, Telegram works today, the rest wait for paperwork.

**A channel proves the thing it delivers to, not the thing the user typed.**
This corrects the plan written in Phase 3.8 and is the most important line in
the file. The deep-link Telegram flow was described there as a way to confirm a
*phone*: the visitor types a number, gets `t.me/bot?start=…`, presses Start and
is confirmed. But pressing Start proves control of a **Telegram account** — it
says nothing about the number typed a minute earlier. Confirming a phone that
way would let anyone type somebody else's number and have the platform record
it as proven.

So the channels split by what they can honestly attest:

- `email` → proves the email address.
- `telegram` → proves the **Telegram chat**, never a phone. Usable to link
  Telegram as a contact, and to deliver a code to an account that already has
  one; not usable to confirm a number.
- `telegram_gateway`, `sms`, `whatsapp` → deliver to the number itself, and so
  do prove the number.

Functions (PROJECT §6.2a):
- `enabled(channel)` — is this transport switched on. Called by: `available_for`,
  `deliver`, `api/auth.channels`.
- `available_for(identifier)` — channels that can prove this identifier.
  Called by: `api/auth.channels`, `api/auth.request_contact_code`.
- `deliver(channel, value, code, locale)` — hand the code to the transport.
  Called by: `tasks/notifications.send_channel_code`.
- `proves(channel)` — which contact channel a success confirms.
  Called by: `api/auth.confirm_contact_code`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.contacts import normalize

EMAIL = "email"
TELEGRAM = "telegram"
TELEGRAM_GATEWAY = "telegram_gateway"
SMS = "sms"
WHATSAPP = "whatsapp"

#: Channels that deliver to a phone number, and therefore can prove one.
PHONE_CHANNELS = (TELEGRAM_GATEWAY, SMS, WHATSAPP)

#: One env flag per channel. Presence of the flag is the whole switch — there
#: is deliberately no second "configured" setting that could disagree with it.
_FLAGS = {
    EMAIL: "CHANNEL_EMAIL_ENABLED",
    TELEGRAM: "CHANNEL_TELEGRAM_ENABLED",
    TELEGRAM_GATEWAY: "CHANNEL_TELEGRAM_GATEWAY_ENABLED",
    SMS: "CHANNEL_SMS_ENABLED",
    WHATSAPP: "CHANNEL_WHATSAPP_ENABLED",
}

#: Email and Telegram are on unless switched off; the three that need an
#: external account or A2P registration are off unless switched on. A default
#: that turns on a channel nobody has paid for would fail at the worst moment —
#: in front of a person trying to sign in.
_DEFAULTS = {EMAIL: True, TELEGRAM: True, TELEGRAM_GATEWAY: False, SMS: False, WHATSAPP: False}


@dataclass(frozen=True)
class Delivery:
    """What happened when a code was handed to a transport.

    `link` exists because Telegram is not symmetric with the others: a bot
    cannot write to somebody who has never written to it, so the "delivery" is
    a link the person opens. Modelling that as a failed send, or as a second
    kind of endpoint, would push the asymmetry into every caller.
    """

    sent: bool
    link: str | None = None


def enabled(channel: str) -> bool:
    raw = os.getenv(_FLAGS.get(channel, ""), "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return _DEFAULTS.get(channel, False)


def available_for(identifier: str) -> list[str]:
    """Channels that can honestly confirm this identifier.

    An email address has exactly one; a phone number has the three that reach
    the number itself. `telegram` is absent from the phone list on purpose —
    see the module docstring: it proves a chat, not a number.
    """
    if normalize(EMAIL, identifier):
        return [EMAIL] if enabled(EMAIL) else []
    if normalize(SMS, identifier):
        return [c for c in PHONE_CHANNELS if enabled(c)]
    return []


def proves(channel: str) -> str:
    """The contact channel a successful code confirms.

    `telegram_gateway` delivers over Telegram but attests a **phone**, so it
    confirms an `sms` contact. Keeping that mapping here rather than at the
    call site is what stops the two from drifting.
    """
    return SMS if channel == TELEGRAM_GATEWAY else channel


def deliver(channel: str, value: str, code: str, locale: str | None) -> Delivery:
    """Hand the code to the transport. Never raises for a disabled channel.

    Returns `Delivery(sent=False)` rather than throwing, because "this channel
    is off" is an ordinary answer at a call site that is already deciding what
    to tell the user — and an exception would tempt that call site into
    distinguishing failures it must not distinguish out loud.
    """
    if not enabled(channel):
        return Delivery(sent=False)

    if channel == EMAIL:
        from app.core.email import send_email
        from app.core.email_templates import render

        letter = render("verification_code", locale, code=code)
        return Delivery(sent=send_email(value, letter.subject, letter.text, letter.html))

    if channel == TELEGRAM:
        # `value` is a chat id: this path is for an account that already linked
        # Telegram. Linking itself goes through the deep link, which is issued
        # by the endpoint, not here — the bot cannot start a conversation.
        from app.core.telegram import send_telegram
        from app.core.email_templates import render

        letter = render("verification_code", locale, code=code)
        send_telegram(value, letter.text)
        return Delivery(sent=True)

    # The three that wait on paperwork. Written as explicit refusals rather than
    # left to fall through: a channel that silently does nothing is how a
    # feature comes to look configured while delivering nothing (T1.7).
    if channel in (TELEGRAM_GATEWAY, SMS, WHATSAPP):
        return Delivery(sent=False)

    return Delivery(sent=False)
