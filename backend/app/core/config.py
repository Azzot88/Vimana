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

    # T3.11 — E2E escape hatch. Comma-separated list of email domains whose
    # registrations are marked verified immediately, so the Playwright suite
    # (T_TEST.3) and the pytest suite can create deals without a mailbox.
    # MUST stay empty in production; `main.py` warns on startup if it is not.
    E2E_AUTO_VERIFY_EMAIL_DOMAINS: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""


settings = Settings()
