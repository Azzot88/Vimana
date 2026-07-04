from app.core.config import settings


def send_whatsapp(to: str, body: str) -> None:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN or not to:
        return
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            from_=f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
            to=f"whatsapp:{to}",
            body=body,
        )
    except Exception:
        pass
