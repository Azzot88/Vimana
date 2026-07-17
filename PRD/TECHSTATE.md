# Vimana — Sacred Logistics · TECHSTATE.md

> FILL ──────────────────────────────
> Назначение: детальное состояние системы, связи компонентов, принятые tech-решения (Decision Log) и обнаруженная логика (Capture Discovered Logic).
> Когда обновлять: при изменении логики/моделей и каждый раз, когда разобрался, как работает блок системы (до завершения задачи).
> Что НЕ дублировать: стек/версии/инфра (живут в ENVIRONMENT), стратегию (MASTERPLAN), задачи (TASKS).
> Формат записи: Status — отметка готовности; Decision Log — Решение / Причина / Дата; Обнаруженная логика — Механика → файлы реализации.
> ───────────────────────────────────

---

## 1. Status (готовность блоков)

| Блок | Фаза | Статус |
|---|---|---|
| Инфраструктура / Docker / БД | 0 | ✅ готово |
| FastAPI + SQLAlchemy + Alembic | 1 | ✅ готово |
| Доменные модели (все 9 таблиц + миграция) | 1 | ✅ готово |
| Auth + Социальный граф (Invite, Connections) | 1 | ✅ готово |
| Маркетплейс (Рейсы, Заявки, Мэтчинг) | 1 | ✅ готово |
| Сделка (lifecycle + DealEvent) | 1 | ✅ готово |
| DealVault (чат + фото + лог, IPFS-ready) | 1 | ✅ готово |
| Frontend SPA (React + Vite + Tailwind) | 1 | ✅ готово |
| Уведомления (email + Telegram + WhatsApp) | 1 | ✅ готово (T1.7) |
| Интернационализация (i18n, 6 языков EN/UA/RU/PL/FR/ES) | 1 | ✅ готово (T1.9, T1.13) |
| База аэропортов + геолокация (Haversine, D11) | 1 | ✅ готово (T1.10, T1.16) |
| Мобильная версия (responsive + BottomNav) | 1 | ✅ готово (T1.12) |
| Телефон в профиль (убран из регистрации) | 1 | ✅ готово (T1.11) |
| Расширяемые категории (Category модель + autocomplete) | 1 | ✅ готово (T1.17) |
| Waitlist + публичный Landing | 1 | ✅ готово (T1.18) |
| SSL / HTTPS / staging deploy | 1 | ✅ готово (T1.8) |
| Pre-production hardening (race conditions, upload security, rate-limit, exception handler, cursor pagination) | 1 | ✅ готово (T1.19) |
| Cloudflare R2 / S3 storage для DealVault-аттачей | 1 | ✅ готово (T1.20) |
| At-rest AES-256-GCM шифрование DealVault-сообщений | 1 | ✅ готово (T1.21, переходно к T2.3) |
| Inquiry chat panel (TripInquiry + InquiryMessage) | 1 | ✅ готово (T1.22) |
| User Zero + Arbiter role + Dispute model (базовая механика) | 1→3 | ✅ готово (T1.23; полная Фаза 3 — позже) |
| Dual role (can_carry/can_send/active_mode) + RBAC (Permission enum + Role) | 1 | ✅ готово (T1.24) |
| NewTripPage redesign (Bento + hook-points для EXP-03/04) | 1 | ✅ готово (T1.25) |
| Receiving Address в профиле + share-in-chat | 1 | ✅ готово (T1.26) |
| Peer Identity Verification (P2P KYC) | 2 | ✅ MVP (T2.1: backend + frontend, custodial only. OCR/OFAC — stub, self-custody 422 до T2.3) |
| Trust Graph (Web-of-Trust) | 2 | ✅ MVP (T2.4: TrustEdge + auto dealt_with/invited + BFS endpoints + denormalized counts + UI. Follow-up: Redis-кэш, UserBadge на TripCard) |
| Keypair + Nostr-совместимость (D10: A+D) | 2 | ✅ MVP (pt.1 custodial + UI; pt.2 NIP-01 event format + NIP-07 signing + Claim self-custody end-to-end) |
| Threshold 2-of-3 encryption (замена at-rest из T1.21) | 2 | ⬜ не начато (T2.3) |
| Уровень Бизнес-Активности (УБА) | 3 | ⬜ не начато (T3.1) |
| Vimana Nostr Relay (strfry) + Federation | 3.5 | ⬜ не начато (T3.5) |
| Regulatory KYC/AML + Санкционный периметр коридоров | 4 | ⬜ не начато (T4.1) |
| Карточные платежи | 4 | ⬜ не начато (T4.2) |
| Эскроу BTC + Залог | 5 | ⬜ не начато |
| USDT-эскроу | 5 | ⬜ не начато |
| Премиум | 6 | ⬜ не начато |
| DealVault → IPFS | 6 | ⬜ не начато |
| Полная Nostr + IPFS портативность | 6 | ⬜ не начато |
| ZK-Proof of Verification | 6 | ⬜ не начато (T6.4) |

