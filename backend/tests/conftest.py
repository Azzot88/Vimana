import base64
import os
import uuid
from datetime import datetime, timedelta, timezone

# Disable rate limiting before importing app modules that read the env at import time.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
# T_TEST speed: bcrypt with 4 rounds (~1 ms vs ~250 ms at prod's 12). Applies
# ONLY to this pytest process — the running backend keeps hashing real user
# passwords at 12 rounds. Same algorithm, verify path identical.
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# Deterministic AES-256 key for tests. Prod value must be set via env.
os.environ.setdefault(
    "MESSAGE_ENCRYPTION_KEY",
    base64.b64encode(b"vimana-test-key-32-bytes-length!").decode(),
)
# T2.2 — separate key for user nsec (never share with MESSAGE_ENCRYPTION_KEY).
os.environ.setdefault(
    "NSEC_ENCRYPTION_KEY",
    base64.b64encode(b"vimana-nsec-key-32-bytes-length!").decode(),
)
# T3.11 — verification gates nothing, so the suite would pass either way. Both
# test domains are auto-verified anyway so ~70 registrations stop minting and
# bcrypt-hashing codes nobody reads. `test_email_verification.py` registers on
# a domain outside this list where it needs the real flow.
os.environ.setdefault(
    "E2E_AUTO_VERIFY_EMAIL_DOMAINS", "vimana.test,e2e.vimana.local"
)
# T3.25 pt.2 — the suite must not be able to reach a real channel. Set with
# `environ[...] =`, not `setdefault`: pytest runs inside the backend container
# with the production `.env` loaded, so a default would lose to it. Without
# this, a test that exercises the "scanner is down" path sends a genuine
# Telegram alert to the owner — which it did, the day the bot was configured.
# Same lesson as the fuzzer unsetting the production webhook: a suite that can
# touch production is the code's problem, not the suite's.
os.environ["ADMIN_TELEGRAM_CHAT_IDS"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_WEBHOOK_SECRET"] = ""

# T3.12 pt.3 — the platform's trip-publishing key. Deterministic and valid
# (below the secp256k1 order); tests that need it absent clear it themselves.
os.environ.setdefault("PLATFORM_PUBLISH_NSEC", "1" * 64)

import psycopg2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.deal import Deal, DealStatus
from app.models.marketplace import Category, DEFAULT_CATEGORIES, Order, OrderStatus, Trip, TripStatus
from app.models.user import User


def _derive_test_url() -> str:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base, _, _ = settings.DATABASE_URL.rpartition("/")
    return f"{base}/vimana_test"


TEST_DATABASE_URL = _derive_test_url()

SEED_CARRIER_EMAIL = "seed-carrier@vimana.test"
SEED_SENDER_EMAIL = "seed-sender@vimana.test"
SEED_PASSWORD = "seed-password-123"


def _ensure_test_database() -> None:
    sync_url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    _, _, rest = sync_url.partition("://")
    creds, _, host_db = rest.partition("@")
    user, _, password = creds.partition(":")
    host_port, _, dbname = host_db.partition("/")
    host, _, port = host_port.partition(":")
    port = port or "5432"

    conn = psycopg2.connect(
        dbname="postgres", user=user, password=password, host=host, port=port
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
    if not cur.fetchone():
        cur.execute(f'CREATE DATABASE "{dbname}"')
    cur.close()
    conn.close()


async def _seed_default_categories(engine) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        result = await db.execute(select(Category))
        existing = {c.name_key for c in result.scalars().all()}
        for key in DEFAULT_CATEGORIES:
            if key in existing:
                continue
            db.add(Category(name_key=key, is_default=True, usage_count=0))
        await db.commit()


async def _migrate_orders_category_to_string(engine) -> None:
    """T1.17 schema fix: orders.category enum → VARCHAR(50). Idempotent."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='orders' AND column_name='category'"
                )
            )
        ).fetchone()
        if row and row[0] == "USER-DEFINED":
            await conn.execute(
                text(
                    "ALTER TABLE orders ALTER COLUMN category TYPE VARCHAR(50) USING category::text"
                )
            )
            await conn.execute(text("DROP TYPE IF EXISTS ordercategory"))


async def _ensure_connections_unique(engine) -> None:
    """T1.19 schema fix: UNIQUE(user_id, connected_user_id) on connections. Idempotent."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint "
                    "WHERE conname = 'uq_connections_user_connected'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "DELETE FROM connections a USING connections b "
                    "WHERE a.id > b.id AND a.user_id = b.user_id "
                    "AND a.connected_user_id = b.connected_user_id"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE connections ADD CONSTRAINT uq_connections_user_connected "
                    "UNIQUE (user_id, connected_user_id)"
                )
            )


async def _ensure_role_column(engine) -> None:
    """T1.24 pt.1 schema fix: users.role varchar; drop legacy booleans."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='role'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN role VARCHAR(20) "
                    "NOT NULL DEFAULT 'user'"
                )
            )

        for legacy_col, role_value in (
            ("is_arbiter", "arbiter"),
            ("is_superuser", "superuser"),
        ):
            exists = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{legacy_col}'"
                    )
                )
            ).fetchone()
            if exists:
                await conn.execute(
                    text(
                        f"UPDATE users SET role = '{role_value}' "
                        f"WHERE {legacy_col} = true AND role = 'user'"
                    )
                )
                await conn.execute(
                    text(f"ALTER TABLE users DROP COLUMN {legacy_col}")
                )


async def _ensure_dual_role(engine) -> None:
    """T1.24 schema fix: can_carry / can_send / active_mode; drop legacy is_carrier."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("can_carry", "ALTER TABLE users ADD COLUMN can_carry BOOLEAN NOT NULL DEFAULT true"),
            ("can_send", "ALTER TABLE users ADD COLUMN can_send BOOLEAN NOT NULL DEFAULT true"),
            ("active_mode", "ALTER TABLE users ADD COLUMN active_mode VARCHAR(10) NOT NULL DEFAULT 'sender'"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(text(ddl))

        legacy = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='is_carrier'"
                )
            )
        ).fetchone()
        if legacy:
            await conn.execute(
                text(
                    "UPDATE users SET can_carry = is_carrier, "
                    "active_mode = CASE WHEN is_carrier THEN 'carrier' ELSE 'sender' END "
                    "WHERE active_mode = 'sender'"
                )
            )
            await conn.execute(text("ALTER TABLE users DROP COLUMN is_carrier"))


