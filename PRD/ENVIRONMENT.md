# Vimana — Sacred Logistics · ENVIRONMENT.md

> FILL ──────────────────────────────
> Назначение: источник истины о стеке, средах и инфраструктуре Vimana — Sacred Logistics.
> Когда обновлять: при любом изменении зависимостей, версий, сред или правил деплоя.
> Что НЕ дублировать: бизнес-логику и связи компонентов (живут в TECHSTATE), продуктовые метрики (METRICS).
> Формат записи: правь соответствующий раздел; значимые инфра-изменения дублируй строкой в CHANGELOG.
> ───────────────────────────────────

---

## 1. Стек технологий (целевой)

Зрелые, надёжные технологии — работаем с ценными грузами, ключами и (с Фазы 2) обеспечением.

### Backend (ядро и API)
- **Python / FastAPI** — строгая типизация, async API.
- **SQLAlchemy (async)** — ORM.
- **Alembic** — миграции.
- **Celery + Redis** — фоновые задачи (уведомления, проверки дедлайнов). Redis поднимается с `--requirepass` (T_SEC.3).
- **PDF «посадочного талона сделки»** — движок не выбран. `weasyprint` числился в зависимостях, но не импортировался ни разу и держал `Pillow<11`; удалён в T_SEC.3. Выбор движка — часть задачи, которая будет делать сам талон.

### Frontend
- **React / TypeScript / Vite** — отзывчивый SPA.
- **TailwindCSS** — стилизация (по DESIGNGUIDELINES: навигационная палитра, IBM Plex Mono для данных).
- **Zustand/Redux** — стейт-менеджмент.

### Infrastructure
- **PostgreSQL** — основная БД (ACID критичен для сделок и обеспечения).
- **Cloudflare R2 / S3-совместимое хранилище** — фото и вложения Чёрного ящика.
- **Docker & Docker Compose** — унификация dev/prod (см. §6).
- **Nginx** — reverse proxy и SSL termination (либо Cloudflare перед origin).

### Идентификация (Фаза 2)
- **Peer identity verification** — локальный OCR-стек: **PaddleOCR** для MRZ-строк паспортов (fallback tesseract), санкционные списки OFAC SDN + EU consolidated (публичные CSV, обновляются ежедневно). Внешние KYC-API **не используются** в Фазе 2 — верификация силами сети (T2.1).
- **Trust Graph (T2.4)** — Postgres-таблица `trust_edges`, BFS в приложении с Redis-кешем.
- **Nostr keypair (T2.2)** — `coincurve` для secp256k1; `nsec` шифруется AES-256-GCM (ключ в env).

### Nostr Relay (Фаза 3.5)
- **strfry** — production-ready C++ relay, отдельный контейнер `nostr-relay` в docker-compose. LMDB storage (~50 MB idle).
- **Friendly relays whitelist** — env `NOSTR_FRIENDLY_RELAYS`; стартовый набор в TECHSTATE D-NOSTR-FEDERATION.
- Event kind trip = NIP-99 30402 (см. D-NOSTR-RELAY).

### Regulatory KYC + Платежи (Фаза 4)
- **KYC-провайдер** — выбирается перед вводом карточных платежей (Sumsub / Onfido / Jumio; фиксируется в TECHSTATE Decision Log D-KYC). Требуется для regulator-compliance.
- **Карточный процессинг** — конкретный процессор фиксируется в Decision Log при подходе к T4.2.

### Эскроу (Фаза 5)
- **BTC-эскроу** — 2-of-3 multisig по образцу HodlHodl; платформа держит **только ключ арбитра**.
- **Некастодиальный кошелёк** — для возвратов.
- **USDT-эскроу** — контрактный аналог не-кастодиальной 2-of-3.