*(Обновлять по мере выполнения: ⬜ → 🟨 в работе → ✅ готово.)*

---

## 2. Decision Log (Решение / Причина / Дата)

| # | Решение | Причина | Дата |
|---|---|---|---|
| D1 | Стек: FastAPI + SQLAlchemy(async) + PostgreSQL + R2/S3 | Выбор владельца; зрелость, async, ACID для сделок | 2026-06 |
| D2 | Эскроу BTC по схеме 2-of-3 multisig (образец HodlHodl); платформа держит только ключ арбитра | Не-кастодиальность снижает регуляторный риск money-transmitter | 2026-06 |
| D3 | Вместо репутации — Уровень Бизнес-Активности (частота × оценочная стоимость × размер залога) | Метрика делом, устойчивее к накрутке отзывами | 2026-06 |
| D4 | Фазы = функциональные блоки (простое+важное → сложное); V1 = только Ядро доверия без денег/эскроу | Быстрый честный MVP, повторяющий работающий рынок | 2026-06 |
| D5 | Иммутабельная запись доставки переименована в **DealVault** (ранее «Чёрный ящик»). Ядро Vimana и будущих проектов. IPFS-ready с Фазы 1 | Авиа-метафора + vault = tamper-proof хранилище; легко портируется в IPFS | 2026-06-27 |
| D6 (open) | Админ/операторская панель: Django Admin vs SQLAlchemy-совместимая (SQLAdmin/Piccolo/starlette-admin) | Django ORM конфликтует с SQLAlchemy-стеком; решить до Фазы 3 | TBD |
| D7 (open) | USDT-эскроу: целевая сеть и контрактная схема не-кастодиальной 2-of-3 | BTC-multisig не переносится 1-в-1 на USDT; проектировать в Фазе 5 | TBD |
| D8 (open) | Портативность: формат экспортируемого пакета — IPFS DAG + Nostr events | DealVault как Nostr event JSON → пин в IPFS → CID = верификационный хеш; реализация в Фазе 6 | TBD |
| D9 (open) | Docker-only dev как жёсткое правило (да/нет) | Подтвердить владельцем; влияет на онбординг исполнителей | TBD |
| D11 | **Геолокация аэропортов: Haversine в Python.** Датасет OpenFlights (~7 000 аэропортов) загружается в память при старте бэкенда. Расстояние до ближайших считается формулой Haversine без внешних API и без PostGIS | Датасет мал (< 1 МБ); Haversine даёт ответ за микросекунды; Redis GEO и PostGIS избыточны | 2026-06-28 |
| D10 | **Nostr-совместимость: Вариант A + D.** Платформа генерирует secp256k1-keypair при регистрации и хранит зашифрованно. Пользователь «забирает» nsec в любой момент → платформа удаляет свою копию. Если обнаружен NIP-07 браузерный extension (Alby, nos2x) — Vimana использует его для подписи вместо custodial ключа | Масс-маркет онбординг без барьеров + поддержка существующей Nostr-идентичности для продвинутых пользователей | 2026-06-27 |
| D-NOSTR-RELAY | **Vimana Nostr Relay = strfry** (C++ от hoytech, LMDB storage). Дeploy как отдельный контейнер `nostr-relay` в docker-compose. Event kind для trip = **NIP-99 30402** (Classified Listing, replaceable per `d`-tag) — совместим с существующими Nostr-клиентами. Federation = **whitelist friendly relays** (publish only, subscribe отложен до Фазы 4+). Auth NIP-42, rate-limit 30 events/hour per pubkey, WoT-gate из T2.4 | strfry — production-ready, лёгкий (~50 MB idle), нативная поддержка нужных NIP-ов; NIP-99 = стандартный marketplace-формат (уже понят damus/amethyst/coracle); publish-only федерация — предсказуемее subscribe с точки зрения spam/moderation | 2026-07-12 |
| D-NOSTR-FEDERATION (open) | Конкретный whitelist friendly relays (env `NOSTR_FRIENDLY_RELAYS`) | Стартовый набор: damus.io, nostr.wine, relay.nostr.band. Ревизия каждые 3-6 месяцев по популярности и uptime | TBD (Фаза 3.5) |
| D-TRANSLATION (open) | Провайдер on-the-fly перевода Nostr-описаний для мультиязычного UI | Варианты: **Claude Haiku** (~$0.0002/call, стабильно), **DeepL Free API** (500k символов/мес, бесплатно), **локальный NLLB** (0 стоимость, но 3+ GB модель). Кэш в Redis TTL 30 дней по `(event_id, target_lang)`. Уточнить при подходе к T3.5 | TBD (Фаза 3.5) |