async def _ensure_trust_tables(engine) -> None:
    """T2.4 schema fix: trust_edges + 3 denormalized counts on users."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'trustedgekind'")
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "CREATE TYPE trustedgekind AS ENUM "
                    "('peer_verified', 'dealt_with', 'invited')"
                )
            )

        for col, ddl in (
            ("verifications_issued_count", "INTEGER NOT NULL DEFAULT 0"),
            ("verifications_received_count", "INTEGER NOT NULL DEFAULT 0"),
            ("dealt_with_count", "INTEGER NOT NULL DEFAULT 0"),
        ):
            r = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not r:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))

        r = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'trust_edges'"
                )
            )
        ).fetchone()
        if not r:
            await conn.execute(
                text(
                    """
                    CREATE TABLE trust_edges (
                        id UUID PRIMARY KEY,
                        from_user_id UUID NOT NULL REFERENCES users(id),
                        to_user_id UUID NOT NULL REFERENCES users(id),
                        kind trustedgekind NOT NULL,
                        weight FLOAT NOT NULL DEFAULT 1.0,
                        source_ref VARCHAR(64),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        revoked_at TIMESTAMPTZ,
                        CONSTRAINT uq_trust_edge_pair_kind_source
                            UNIQUE (from_user_id, to_user_id, kind, source_ref)
                    )
                    """
                )
            )


async def _ensure_verification_tables(engine) -> None:
    """T2.1 schema fix: 4 tables + users.highest_verification_level + 7 enums.
    Idempotent — safe to re-run when tests reset schema."""
    enums = [
        ("verificationlevel", ["auto", "peer", "kyc"]),
        (
            "verificationrequeststatus",
            [
                "pending", "later_in_person", "declined", "declined_polite",
                "verified", "escalated",
            ],
        ),
        ("verificationtargetrole", ["sender", "carrier"]),
        ("sanctionsstatus", ["clean", "match", "review_needed"]),
        ("ownerrole", ["sender", "carrier", "both"]),
        ("storagemode", ["encrypted_blob", "zk_snark"]),
        (
            "verificationsource",
            ["auto_ocr", "peer", "arbiter_review", "kyc_provider"],
        ),
    ]
    async with engine.begin() as conn:
        for name, values in enums:
            row = (
                await conn.execute(
                    text("SELECT 1 FROM pg_type WHERE typname = :n").bindparams(n=name)
                )
            ).fetchone()
            if not row:
                inner = ", ".join(f"'{v}'" for v in values)
                await conn.execute(text(f"CREATE TYPE {name} AS ENUM ({inner})"))

        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='users' AND column_name='highest_verification_level'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN highest_verification_level VARCHAR(10)"
                )
            )

        for table_sql in (
            """CREATE TABLE IF NOT EXISTS identity_containers (
                id UUID PRIMARY KEY,
                owner_id UUID NOT NULL REFERENCES users(id),
                owner_role ownerrole NOT NULL DEFAULT 'both',
                storage_mode storagemode NOT NULL DEFAULT 'encrypted_blob',
                blob_encrypted BYTEA NOT NULL,
                blob_nonce BYTEA NOT NULL,
                doc_hash VARCHAR(64) NOT NULL,
                doc_country VARCHAR(2),
                doc_type VARCHAR(32),
                sanctions_check_status sanctionsstatus NOT NULL DEFAULT 'clean',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",
            """CREATE TABLE IF NOT EXISTS verification_requests (
                id UUID PRIMARY KEY,
                deal_id UUID NOT NULL REFERENCES deals(id),
                requested_by_id UUID NOT NULL REFERENCES users(id),
                target_role verificationtargetrole NOT NULL,
                status verificationrequeststatus NOT NULL DEFAULT 'pending',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )""",
            """CREATE TABLE IF NOT EXISTS verification_badges (
                id UUID PRIMARY KEY,
                subject_id UUID NOT NULL REFERENCES users(id),
                level verificationlevel NOT NULL,
                source verificationsource NOT NULL,
                container_ref_id UUID REFERENCES identity_containers(id),
                verified_by_id UUID REFERENCES users(id),
                in_deal_id UUID REFERENCES deals(id),
                verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ
            )""",
            """CREATE TABLE IF NOT EXISTS sanctions_list (
                id SERIAL PRIMARY KEY,
                source VARCHAR(32) NOT NULL,
                name_normalized VARCHAR(255) NOT NULL,
                dob VARCHAR(10),
                country VARCHAR(2),
                added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",
        ):
            await conn.execute(text(table_sql))


async def _ensure_nostr_keypair_columns(engine) -> None:
    """T2.2 schema fix: nsec_encrypted / nsec_nonce / key_self_custody. Idempotent."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("nsec_encrypted", "BYTEA"),
            ("nsec_nonce", "BYTEA"),
            ("key_self_custody", "BOOLEAN NOT NULL DEFAULT false"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))


