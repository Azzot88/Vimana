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

    # The live circuit: the mailbox real people are written from.
    SMTP_HOST: str = ""
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_PORT: int = 587

    # T_UX.9 pt.2 — the preview circuit, deliberately a *separate* set of
    # settings rather than a flag on the ones above. Pointing the live host at
    # a catcher would silence every real letter while `send_email` kept
    # returning True and rows kept being marked sent — the exact failure this
    # project spent a week tracing. Two circuits cannot be confused into each
    # other by editing one value.
    #
    # Unset → the admin page says the preview circuit is off and refuses to
    # send anything. Rendering a preview never touches either circuit.
    PREVIEW_SMTP_HOST: str = ""
    PREVIEW_SMTP_USER: str = ""
    PREVIEW_SMTP_PASSWORD: str = ""
    PREVIEW_SMTP_PORT: int = 1025

    # T3.11 — comma-separated email domains whose registrations are marked
    # verified immediately, so the e2e suites stop minting confirmation codes
    # nobody reads. Verification gates nothing, so this changes no behaviour
    # beyond the banner — but it MUST stay empty in production: a verified flag
    # is supposed to mean someone actually opened that mailbox. `main.py` warns
    # on startup if it is set.
    E2E_AUTO_VERIFY_EMAIL_DOMAINS: str = ""

    # T_TEST.8, 2026-08-22 — addresses `cleanup_e2e_users` must NOT delete,
    # comma-separated. The suite signs in as a long-lived account (registration
    # is code-based since T3.28 and cannot be automated), and that account lives
    # on the same `@e2e.vimana.local` domain the cleanup prunes after 24 hours.
    # Without this it would vanish every night and the next run would fail with
    # a 401 that looks like a new problem rather than the scheduled one.
    E2E_KEEP_EMAILS: str = ""

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