---

## 2b. D10 — Реализация Nostr-совместимости (принято: A + D)

> Решение зафиксировано. Реализация в Фазе 2 (T2.2).

### Механика (Вариант A — кастодиальный старт)

1. При регистрации: генерируется secp256k1-keypair (`nsec` + `npub`).
2. `nsec` хранится зашифрованно на сервере (AES-256-GCM, ключ шифрования в env/KMS — не в БД). `npub` записывается в `User.nostr_pubkey`.
3. DealVault-события (`DealVaultMessage`, `DealEvent`) подписываются server-side: `sig = schnorr_sign(event_hash, nsec)`.
4. Пользователь может в любой момент: **экспортировать** `nsec` (после подтверждения пароля/2FA) → платформа после подтверждения **удаляет** зашифрованный `nsec` и проставляет `User.key_self_custody = true`.
5. После self-custody: подпись событий происходит client-side (пользователь передаёт подписанный event) или через NIP-07 (Вариант D).
6. Импорт существующего `nsec`: пользователь вводит свой ключ → он заменяет сгенерированный; платформа сразу помечает `key_self_custody = true` (не хранит чужой nsec).

### Механика (Вариант D — NIP-07 override)

1. Frontend при загрузке проверяет `window.nostr` (NIP-07 API).
2. Если extension обнаружен: `npub` запрашивается через `window.nostr.getPublicKey()`, сравнивается с `User.nostr_pubkey`. Если совпадает — подпись через `window.nostr.signEvent()`. Если нет — предложить «использовать extension-ключ» (импорт npub).
3. Signing flow: frontend формирует Nostr event object → отправляет в extension для подписи → получает `sig` → отправляет на сервер с уже готовой подписью.
4. Сервер верифицирует подпись через `pubkey` перед сохранением.

### API-эндпоинты (добавить в Фазе 2)
- `GET /api/me/keypair/status` — custodial / self-custody, npub.
- `POST /api/me/keypair/export` — получить зашифрованный nsec (требует re-auth).
- `POST /api/me/keypair/claim` — подтвердить self-custody (платформа удаляет nsec).
- `POST /api/me/keypair/import` — импортировать существующий npub/nsec.

### Поле в User (добавить в Фазе 2)
- `key_self_custody: bool = False` — True означает, что nsec у платформы отсутствует.

---

## 3. Обнаруженная логика (Capture Discovered Logic)

> Заполняется по ходу: **Механика → файлы реализации.** Пусто до начала разработки.