async def _ensure_email_verification_columns(engine) -> None:
    """T3.11 schema fix: email verification state + password_hash nullable.
    Mirrors migration 0028, plus `pending_email` from 0032. Idempotent."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("email_verified_at", "TIMESTAMPTZ"),
            ("email_verification_code_hash", "VARCHAR(255)"),
            ("email_verification_expires_at", "TIMESTAMPTZ"),
            ("email_verification_attempts", "SMALLINT NOT NULL DEFAULT 0"),
            ("email_verification_sent_at", "TIMESTAMPTZ"),
            # T3.15 (migration 0032) — address awaiting proof during a change.
            ("pending_email", "VARCHAR(255)"),
            # T3.15 (migration 0033) — cutoff that retires older sessions.
            ("sessions_valid_from", "TIMESTAMPTZ"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
        await conn.execute(
            text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
        )


async def _ensure_webauthn_table(engine) -> None:
    """T3.14 schema fix: webauthn_credentials. Mirrors migration 0031.
    Idempotent — `create_all` builds it, this covers a pre-existing test DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS webauthn_credentials (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    credential_id BYTEA NOT NULL UNIQUE,
                    public_key BYTEA NOT NULL,
                    sign_count BIGINT NOT NULL DEFAULT 0,
                    transports JSONB,
                    aaguid VARCHAR(36),
                    device_name VARCHAR(100),
                    backed_up BOOLEAN NOT NULL DEFAULT false,
                    uv_capable BOOLEAN,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    last_used_at TIMESTAMPTZ
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_webauthn_credentials_user_id "
                "ON webauthn_credentials (user_id)"
            )
        )


async def _ensure_identity_columns(engine) -> None:
    """T3.12 pt.1 schema fix: users.key_lost_at + unique npub +
    trips.nostr_published_by_pubkey. Mirrors migration 0029. Idempotent."""
    async with engine.begin() as conn:
        for table, col, ddl in (
            ("users", "key_lost_at", "TIMESTAMPTZ"),
            # T3.21 — mirrors migration 0036.
            ("users", "identity_file_released_at", "TIMESTAMPTZ"),
            # T3.23 — mirrors migration 0037.
            ("users", "previous_nostr_pubkey", "VARCHAR(64)"),
            ("users", "identity_changed_at", "TIMESTAMPTZ"),
            # T3.18 — mirrors migration 0038.
            ("users", "public_profile", "VARCHAR(16) NOT NULL DEFAULT 'full'"),
            # T3.19 — mirrors migration 0039. No default on `archive_choice`:
            # NULL means the owner has not answered, and a default would put
            # words in their mouth on every existing row.
            ("users", "archive_notice_seen_at", "TIMESTAMPTZ"),
            ("users", "archive_choice", "VARCHAR(8)"),
            # T3.8 — mirrors migration 0040. `pending` for existing rows is the
            # honest default: nothing stored before this ever went past a
            # scanner, and the rescan task is meant to find exactly those.
            ("attachments", "scan_status", "VARCHAR(10) NOT NULL DEFAULT 'pending'"),
            ("attachments", "scanned_at", "TIMESTAMPTZ"),
            ("trips", "nostr_published_by_pubkey", "VARCHAR(64)"),
            # T3.12 pt.2b — mirrors migration 0030.
            ("identity_containers", "key_envelope", "TEXT"),
            ("identity_containers", "key_envelope_sender_pubkey", "VARCHAR(64)"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='{table}' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                )
        await conn.execute(
            text(
                "DO $$ BEGIN "
                "ALTER TABLE users ADD CONSTRAINT uq_users_nostr_pubkey "
                "UNIQUE (nostr_pubkey); "
                "EXCEPTION WHEN duplicate_table THEN NULL; "
                "WHEN duplicate_object THEN NULL; "
                "END $$;"
            )
        )


async def _ensure_notices_tables(engine) -> None:
    """T_UX.2 schema fix: routestatus / noticeseverity / noticesurface enums
    + route_notes + platform_notices tables. Idempotent."""
    async with engine.begin() as conn:
        for enum_name, values in (
            ("routestatus", ["standard", "attention", "complex", "restricted"]),
            ("noticeseverity", ["info", "warning", "alert"]),
            ("noticesurface", ["footer", "trip_card", "deal_page", "all"]),
        ):
            existing = (
                await conn.execute(
                    text(f"SELECT 1 FROM pg_type WHERE typname = '{enum_name}'")
                )
            ).fetchone()
            if not existing:
                inner = ", ".join(f"'{v}'" for v in values)
                await conn.execute(text(f"CREATE TYPE {enum_name} AS ENUM ({inner})"))
        for tbl, ddl in (
            (
                "route_notes",
                """
                CREATE TABLE route_notes (
                    id UUID PRIMARY KEY,
                    origin_iso VARCHAR(3) NOT NULL,
                    destination_iso VARCHAR(3) NOT NULL,
                    status routestatus NOT NULL DEFAULT 'standard',
                    severity noticeseverity NOT NULL DEFAULT 'info',
                    headline VARCHAR(500) NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    active_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    active_until TIMESTAMPTZ,
                    created_by UUID REFERENCES users(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
            ),
            (
                "platform_notices",
                """
                CREATE TABLE platform_notices (
                    id UUID PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    severity noticeseverity NOT NULL DEFAULT 'info',
                    target_surface noticesurface NOT NULL DEFAULT 'all',
                    headline VARCHAR(500) NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    active_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    active_until TIMESTAMPTZ,
                    created_by UUID REFERENCES users(id),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """,
            ),
        ):
            exists = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.tables WHERE table_name='{tbl}'"
                    )
                )
            ).fetchone()
            if not exists:
                await conn.execute(text(ddl))

        # T_UX.2 pt.4: migrate legacy tables that were created with i18n_key
        # columns to direct-text schema. Idempotent — no-op if already migrated.
        for tbl in ("route_notes", "platform_notices"):
            await conn.execute(
                text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS headline VARCHAR(500) NOT NULL DEFAULT ''")
            )
            await conn.execute(
                text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''")
            )
        for legacy_col, new_col in (
            ("headline_i18n_key", "headline"),
            ("body_i18n_key", "body"),
        ):
            has_col = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name='route_notes' AND column_name=:c"
                    ),
                    {"c": legacy_col},
                )
            ).fetchone()
            if has_col:
                await conn.execute(
                    text(f"UPDATE route_notes SET {new_col} = {legacy_col} WHERE {new_col} = ''")
                )
                await conn.execute(text(f"ALTER TABLE route_notes DROP COLUMN {legacy_col}"))


async def _ensure_receiving_addresses(engine) -> None:
    """T_UX.4 A schema fix: `receiving_addresses` table + partial-unique
    index on (user_id) WHERE is_default. Idempotent."""
    async with engine.begin() as conn:
        exists = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'receiving_addresses'"
                )
            )
        ).fetchone()
        if not exists:
            await conn.execute(
                text(
                    """
                    CREATE TABLE receiving_addresses (
                        id UUID PRIMARY KEY,
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        label VARCHAR(60) NOT NULL,
                        country_iso VARCHAR(2) NOT NULL,
                        city VARCHAR(150),
                        city_geoname_id INTEGER,
                        street VARCHAR(255),
                        postal_code VARCHAR(20),
                        note VARCHAR(500),
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX ix_receiving_addresses_user_id ON receiving_addresses(user_id)"
                )
            )
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_receiving_addresses_user_default "
                    "ON receiving_addresses(user_id) WHERE is_default IS TRUE"
                )
            )


async def _ensure_deal_participants(engine) -> None:
    """T3.3 schema fix: dealparticipantrole enum + deal_participants table."""
    async with engine.begin() as conn:
        exists_type = (
            await conn.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'dealparticipantrole'")
            )
        ).fetchone()
        if not exists_type:
            await conn.execute(
                text("CREATE TYPE dealparticipantrole AS ENUM ('recipient')")
            )
        exists_table = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name='deal_participants'"
                )
            )
        ).fetchone()
        if not exists_table:
            await conn.execute(
                text(
                    """
                    CREATE TABLE deal_participants (
                        id UUID PRIMARY KEY,
                        deal_id UUID NOT NULL REFERENCES deals(id),
                        user_id UUID REFERENCES users(id),
                        role dealparticipantrole NOT NULL DEFAULT 'recipient',
                        invited_by UUID NOT NULL REFERENCES users(id),
                        invite_token VARCHAR(64) NOT NULL UNIQUE,
                        invited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        accepted_at TIMESTAMPTZ,
                        revoked_at TIMESTAMPTZ,
                        CONSTRAINT uq_participant_deal_user_role UNIQUE (deal_id, user_id, role)
                    )
                    """
                )
            )