### Портативность (Фаза 6)
- **Nostr SDK** — расширение существующего Nostr-стека для полного экспорта аккаунта.
- **IPFS SDK** — контент-адресуемое дублирование (CID ↔ хеш вложений).
- **ZK-proof** (T6.4) — Circom / halo2, `snarkjs`/`halo2-wasm` в браузере.
- **Админ/операторская панель** — вариант на оценке (см. Decision Log в TECHSTATE D6).

---

## 2. Среды (ожидаемые)

| Среда | Ветка | Описание |
|---|---|---|
| **Local (Dev)** | `*` | `docker compose -f docker-compose.dev.yml up` |
| **Staging** | `dev` | Тестовый сервер для UI и интеграций |
| **Production** | `main` | Боевой сервер с бэкапами БД |

*(IP/домены добавляются после реального деплоя. Маркетинговый лендинг деплоится на Cloudflare Pages/Workers — см. README.)*

---

## 3. Секреты и переменные окружения (.env)

Все ключи — строго в `.env` (в `.gitignore`).

**Обязательные (в prod уже используются):**
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` / `DATABASE_URL`
- `TEST_DATABASE_URL` (изолированная тестовая БД, ENVIRONMENT §8)
- `SECRET_KEY` (подпись JWT)
- `MESSAGE_ENCRYPTION_KEY` (T1.21 at-rest AES-256-GCM для DealVault; **если пусто в prod — падение при первом encrypt/decrypt**)
- `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` / `R2_ENDPOINT` (вложения DealVault)
- `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_HOST` / `SMTP_PORT` (email-уведомления). На проде — Mailu, `mail.dealvault.club:465` (`D-MAIL-VIA-MAILU`). **В dev можно направить в Mailpit** (T_UX.9): `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, логин и пароль любые — тогда всё, что шлёт приложение, оседает в веб-ящике на `:8025` вместо настоящей почты. Поднимается профилем: `docker compose -f docker-compose.dev.yml --profile mail up -d mailpit`; обычный `up` его не трогает.
- `PREVIEW_SMTP_HOST` / `PREVIEW_SMTP_USER` / `PREVIEW_SMTP_PASSWORD` / `PREVIEW_SMTP_PORT` (T_UX.9 pt.2) — **контур просмотра, отдельный от боевого**. Сюда и только сюда уходит тестовая отправка из админской почтовой консоли. Значения для Mailpit: `PREVIEW_SMTP_HOST=mailpit`, `PREVIEW_SMTP_PORT=1025`, `PREVIEW_SMTP_USER=dev@dealvault.club`, пароль пустой. Не задан → консоль честно пишет «контур не настроен» и отвечает 503 вместо тихого успеха. **Никогда не подменять этим `SMTP_*`:** боевой хост, направленный в ловушку, заглушает все настоящие письма, пока `send_email` продолжает возвращать `True`.
- `REDIS_PASSWORD` (T_SEC.3; compose стартует Redis с `--requirepass`, без переменной `up` падает с явной ошибкой) + `REDIS_URL` (Celery и приложение; пароль вписывается в URL руками — `env_file` не раскрывает подстановки)
- `CORS_ORIGINS` (T1.19 whitelist доменов)
- `RATE_LIMIT_ENABLED` (T1.19 slowapi; в тестах = `false`)

**Notifications (Фаза 1):**
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` / `TELEGRAM_WEBHOOK_SECRET` (T1.7 Telegram)
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` (T1.7 WhatsApp)

**Admin (Фаза 1, T1.18):**
- ~~`ADMIN_API_TOKEN`~~ — **удалена в T_UX.8 pt.2 (2026-08-08).** Была единственным местом, где авторизация шла статическим заголовком мимо ролевой модели; `GET /api/waitlist` переведён на `require_perm(Permission.WAITLIST_READ)`, то есть на обычную сессию суперюзера. Переменную можно убрать из `.env`.
- `ADMIN_TELEGRAM_CHAT_IDS` (comma-separated chat_ids для уведомлений о новом waitlist)