| Механика | Где реализовано (файлы) |
|---|---|
| FastAPI app + /health + CORS + роутеры + lifespan (User Zero promote) | `backend/app/main.py` |
| Настройки (pydantic-settings) | `backend/app/core/config.py` |
| JWT (HS256, 30д), bcrypt | `backend/app/core/security.py` |
| get_current_user dependency + is_superuser helper | `backend/app/api/deps.py` |
| Auth API: register/login/me + normalize/case-insensitive/trim (T1.15) | `backend/app/api/auth.py` |
| Invite + Connection API + /me/invites (T1.14) | `backend/app/api/social.py` |
| Trips API (POST/GET + фильтры) — `can_carry` check (T1.24) | `backend/app/api/trips.py` |
| Deals API (match/accept/event/confirm) + DealEvent append-only + inquiry.deal_id linking (T1.22) | `backend/app/api/deals.py` |
| DealVault API (чат + upload) — MAX 10MB, streaming SHA-256, MIME whitelist (T1.19) | `backend/app/api/dealvault.py` |
| Inquiry API (TripInquiry + InquiryMessage) | `backend/app/api/inquiries.py` |
| Admin API (Dispute + Vault access + Users) — все через require_perm() | `backend/app/api/admin.py` |
| RBAC: Permission enum + Role + perms_of() + require_perm() FastAPI dep (T1.24 pt.1) | `backend/app/core/permissions.py` |
| Waitlist API + Telegram admin notify (T1.18) | `backend/app/api/waitlist.py` |
| Categories API (search + auto-create on match, T1.17) | `backend/app/api/categories.py` |
| Airports API (search + nearest + cascade country→city→airport, T1.10/T1.16) | `backend/app/api/airports.py`, `backend/app/core/airports.py` |
| Telegram bot webhook + linking через /start {token} (T1.7) | `backend/app/api/telegram.py`, `backend/app/core/telegram.py` |
| R2/S3 клиент + health check (T1.20) | `backend/app/core/storage.py` |
| AES-256-GCM at-rest шифрование (T1.21) — property-facade `text` на модели | `backend/app/core/crypto.py`, `backend/app/models/deal.py` |
| Cursor pagination utils Page[T] (T1.19) | `backend/app/core/pagination.py` |
| slowapi rate-limit + X-Forwarded-For key (T1.19) | `backend/app/core/rate_limit.py` |
| Global exception handler + X-Request-ID middleware + jsonable_encoder fix (T1.19) | `backend/app/main.py`, `backend/app/core/logging_setup.py` |
| Email + WhatsApp (Twilio) notifications | `backend/app/core/email.py`, `backend/app/core/whatsapp.py` |
| Celery worker + beat (notifications, dispute checks) | `backend/app/worker.py`, `backend/app/tasks/notifications.py` |
| Superuser (User Zero) startup promotion — idempotent | `backend/app/core/superuser.py` |
| Boarding pass PDF (WeasyPrint) | *(планируется, слот под T6.1)* |
| Async SQLAlchemy engine + Base + get_db() | `backend/app/core/database.py` |
| Alembic async migrations (0001–0010) | `backend/alembic/env.py`, `backend/alembic/versions/` |
| Все доменные модели (13 таблиц) | `backend/app/models/` |
| Изолированная тестовая БД `vimana_test` + идемпотентные seed-фикстуры | `backend/tests/conftest.py` |
| 140 backend-тестов (auth, trips, deals, dealvault, dealvault_attachments, arbiter, dual_role, permissions, hardening_block3/4/5, encryption, inquiry, notifications, race_conditions, social, telegram, waitlist, categories, airports) | `backend/tests/` |
| Frontend SPA — React 18 + Vite + TypeScript + Tailwind + i18n 6 языков | `frontend/src/` |
| Frontend RBAC: hasPerm() + Permission enum mirror | `frontend/src/lib/permissions.ts` |
| ModeSwitcher в Navbar (T1.24) + разный визуал Dashboard | `frontend/src/components/ModeSwitcher.tsx`, `pages/DashboardPage.tsx` |
| InquiryPanel — right-side drawer/panel с encrypted-at-rest badge | `frontend/src/components/InquiryPanel.tsx` |
| ImageLightbox — full-screen preview с Esc/click-outside close | `frontend/src/components/ImageLightbox.tsx` |
| Admin pages (`/admin/disputes`, `/admin/users`, `/admin/deals/:id/vault`) | `frontend/src/pages/Admin*.tsx` |
| Landing + Waitlist public route (T1.18) | `frontend/src/pages/LandingPage.tsx` |
| Frontend smoke-тесты (7 кейсов через vitest) | `frontend/src/test/`, `frontend/src/**/*.test.tsx` |
| Docker compose dev с nginx dynamic DNS resolver + SSL termination | `docker-compose.dev.yml`, `nginx/default.conf` |
| Nginx custom 502/503/504 page с auto-refresh + healthcheck-based startup (2026-07-14) | `nginx/_error.html`, `nginx/default.conf`, `docker-compose.dev.yml` |
| Vite build vendor chunk splitting (react/i18n/phone) — main bundle < 500 kB | `frontend/vite.config.ts`, `frontend/package.json` |
| Receiving Address helper (T1.26) + share-address message prefix `📍 SHARED ADDRESS` | `backend/app/core/address.py` |
| GeoNames city autocomplete (T1.26) — reuses `cities15000.txt` из T1.16 | `backend/app/core/cities.py`, `backend/app/api/cities.py` |
| Nostr keypair core (T2.2) — coincurve secp256k1, Schnorr sign/verify, AES-256-GCM wrap для nsec | `backend/app/core/keypair.py` |
| Signing helper (T2.2 pt.2) — NIP-01 event format (kind 4801 vault_message / 4802 deal_event), event_id per NIP-01, ±5 min clock-skew guard. Vault-message strict для self-custody (422 без sig); deal-event lenient (unsigned OK). Legacy pt.1 helpers сохранены | `backend/app/core/signing.py` |
| Keypair endpoints (T2.2) — /me/keypair/{status,export,claim,import} | `backend/app/api/keypair.py` |
| NIP-07 signing (T2.2 pt.2) — `signVaultMessageViaNip07(dealId, text, isSystem)` через `window.nostr.signEvent()`; api/dealvault.ts авто-подписывает если self-custody | `frontend/src/{lib/nostr,api/dealvault}.ts` |
| Claim self-custody UI (T2.2 pt.2) — кнопка + модалка с warn (амбер), доступна если `has_encrypted_nsec && nip07` | `frontend/src/components/KeypairSection.tsx` |
| Nostr event schema fields (T2.2 pt.2) — `nostr_event_id VARCHAR(64)`, `nostr_created_at BIGINT`, `nostr_pubkey VARCHAR(64)` на deal_vault_messages + deal_events (nullable для backward-compat pt.1 записей) | миграция `0015_nostr_event_format` |
| Verification container encryption (T2.1) — AES-256-GCM key = owner's nsec[:32], custodial-only | `backend/app/core/verification.py` |
| Verification endpoints (T2.1) — create/respond/submit/escalate/self-upload/public listing/revoke | `backend/app/api/verification.py` |
| Verification frontend components — VerificationSection (profile), VerificationBadgeChip, RequestModal, RespondModal | `frontend/src/components/Verification*.tsx` |
| Trust Graph core (T2.4) — BFS до глубины 6, sybil-guard, symmetric add_dealt_with/add_invited, refresh_trust_counts | `backend/app/core/trust.py` |
| Trust Graph endpoints (T2.4) — /me/trust-circle, /users/{id}/trust-metrics | `backend/app/api/trust.py` |
| Trust Graph auto-populate — dealt_with на confirm_deal, invited на accept_invite | `backend/app/api/{deals,social}.py` |
| Trust Circles UI (T2.4) — depth selector 1–6, counter tiles, hop list | `frontend/src/{api/trust,components/TrustCirclesSection}.tsx` |
| KeypairSection frontend — status/export/import UI + NIP-07 detection | `frontend/src/components/KeypairSection.tsx`, `frontend/src/lib/nostr.ts` |
| AddressForm / AddressCard — profile form + chat card render | `frontend/src/components/Address{Form,Card}.tsx` |