async def _ensure_publish_metrics_table(engine) -> None:
    """T3.5 pt.2 schema fix: publish_metrics single-row counter. Idempotent."""
    async with engine.begin() as conn:
        exists = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name='publish_metrics'"
                )
            )
        ).fetchone()
        if not exists:
            await conn.execute(
                text(
                    """
                    CREATE TABLE publish_metrics (
                        id UUID PRIMARY KEY,
                        success_count BIGINT NOT NULL DEFAULT 0,
                        error_count BIGINT NOT NULL DEFAULT 0,
                        last_attempt_at TIMESTAMPTZ
                    )
                    """
                )
            )


async def _ensure_trip_nostr_columns(engine) -> None:
    """T3.5 schema fix: nostr_event_id + nostr_published_at on trips. Idempotent."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("nostr_event_id", "VARCHAR(64)"),
            ("nostr_published_at", "TIMESTAMPTZ"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='trips' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(text(f"ALTER TABLE trips ADD COLUMN {col} {ddl}"))


async def _ensure_operator_access_grants(engine) -> None:
    """T3.2 schema fix: operator_access_grants table. Idempotent."""
    async with engine.begin() as conn:
        exists = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name='operator_access_grants'"
                )
            )
        ).fetchone()
        if not exists:
            await conn.execute(
                text(
                    """
                    CREATE TABLE operator_access_grants (
                        id UUID PRIMARY KEY,
                        dispute_id UUID NOT NULL REFERENCES disputes(id),
                        granted_by UUID NOT NULL REFERENCES users(id),
                        granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        revoked_at TIMESTAMPTZ,
                        CONSTRAINT uq_grant_dispute_party UNIQUE (dispute_id, granted_by)
                    )
                    """
                )
            )


async def _ensure_threshold_columns(engine) -> None:
    """T2.3 schema fix: is_e2e / wrapped_shares / read_packages on
    deal_vault_messages. Idempotent."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("is_e2e", "BOOLEAN NOT NULL DEFAULT false"),
            ("wrapped_shares", "JSONB"),
            ("read_packages", "JSONB"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='deal_vault_messages' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(
                    text(f"ALTER TABLE deal_vault_messages ADD COLUMN {col} {ddl}")
                )


async def _ensure_nostr_event_columns(engine) -> None:
    """T2.2 pt.2 schema fix: NIP-01 event_id / created_at / pubkey on
    deal_vault_messages and deal_events. Idempotent."""
    async with engine.begin() as conn:
        for tbl in ("deal_vault_messages", "deal_events"):
            for col, ddl in (
                ("nostr_event_id", "VARCHAR(64)"),
                ("nostr_created_at", "BIGINT"),
                ("nostr_pubkey", "VARCHAR(64)"),
            ):
                row = (
                    await conn.execute(
                        text(
                            f"SELECT 1 FROM information_schema.columns "
                            f"WHERE table_name='{tbl}' AND column_name='{col}'"
                        )
                    )
                ).fetchone()
                if not row:
                    await conn.execute(
                        text(f"ALTER TABLE {tbl} ADD COLUMN {col} {ddl}")
                    )


async def _ensure_receiving_address_columns(engine) -> None:
    """T_UX.4 B schema fix: `avatar_key` on users. Idempotent.

    The six `receiving_*` columns left this mirror with migration 0041: the
    single-address fields were dropped after the read fallback proved
    unreachable (T_KEYS.1). The long-lived test DB keeps whatever columns it
    already has — harmless, since nothing reads them any more."""
    async with engine.begin() as conn:
        for col, ddl in (
            ("avatar_key", "VARCHAR(255)"),
        ):
            row = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='users' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not row:
                await conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
                )


