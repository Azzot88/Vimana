from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    SECRET_KEY: str
    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: str = "*"

    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_ENDPOINT: str = ""

    SMTP_HOST: str = ""
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_PORT: int = 587

    # T3.11 — comma-separated email domains whose registrations are marked
    # verified immediately, so the e2e suites stop minting confirmation codes
    # nobody reads. Verification gates nothing, so this changes no behaviour
    # beyond the banner — but it MUST stay empty in production: a verified flag
    # is supposed to mean someone actually opened that mailbox. `main.py` warns
    # on startup if it is set.
    E2E_AUTO_VERIFY_EMAIL_DOMAINS: str = ""

    # T3.14 — WebAuthn. `RP_ID` must equal the site's domain (or a parent of
    # it), and `ORIGIN` must match the browser's origin exactly, scheme
    # included. Get either wrong and the browser aborts the ceremony on its own
    # side — the server sees nothing at all, which makes it a miserable thing to
    # debug. Defaults are the dev ones, prod sets them in `.env`.
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "Vimana"
    WEBAUTHN_ORIGIN: str = "http://localhost:5173"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""


settings = Settings()