---

## 4. Ключевые модели данных / контракты (целевые)

**Фаза 1 (в prod)**
- `User(id, email?/phone?, password_hash?, display_name, can_carry, can_send, active_mode ∈ {sender, carrier}, role ∈ {user, arbiter, superuser}, nostr_pubkey?, business_activity_level?, notify_email/telegram/whatsapp, telegram_chat_id?, telegram_link_token?, whatsapp_number?, created_at)` — колонки `is_carrier`/`is_superuser`/`is_arbiter` удалены миграциями 0009/0010
- `InviteLink(id, creator_id→User, token, expires_at 14д, used_by→User?)`
- `Connection(id, user_id→User, connected_user_id→User, created_at)` — двусторонняя запись, UNIQUE(user_id, connected_user_id) из T1.19
- `Trip(id, carrier_id→User, origin, destination, depart_at, capacity, allowed_categories JSON, status)`
- `Order(id, sender_id→User, recipient_contact, origin, destination, category VARCHAR(50), declared_value, currency, description, deadline?, status, trip_id→Trip?)`
- `Deal(id, order_id→Order, trip_id→Trip, sender_id, carrier_id, recipient_id?, status ∈ {draft, matched, accepted, in_transit, delivered, confirmed, closed, disputed}, created_at)`
- `DealEvent(id, deal_id→Deal, event_type ∈ {…, dispute_opened, arbiter_opened, dispute_resolved}, payload JSON, actor_id, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, timestamp)` — **append-only**. T2.2 pt.2 добавил NIP-01 event поля (nullable); self-custody lenient — остаётся `None`.
- `DealVaultMessage(id, deal_id→Deal, sender_id?, text_ciphertext BYTEA, text_nonce BYTEA, is_system, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, created_at)` — **иммутабельно**, at-rest AES-256-GCM из T1.21; property `text` decrypt on access. T2.2 pt.2: для self-custody клиент подписывает через NIP-07 и передаёт sig+ts.
- `Attachment(id, message_id→DealVaultMessage, r2_key, file_hash SHA-256, ipfs_cid?, kind ∈ {handoff_photo, receipt_photo, doc, payment_receipt}, created_at)` — **иммутабельно**
- `Category(id, name_key UNIQUE, is_default, usage_count, created_at)` — T1.17
- `TripInquiry(id, trip_id→Trip, sender_id, carrier_id, deal_id?, created_at)` — UNIQUE(trip_id, sender_id), T1.22
- `InquiryMessage(id, inquiry_id→TripInquiry, sender_id, text_ciphertext, text_nonce, created_at)` — at-rest шифрование, T1.22
- `Dispute(id, deal_id→Deal UNIQUE, opened_by, arbiter_id?, reason, status ∈ {open, claimed, resolved}, verdict?, created_at, resolved_at?)` — T1.23
- `WaitlistEntry(id, email UNIQUE, name?, source, created_at)` — T1.18
- *(User расширение T1.26)*: `receiving_country_iso?`, `receiving_city?`, `receiving_city_geoname_id?`, `receiving_street?`, `receiving_postal_code?`, `receiving_note?` — **приватные**, отдаются только через `GET /me`, никогда в list-endpoints (например `/admin/users` их не возвращает)