async def _ensure_recovery_codes(engine) -> None:
    """T3.16 schema mirror: `recovery_codes`. Mirrors migration 0035.
    Idempotent — `create_all` builds it, this covers a pre-existing test DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS recovery_codes (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code_hash VARCHAR(255) NOT NULL,
                    used_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_recovery_codes_user_hash "
                "ON recovery_codes (user_id, code_hash)"
            )
        )


async def _ensure_hot_path_indexes(engine) -> None:
    """T_PERF.1 schema mirror: indexes from migration 0034.

    `create_all` builds indexes only for tables it creates, and these tables all
    predate the migration — so without this the test database would keep drifting
    from production exactly where the plans differ. Idempotent, and cheap on
    tables this size."""
    async with engine.begin() as conn:
        for name, target in (
            ("ix_deals_sender_id", "deals (sender_id)"),
            ("ix_deals_carrier_id", "deals (carrier_id)"),
            ("ix_trips_status_created", "trips (status, created_at, id)"),
            ("ix_trips_carrier_id", "trips (carrier_id)"),
            (
                "ix_deal_vault_messages_deal_created",
                "deal_vault_messages (deal_id, created_at, id)",
            ),
            ("ix_attachments_message_id", "attachments (message_id)"),
            (
                "ix_inquiry_messages_inquiry_created",
                "inquiry_messages (inquiry_id, created_at, id)",
            ),
            ("ix_trust_edges_to_user_id", "trust_edges (to_user_id)"),
            (
                "ix_verification_requests_deal_id",
                "verification_requests (deal_id)",
            ),
            (
                "ix_verification_badges_subject_id",
                "verification_badges (subject_id)",
            ),
        ):
            await conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))


async def _ensure_inquiry_tables(engine) -> None:
    """T1.22 schema fix: trip_inquiries + inquiry_messages. Idempotent."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'trip_inquiries'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "CREATE TABLE trip_inquiries ("
                    "id UUID PRIMARY KEY, "
                    "trip_id UUID NOT NULL REFERENCES trips(id), "
                    "sender_id UUID NOT NULL REFERENCES users(id), "
                    "carrier_id UUID NOT NULL REFERENCES users(id), "
                    "deal_id UUID REFERENCES deals(id), "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
                    "CONSTRAINT uq_trip_inquiries_trip_sender UNIQUE (trip_id, sender_id))"
                )
            )
        row = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'inquiry_messages'"
                )
            )
        ).fetchone()
        if not row:
            await conn.execute(
                text(
                    "CREATE TABLE inquiry_messages ("
                    "id UUID PRIMARY KEY, "
                    "inquiry_id UUID NOT NULL REFERENCES trip_inquiries(id), "
                    "sender_id UUID NOT NULL REFERENCES users(id), "
                    "text_ciphertext BYTEA, "
                    "text_nonce BYTEA, "
                    "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                )
            )


async def _ensure_encrypted_messages(engine) -> None:
    """T1.21 schema fix: drop legacy `text` column, ensure BYTEA pair exists."""
    async with engine.begin() as conn:
        for col in ("text_ciphertext", "text_nonce"):
            check = (
                await conn.execute(
                    text(
                        f"SELECT 1 FROM information_schema.columns "
                        f"WHERE table_name='deal_vault_messages' AND column_name='{col}'"
                    )
                )
            ).fetchone()
            if not check:
                await conn.execute(
                    text(
                        f"ALTER TABLE deal_vault_messages ADD COLUMN {col} BYTEA"
                    )
                )
        legacy = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='deal_vault_messages' AND column_name='text'"
                )
            )
        ).fetchone()
        if legacy:
            await conn.execute(
                text("ALTER TABLE deal_vault_messages DROP COLUMN text")
            )


async def _ensure_dealevent_types(engine) -> None:
    """T1.23: extend DealEventType enum with dispute/arbiter values. Idempotent."""
    async with engine.begin() as conn:
        for value in ("dispute_opened", "arbiter_opened", "dispute_resolved"):
            await conn.execute(
                text(f"ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS '{value}'")
            )


async def _ensure_vault_completeness(engine) -> None:
    """T3.7/T3.9: vault-content event types + deal seal + anchor backend +
    identity_doc attachment kind. Mirrors migrations 0026 + 0027. Idempotent."""
    async with engine.begin() as conn:
        for value in ("message_added", "file_added", "sealed", "identity_ref"):
            await conn.execute(
                text(f"ALTER TYPE dealeventtype ADD VALUE IF NOT EXISTS '{value}'")
            )
        await conn.execute(
            text("ALTER TYPE attachmentkind ADD VALUE IF NOT EXISTS 'identity_doc'")
        )
        await conn.execute(
            text("ALTER TABLE deals ADD COLUMN IF NOT EXISTS sealed_at TIMESTAMPTZ NULL")
        )
        await conn.execute(
            text(
                "ALTER TABLE deal_chain_anchors ADD COLUMN IF NOT EXISTS backend "
                "VARCHAR(16) NOT NULL DEFAULT 'nostr'"
            )
        )