**Фаза 2:**
- OCR/санкции — без API-ключей, всё локально (PaddleOCR + публичные CSV).

**Фаза 3.5:**
- `NOSTR_PUBLISH_ENABLED` (мастер-переключатель всего, что уходит наружу: листинги рейсов и якоря цепи; по умолчанию `false`)
- `NOSTR_RELAY_URL` — наш публичный endpoint, **`wss://<домен>/relay`** (TLS терминирует nginx, T_SEC.4); `NOSTR_OWN_RELAY_URL` — тот же relay изнутри compose-сети, `ws://nostr-relay:7777`
- `NOSTR_RELAY_PRIVKEY` (служебный ключ для NIP-42 challenges + deletion events)
- `NOSTR_FRIENDLY_RELAYS` (comma-separated whitelist wss:// адресов)
- `CHAIN_ANCHOR_NSEC` (T3.6/T3.20) — 64-hex ключ, которым платформа подписывает якоря голов цепи. Не задан → якорение молча ничего не делает; именно так оно и жило до T3.20. **Обязан отличаться от `PLATFORM_PUBLISH_NSEC`** и не быть ничьим пользовательским: якорь — утверждение платформы о своих же записях, и подписант, который вдобавок подписывает события сделок, делает неразличимым, кто из двоих говорит. Генерация на сервере: `docker compose -f docker-compose.dev.yml exec -w /app backend python -c "from app.core.keypair import generate_keypair; print(generate_keypair()[0])"`. Якорение включается **тремя** значениями сразу: `NOSTR_PUBLISH_ENABLED=true`, `CHAIN_ANCHOR_NSEC=<hex>` и хотя бы один **сторонний** relay в `NOSTR_FRIENDLY_RELAYS` — голова, дошедшая только до нашего strfry, не доказывает о нас ничего, а в этом весь смысл якоря. После правки `.env` нужен `up -d --force-recreate` (не `restart`) для `backend`, `celery-worker` и `celery-beat` — тик якорения исполняет воркер, и старое значение переменной пережило бы `restart`.

**Фаза 3.8** (`D-CONTACT-CHANNELS`, T3.26):
- `CHANNEL_EMAIL_ENABLED` / `CHANNEL_TELEGRAM_ENABLED` — по умолчанию `true`. Оба канала работают сегодня: почта чинена 2026-07-30 (`D-MAIL-VIA-MAILU`), Telegram-бот и связывание через `/start {token}` живут с T1.7.
- `CHANNEL_TELEGRAM_GATEWAY_ENABLED` + `TELEGRAM_GATEWAY_TOKEN` (T3.26) — отправка кода **по номеру телефона** любому, у кого есть Telegram. Требует отдельного аккаунта и депозита; условия и тариф проверять на момент подключения, а не по этой строке.
- `CHANNEL_SMS_ENABLED` (T3.30) — по умолчанию `false`. **Что блокирует включение:** A2P-регистрация трафика. США — 10DLC (регистрация бренда и кампании, нужна американская сущность с EIN) либо верификация toll-free номера; ОАЭ — зарегистрированный Sender ID у Etisalat/du, обычно с местной лицензией. Недели, не дни. Записано здесь, чтобы через два месяца это не выяснялось заново.
- `CHANNEL_WHATSAPP_ENABLED` (T3.31) — по умолчанию `false`. **Что блокирует:** WhatsApp Business Account, верификация бизнеса в Meta и одобрение authentication-шаблона. То же ограничение действует и на оповещения из T1.7: вне 24-часового окна возможен только шаблон.
- `OTP_COUNTRY_ALLOWLIST` (T3.29) — comma-separated ISO-коды стран, которым доступны **платные** каналы. Пусто = платные каналы не выдаются никому. Публичный «отправить код» — готовая схема SMS-pumping, и счёт за неё приходит платформе, поэтому список пустой по умолчанию, а не открытый.
- `TURNSTILE_SECRET_KEY` (T3.29) — капча на подозрительных запросах кода. Не задан → проверка пропускается, лимиты по идентификатору/IP/стране продолжают действовать.

**Фаза 4:**
- `KYC_PROVIDER_API_KEY` (Sumsub / Onfido / Jumio — D-KYC)
- `PAYMENT_PROVIDER_KEY` (карточный процессинг)

**Фаза 5:**
- `BTC_ESCROW_ARBITER_KEY_REF` (ссылка на защищённое хранилище ключа арбитра — не сам ключ)
- `USDT_ESCROW_RPC_URL`

**Фаза 6:**
- `IPFS_GATEWAY_URL`

---

## 4. Правила работы с БД

1. **Миграции обязательны** (`alembic revision --autogenerate` + `alembic upgrade head`). Никаких ручных правок схемы.
2. Данные `deals`, `deal_events`, `deal_vault_messages`, `attachments`, `disputes`, `peer_verifications`, `identity_containers` считаются критическими: **не удаляются** (только статусная архивация); append-only сохраняется на уровне приложения и ограничений.
3. Вложения хешируются (SHA-256) при загрузке; хеш хранится в `Attachment`.

---

## 5. Безопасность данных и ключей

- KYC-данные и фото документов — чувствительная PII; шифрование at-rest, доступ под аудит.
- Ключ арбитра — через защищённое хранилище (KMS/HSM-подход), **никогда** в открытом виде в БД.
- Платформа **не кастодирует средства пользователей** — только ключ арбитра в схеме 2-of-3.

### 5.1 Prod attack-surface (T_SEC.1)

- **Swagger / OpenAPI выключены в prod** через env `EXPOSE_DOCS=false` → `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. В dev остаются открыты `/docs`, `/redoc`. Реализация — T_SEC.1.
- **nginx security headers** (см. T_SEC.1): CSP, HSTS `max-age=31536000; includeSubDomains`, X-Frame-Options `DENY`, X-Content-Type-Options `nosniff`, Referrer-Policy `strict-origin-when-cross-origin`, Permissions-Policy минимальный, `server_tokens off`.
- **Probe-пути блокируются** на уровне nginx: `.env`, `.git`, `wp-admin`, `.php`, `.aspx` → 403/404.
- **Rate-limit** на `/api/auth/login` и `/api/auth/register` — slowapi + nginx `limit_req` дублированно.
- **Публичные endpoint'ы** только `/health` (для docker healthcheck); всё остальное — JWT auth или RBAC.
- **Наружу публикуется только nginx** (80/443). Relay с T_SEC.4 порт не публикует вовсе — он доступен как `wss://<домен>/relay` через тот же nginx; 7777 в security group можно закрыть. `db`, `redis` и `backend` слушают `127.0.0.1` — T_SEC.3. До этого `backend` был опубликован на `0.0.0.0:8000` и открыт в security group: прямое обращение обходило TLS, security-заголовки, probe-deny и обе зоны `limit_req`, а ключ slowapi берётся из `X-Forwarded-For` (`core/rate_limit.py`), который прямой клиент подставляет сам. Доступ для отладки — SSH-туннель (`ssh -L 8000:127.0.0.1:8000`), не публикация порта.

### 5.2 Developer setup — remote access

- **iOS-клиент для управления Mac-терминалом с Claude Code:** Blink Shell (App Store) + Tailscale mesh VPN. Тайл: телефон → Blink через Tailscale → mosh на Mac → `claude` в терминале. Официального iOS Claude Code клиента нет; альтернатива — Safari на claude.ai/code (UX хуже).

---

## 6. Docker-Dev (правило)

> [!CAUTION]
> Зависимости проекта (Python, pip, пакеты) — **внутри Docker-контейнеров**. Локально: Docker, Git, IDE, `.env`. Правило распространяется на людей и AI-агентов.
> *(Допущение проекта — подтвердить владельцем; при отказе перенести в TECHSTATE Decision Log.)*

---

## 7. Правила тестирования (ОБЯЗАТЕЛЬНО)

### Принципы
1. **Отдельная тестовая БД** — `vimana_test`, изолирована от dev/prod. Никогда не запускать тесты против dev/prod-базы.
2. **Сид-данные создаются один раз, не удаляются.** Фикстуры проверяют существование записи перед созданием (idempotent): `SELECT … WHERE email = 'seed@vimana.test'` → если есть, использовать; если нет — создать. Никакого `teardown`, `DROP TABLE`, `TRUNCATE`, `DELETE FROM` на сид-таблицах.
3. **`scope="session"`** для сид-фикстур — данные живут весь запуск pytest и переживают его (остаются в БД).
4. **Тесты идемпотентны** — каждый тест самодостаточен и не зависит от порядка выполнения. Тест-специфичные записи (не сид) помечаются префиксом `test_` и могут пересоздаваться.
5. **Тесты не меняют сид-данные** — только читают и проверяют ожидаемое состояние.

### Переменные окружения для тестов
```
TEST_DATABASE_URL=postgresql+asyncpg://vimana:vimana_dev@db:5432/vimana_test
```
Миграции применяются к тестовой БД через `alembic upgrade head` с подменой `DATABASE_URL`.

### Запуск
```bash
docker compose exec -w /app backend pytest -v
```

### Запрещено в тестах
- `DROP TABLE`, `TRUNCATE`, `DELETE FROM` на таблицах с сид-данными
- Изменение полей существующих сид-записей
- Тесты, завязанные на порядок выполнения

---

## 8. Как запустить (сценарий)

```bash
git clone <repo-url> vimana && cd vimana
cp .env.example .env   # заполнить .env
docker compose -f docker-compose.dev.yml up -d --build
docker compose exec backend alembic upgrade head
```

## 9. Правила инкрементального деплоя (dev/prod)

**Стандартный цикл на сервере после `git pull`:**

```bash
docker compose -f docker-compose.dev.yml up -d --build backend frontend celery-worker celery-beat
docker compose -f docker-compose.dev.yml exec -w /app backend pytest -v
```

**Правила:**

- **При изменении `frontend/package.json`** — только `--build frontend`. `Dockerfile` уже содержит `RUN npm install`, Docker инвалидирует слой автоматически. **Никогда не запускать `docker compose exec frontend npm install`** — это лишний шаг, зависимости уже установлены в новом образе.
- **При изменении `backend/requirements.txt`** — только `--build backend`. Аналогично: `pip install -r requirements.txt` в Dockerfile ставит пакеты при билде.
- **При изменении только исходников (без deps)** — `--build` всё равно быстро отрабатывает через кэш слоёв, ставить только `restart backend/frontend` **не безопасно** (nginx-контейнер держит соединения к старым, .env не подхватится).
- **Правка исходников требует пересоздания контейнера** (T_SEC.3). `uvicorn` больше не запускается с `--reload`: watcher держал вторую копию приложения в памяти и перезапускал воркеров при любом изменении файла в примонтированном `./backend` — `git pull` во время запроса ронял этот запрос. Штатный `up -d --build backend` из шаблона выше это и делает.
- **При изменении `.env`** — обязательно `up --force-recreate --remove-orphans` (просто `restart` **не подхватит** переменные окружения, см. [feedback_docker_compose_env]).
- **Миграции `alembic upgrade head` — НЕ в стандартный шаблон.** Запускать только если в коммите есть новый файл в `backend/alembic/versions/`. Alembic идемпотентна, но лишняя `docker exec` — трата времени и шума в логах. Проверка: `git diff --name-only HEAD~1 HEAD -- backend/alembic/versions/`. Если пусто — миграцию не запускать.
- **Тесты и билды выполняются только на сервере**, никогда локально (см. `feedback_no_local_tests_builds`).