**Фаза 2 (частично в prod)**

> **Реализовано** (миграции 0012 + 0013): keypair per user, verification MVP.
> **Планируется**: T2.2 pt.2 NIP-07, T2.3 threshold, T2.4 trust graph.

- User расширение T2.2: `nostr_pubkey` (уже был), `nsec_encrypted BYTEA`, `nsec_nonce BYTEA`, `key_self_custody: bool = False`. Custodial nsec шифрован AES-256-GCM с env `NSEC_ENCRYPTION_KEY`.
- User расширение T2.1: `highest_verification_level: str | None` — денормализация. Обновляется через `refresh_highest_level()` при INSERT/revoke badge.
- User расширение T2.4: `verifications_issued_count: int`, `verifications_received_count: int`, `dealt_with_count: int` (все default 0). Refreshed через `refresh_trust_counts()`.
- `TrustEdge(id, from_user_id, to_user_id, kind ∈ {peer_verified, dealt_with, invited}, weight FLOAT, source_ref VARCHAR(64), created_at, revoked_at?)` — T2.4. UNIQUE(from, to, kind, source_ref) для идемпотентных вставок. Partial index на активных рёбрах.
- `VerificationLevel` enum: `auto` / `peer` / `kyc` (порядок = сила trust).
- `VerificationRequest(id, deal_id→Deal, requested_by_id, target_role ∈ {sender, carrier}, status ∈ {pending, upload, later_in_person, declined, declined_polite, verified, escalated}, created_at, resolved_at?)` — T2.1. `target_role=carrier` → допустимо `declined_polite` (без последствий).
- `IdentityContainer(id, owner_id, owner_role ∈ {sender, carrier, both}, storage_mode ∈ {encrypted_blob, zk_snark}, blob_encrypted BYTEA?, doc_hash, doc_country, doc_type, sanctions_check_status ∈ {clean, match, review_needed}, created_at)` — ключ = owner's Nostr nsec, multi-doc allowed. `storage_mode=encrypted_blob` default в T2.1; `zk_snark` добавляется в T6.4.
- `VerificationBadge(id, subject_id, level ∈ VerificationLevel, source ∈ {auto_ocr, peer, arbiter_review, kyc_provider}, container_ref_id→IdentityContainer, verified_by_id?, in_deal_id?, verified_at, expires_at?, revoked_at?)` — append-only. `verified_by_id` null для auto, user для peer, `KycRecord.id`-ref для kyc. Index `(subject_id, level, revoked_at IS NULL)`.
- `TrustEdge(id, from_user_id, to_user_id, kind ∈ {peer_verified, dealt_with, invited}, weight FLOAT, source_ref, created_at, revoked_at?)` — T2.4
- `SanctionsList(source, name_normalized, dob?, country?, added_at)` — daily refresh OFAC SDN + EU consolidated
- `User.highest_verification_level: VerificationLevel | None` — денормализованное поле, обновляется при INSERT/revoke `VerificationBadge`. MAX по всем не-revoked.
- *(User.nostr_pubkey заполняется; DealVaultMessage/DealEvent подписываются; T2.3 — threshold-encryption заменяет at-rest из T1.21)*
- `User.key_self_custody: bool = False` — добавляется в T2.2