async def _ensure_contact_tables(engine) -> None:
    """T3.25: user_contacts + verification_challenges. Mirrors migration 0045.
    Idempotent — `create_all` builds them, this covers a pre-existing test DB
    and, crucially, the *partial* unique index, which `create_all` does not
    know about because it lives only in the migration."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_contacts_verified "
                "ON user_contacts (channel, value) WHERE verified_at IS NOT NULL"
            )
        )


async def _ensure_password_reset_columns(engine) -> None:
    """T_SEC.5: users.password_reset_hash + _expires_at. Mirrors migration 0044.
    Idempotent — `create_all` builds them, this covers a pre-existing test DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "password_reset_hash VARCHAR(255)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "password_reset_expires_at TIMESTAMPTZ"
            )
        )


async def _ensure_locale_columns(engine) -> None:
    """T_UX.9: users.locale + waitlist.locale. Mirrors migration 0043.
    Idempotent — `create_all` builds them, this covers a pre-existing test DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "locale VARCHAR(5) NOT NULL DEFAULT 'en'"
            )
        )
        await conn.execute(
            text("ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS locale VARCHAR(5)")
        )


async def _ensure_waitlist_confirmation_column(engine) -> None:
    """T_UX.8: waitlist.confirmation_sent_at. Mirrors migration 0042.
    Idempotent — `create_all` builds it, this covers a pre-existing test DB."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "ALTER TABLE waitlist ADD COLUMN IF NOT EXISTS "
                "confirmation_sent_at TIMESTAMPTZ NULL"
            )
        )


async def _ensure_deal_event_chain(engine) -> None:
    """T3.6: seq/entry_hash/prev_hash on deal_events + deal_chain_anchors.

    Mirrors migration 0025 for the long-lived `vimana_test` database, which
    `create_all` cannot alter. Rows left over from earlier runs are chained in
    `(timestamp, id)` order using the production hash function, so the NOT NULL
    constraint can be applied without dropping test history.
    """
    import json as _json

    from app.core.deal_chain import compute_entry_hash

    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='deal_events' AND column_name='entry_hash'"
                )
            )
        ).fetchone()
        if existing:
            return

        await conn.execute(text("ALTER TABLE deal_events ADD COLUMN seq BIGINT"))
        await conn.execute(text("ALTER TABLE deal_events ADD COLUMN entry_hash BYTEA"))
        await conn.execute(text("ALTER TABLE deal_events ADD COLUMN prev_hash BYTEA"))

        rows = (
            await conn.execute(
                text(
                    "SELECT id::text AS id, deal_id::text AS deal_id, "
                    "event_type::text AS event_type, actor_id::text AS actor_id, "
                    "nostr_event_id, payload::text AS payload, timestamp "
                    "FROM deal_events ORDER BY deal_id, timestamp, id"
                )
            )
        ).fetchall()

        seq_by_deal: dict[str, int] = {}
        prev_by_deal: dict[str, bytes | None] = {}
        for row in rows:
            seq = seq_by_deal.get(row.deal_id, 0) + 1
            seq_by_deal[row.deal_id] = seq
            prev_hash = prev_by_deal.get(row.deal_id)
            entry_hash = compute_entry_hash(
                deal_id=uuid.UUID(row.deal_id),
                seq=seq,
                timestamp=row.timestamp,
                event_type=row.event_type,
                actor_id=uuid.UUID(row.actor_id) if row.actor_id else None,
                nostr_event_id=row.nostr_event_id,
                payload=_json.loads(row.payload) if row.payload is not None else None,
                prev_hash=prev_hash,
            )
            # asyncpg can't infer parameter type when the same $N sits in
            # both branches of a CASE (NULL is untyped, decode()→bytea). Split.
            if prev_hash is None:
                await conn.execute(
                    text(
                        "UPDATE deal_events SET seq = :seq, "
                        "entry_hash = decode(:entry_hash, 'hex'), "
                        "prev_hash = NULL "
                        "WHERE id = :id"
                    ),
                    {"seq": seq, "entry_hash": entry_hash.hex(), "id": row.id},
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE deal_events SET seq = :seq, "
                        "entry_hash = decode(:entry_hash, 'hex'), "
                        "prev_hash = decode(:prev_hash, 'hex') "
                        "WHERE id = :id"
                    ),
                    {
                        "seq": seq,
                        "entry_hash": entry_hash.hex(),
                        "prev_hash": prev_hash.hex(),
                        "id": row.id,
                    },
                )
            prev_by_deal[row.deal_id] = entry_hash

        await conn.execute(text("ALTER TABLE deal_events ALTER COLUMN seq SET NOT NULL"))
        await conn.execute(
            text("ALTER TABLE deal_events ALTER COLUMN entry_hash SET NOT NULL")
        )
        await conn.execute(
            text(
                "ALTER TABLE deal_events ADD CONSTRAINT uq_deal_events_deal_seq "
                "UNIQUE (deal_id, seq)"
            )
        )


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    _ensure_test_database()
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_orders_category_to_string(engine)
    await _ensure_connections_unique(engine)
    await _ensure_role_column(engine)
    await _ensure_dealevent_types(engine)
    await _ensure_deal_event_chain(engine)
    await _ensure_vault_completeness(engine)
    await _ensure_encrypted_messages(engine)
    await _ensure_inquiry_tables(engine)
    await _ensure_dual_role(engine)
    await _ensure_receiving_address_columns(engine)
    await _ensure_nostr_keypair_columns(engine)
    await _ensure_email_verification_columns(engine)
    await _ensure_identity_columns(engine)
    await _ensure_webauthn_table(engine)
    await _ensure_nostr_event_columns(engine)
    await _ensure_threshold_columns(engine)
    await _ensure_operator_access_grants(engine)
    await _ensure_trip_nostr_columns(engine)
    await _ensure_publish_metrics_table(engine)
    await _ensure_deal_participants(engine)
    await _ensure_notices_tables(engine)
    await _ensure_receiving_addresses(engine)
    await _ensure_verification_tables(engine)
    await _ensure_trust_tables(engine)
    await _ensure_recovery_codes(engine)
    await _ensure_hot_path_indexes(engine)
    await _ensure_waitlist_confirmation_column(engine)
    await _ensure_locale_columns(engine)
    await _ensure_password_reset_columns(engine)
    await _ensure_contact_tables(engine)
    await _seed_default_categories(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_maker(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def override_db(session_maker):
    async def _get_test_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)


# `redis.asyncio` finalizers firing on a dead loop are filtered in `pytest.ini`
# — see the comment on the `AbstractConnection.__del__` entry there.
#
# A `sys.unraisablehook` used to live here and did nothing at all: pytest's
# `unraisableexception` plugin swaps that hook out around every test item, so a
# hook installed at conftest import time is only in place *between* tests, which
# is not where these fire. Two lessons worth keeping: chaining that hook is not
# a usable mechanism under pytest, and a suppression nobody verified is
# indistinguishable from no suppression at all.


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def _close_redis_clients():
    """Shut the shared Redis client down while its loop is still alive.

    pytest-asyncio gives each test a fresh loop and closes it afterwards. A
    Redis connection left for the garbage collector then raises inside its own
    finalizer — `loop.call_soon()` on a closed loop — which pytest reports as
    `PytestUnraisableExceptionWarning`, one per Redis call made after the first
    loop died. Both `token_blacklist` and `challenge` share one client, so
    closing it here covers every consumer.

    `loop_scope="function"` is the whole point. `pytest.ini` sets
    `asyncio_default_fixture_loop_scope = session`, so without it this fixture
    runs in the *session* loop while the app under test ran in the *function*
    loop — `aclose_current()` would look up the session loop, find nothing, and
    return having closed exactly zero clients. Three separate attempts at these
    warnings failed because of that, all of them operating on an empty dict in
    the wrong loop.
    """
    yield
    from app.core.redis_client import aclose_current

    await aclose_current()


@pytest.fixture(autouse=True)
def sync_sessions(monkeypatch):
    """Point every Celery-task module's `SyncSessionLocal` at the TEST database.

    `app.core.database.SyncSessionLocal` is built from `settings.DATABASE_URL`
    — production. Overriding the async `get_db` dependency does not touch it,
    so any task invoked directly from a test talks to live data. That is not
    theoretical: on 2026-07-26 `cleanup_e2e_users` ran unpatched during a suite
    run and deleted 22 real accounts from prod, cascading through their deals,
    messages and trust edges.

    Patching the *importing modules* rather than `app.core.database` matters —
    each of them did `from app.core.database import SyncSessionLocal` and holds
    its own reference. Autouse so a new task module cannot quietly reintroduce
    the hole; add it to the tuple below when one appears.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        TEST_DATABASE_URL.replace("+asyncpg", "+psycopg2"), pool_pre_ping=True
    )
    maker = sessionmaker(engine, expire_on_commit=False)

    from app.core import uba as core_uba
    from app.tasks import (
        chain_anchor,
        cleanup,
        nostr_publish,
        nostr_whitelist,
        notifications,
        uba as tasks_uba,
    )

    for module in (
        chain_anchor,
        cleanup,
        nostr_publish,
        nostr_whitelist,
        notifications,
        tasks_uba,
        core_uba,
    ):
        if hasattr(module, "SyncSessionLocal"):
            monkeypatch.setattr(module, "SyncSessionLocal", maker)

    # Yielded so tests that seed rows for a task can use the very same binding
    # instead of reaching for `app.core.database.SyncSessionLocal` themselves.
    yield maker
    engine.dispose()


@pytest.fixture(autouse=True)
def _mute_celery(monkeypatch):
    from app.api import deals as deals_module

    class _NoopTask:
        def delay(self, *args, **kwargs):
            return None

    monkeypatch.setattr(deals_module, "notify_deal_status", _NoopTask())


async def _get_or_create_user(
    db: AsyncSession,
    *,
    email: str,
    display_name: str,
    can_carry: bool = True,
    can_send: bool = True,
    active_mode: str = "sender",
) -> User:
    from app.core.keypair import encrypt_nsec, generate_keypair

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user:
        changed = False
        # T2.1/T2.2 backfill for seed users created before keypair migration.
        # Idempotent: only fills what's missing, never rotates existing key.
        if not user.nostr_pubkey or user.nsec_encrypted is None:
            nsec_hex, npub_hex = generate_keypair()
            nonce, ct = encrypt_nsec(nsec_hex)
            user.nostr_pubkey = npub_hex
            user.nsec_encrypted = ct
            user.nsec_nonce = nonce
            user.key_self_custody = False
            changed = True
        # Speed: rehash seeds stored at prod's 12 rounds down to the test-env
        # cost (bcrypt embeds rounds in the hash, so old hashes stay slow to
        # verify on every login regardless of BCRYPT_ROUNDS).
        if not user.password_hash.startswith("$2b$04$"):
            user.password_hash = hash_password(SEED_PASSWORD)
            changed = True
        # T3.11 — seeds predate email verification. Nothing depends on the flag
        # behaviourally, but leaving them unverified would misrepresent the
        # fixture state in any test that reads `/me`.
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(timezone.utc)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)
        return user
    # T2.2 — seed users get a custodial keypair too so signing + container
    # encryption paths work in tests without touching /register.
    nsec_hex, npub_hex = generate_keypair()
    nonce, ct = encrypt_nsec(nsec_hex)

    user = User(
        email=email,
        password_hash=hash_password(SEED_PASSWORD),
        display_name=display_name,
        can_carry=can_carry,
        can_send=can_send,
        active_mode=active_mode,
        nostr_pubkey=npub_hex,
        nsec_encrypted=ct,
        nsec_nonce=nonce,
        key_self_custody=False,
        email_verified_at=datetime.now(timezone.utc),  # T3.11
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture(scope="session")
async def seed_carrier(session_maker) -> User:
    async with session_maker() as db:
        return await _get_or_create_user(
            db,
            email=SEED_CARRIER_EMAIL,
            display_name="Seed Carrier",
            can_carry=True,
            active_mode="carrier",
        )


@pytest_asyncio.fixture(scope="session")
async def seed_sender(session_maker) -> User:
    async with session_maker() as db:
        return await _get_or_create_user(
            db,
            email=SEED_SENDER_EMAIL,
            display_name="Seed Sender",
            can_carry=False,
            active_mode="sender",
        )


@pytest_asyncio.fixture(scope="session")
async def seed_trip(session_maker, seed_carrier) -> Trip:
    async with session_maker() as db:
        result = await db.execute(
            select(Trip).where(
                Trip.carrier_id == seed_carrier.id,
                Trip.origin == "SEED-ORIGIN",
                Trip.destination == "SEED-DEST",
            )
        )
        trip = result.scalars().first()
        if trip:
            return trip
        trip = Trip(
            carrier_id=seed_carrier.id,
            origin="SEED-ORIGIN",
            destination="SEED-DEST",
            depart_at=datetime.now(timezone.utc) + timedelta(days=7),
            capacity=5.0,
            allowed_categories=["document"],
            status=TripStatus.open,
        )
        db.add(trip)
        await db.commit()
        await db.refresh(trip)
        return trip


@pytest_asyncio.fixture(scope="session")
async def seed_deal(session_maker, seed_carrier, seed_sender, seed_trip) -> Deal:
    async with session_maker() as db:
        result = await db.execute(
            select(Deal).where(
                Deal.trip_id == seed_trip.id,
                Deal.sender_id == seed_sender.id,
            )
        )
        deal = result.scalars().first()
        if deal:
            return deal
        order = Order(
            sender_id=seed_sender.id,
            recipient_contact="+10000000000",
            origin=seed_trip.origin,
            destination=seed_trip.destination,
            category="document",
            declared_value=100.0,
            currency="USD",
            description="Seed order",
            status=OrderStatus.matched,
            trip_id=seed_trip.id,
        )
        db.add(order)
        await db.flush()
        deal = Deal(
            order_id=order.id,
            trip_id=seed_trip.id,
            sender_id=seed_sender.id,
            carrier_id=seed_carrier.id,
            status=DealStatus.matched,
        )
        db.add(deal)
        await db.commit()
        await db.refresh(deal)
        return deal


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/auth/login", json={"login": email, "password": SEED_PASSWORD}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest_asyncio.fixture
async def carrier_headers(client, seed_carrier) -> dict[str, str]:
    token = await _login(client, seed_carrier.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sender_headers(client, seed_sender) -> dict[str, str]:
    token = await _login(client, seed_sender.email)
    return {"Authorization": f"Bearer {token}"}


async def service_nsec_for_email(session_maker, email: str) -> str:
    """Read an account's **service** nsec the way the platform reads it.

    For tests that need to encrypt or sign as a user while leaving the account
    custodial. `POST /me/keypair/export` used to serve this and is gone (T3.12):
    it handed the user a key that was never theirs, and the flows below are
    precisely the ones where the platform — not the user — holds it.

    Doing it through the DB instead of an endpoint keeps that honest. There is
    no API for this because no user should have one.
    """
    from app.core.keypair import decrypt_nsec

    async with session_maker() as db:
        user = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one()
        return decrypt_nsec(bytes(user.nsec_nonce), bytes(user.nsec_encrypted))


async def establish_identity(client: AsyncClient, headers: dict[str, str]) -> dict:
    """Give this account its own key the way the app does, and hand the test the
    private half. Returns `{"nsec_hex", "npub_hex"}`.

    Replaces the old `POST /me/keypair/export` + `POST /me/keypair/claim` pair
    the crypto suite used to get a known nsec and flip a user to self-custody.
    Both are gone (T3.12): `export` handed over a key that was never the user's,
    and `claim` promoted a key the platform had held all along — an identity
    built on it is sovereign only on our word.

    This does what a real client does: generate locally, prove possession over a
    one-time challenge, send only the public half. The returned nsec is known to
    the test because the *test* generated it, not because the server disclosed
    anything — which is the property the whole phase is about.

    Note the account's npub **changes** here. Read any npub after calling this,
    never before.
    """
    from app.core.identity_proof import PURPOSE_ESTABLISH, proof_event_id
    from app.core.keypair import generate_keypair, sign_event_id

    nsec_hex, npub_hex = generate_keypair()

    ch = await client.post("/api/me/identity/challenge", headers=headers)
    ch.raise_for_status()
    challenge = ch.json()["challenge"]

    created_at = int(datetime.now(timezone.utc).timestamp())
    event_id = proof_event_id(npub_hex, PURPOSE_ESTABLISH, challenge, created_at)
    resp = await client.post(
        "/api/me/identity/establish",
        headers=headers,
        json={
            "npub_hex": npub_hex,
            "challenge": challenge,
            "created_at": created_at,
            "sig": sign_event_id(event_id, nsec_hex),
        },
    )
    resp.raise_for_status()
    return {"nsec_hex": nsec_hex, "npub_hex": npub_hex}


async def step_up_token(
    client: AsyncClient,
    headers: dict[str, str],
    scope: str,
    password: str = SEED_PASSWORD,
) -> str:
    """Obtain a step-up grant with a password proof (T3.15).

    For tests whose subject is the guarded operation rather than the
    confirmation itself. The other two proofs — passkey and Nostr signature —
    are exercised in `test_step_up.py`.
    """
    resp = await client.post(
        "/api/auth/step-up/verify",
        headers=headers,
        json={"scope": scope, "password": password},
    )
    resp.raise_for_status()
    return resp.json()["step_up_token"]


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@vimana.test"