**Фаза 3**
- *(User.business_activity_level — заглушка Фазы 1 — заполняется реальным значением УБА; пересчёт Celery beat ежечасно)*
- **УБА-формула:** `round(F_norm × Q_norm × V_norm × D_factor × 1000)`. F = рейсы/мес (rolling 90d), Q = сделки с двумя DealVault-фото (log), V = сумма declared_value USD (log), D_factor = бонус залога [1.0–1.5]. Детали: IMPLEMENTATIONPLAN §6 §3.1.
- **Оператор-арбитр и Dispute уже реализованы в T1.23/T1.24** — Фаза 3 добавляет только УБА + расширенную консоль/аналитику.

**Фаза 3**
- `V_verify_factor` в формуле УБА — новый компонент из T2.1: множитель [1.0…1.3] по `User.highest_verification_level` (`auto → 1.05`, `peer → 1.15`, `kyc → 1.3`, `null → 1.0`). Формула становится: `УБА = round(F_norm × Q_norm × V_norm × D_factor × V_verify_factor × 1000 / V_verify_factor_max)` — нормализация чтобы диапазон остался [0…1000].
- `Trip.carrier_verification_level: VerificationLevel | None` — денормализация от `Trip.carrier.highest_verification_level` для фильтров и chip'ов.

**Фаза 3.5**
- `Trip.nostr_event_id?` (unique index), `Trip.nostr_published_at?` — T3.5
- `SanctionsList` уже введена в Фазе 2

**Фаза 4**
- `KycRecord(id, user_id, provider, external_id, status ∈ {pending, verified, rejected, expired}, verified_at, expires_at, level)` — T4.1
- `ComplianceAck(id, user_id, doc_version, category, acknowledged_at)` — T4.1
- `CorridorRestriction(origin_country, destination_country, requires_kyc_level, blocked)` — T4.1 санкционный периметр
- `Payment(id, deal_id, method=card, amount, platform_fee, status)` — T4.2

**Фаза 5**
- `Escrow(id, deal_id, chain, type=multisig_2of3, lock_address, amount, arbiter_pubkey_ref, status)`
- `Collateral(id, deal_id, carrier_id, amount, status)`

**Фаза 6**
- `PremiumSubscription(id, user_id, plan, status)`
- `PortableExport(id, user_id, package_hash, ipfs_cid_root, created_at)`
- *(Attachment.ipfs_cid заполняется; DealVaultMessage → IPFS-пин)*

---

## 5. Инварианты (нельзя нарушать)
- `DealEvent`, `DealVaultMessage`, `Attachment` — только добавление; без UPDATE/DELETE через приложение.
- Сумма/условия сделки не меняются без записи события и согласия второй стороны.
- Платформа не хранит средства пользователей — только ключ арбитра (`arbiter_pubkey_ref`).
- Каждое вложение имеет `file_hash` (SHA-256).
