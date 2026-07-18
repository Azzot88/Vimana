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
- **Celery + Redis** — фоновые задачи (уведомления, проверки дедлайнов).
- **ReportLab / WeasyPrint** — генерация «посадочного талона сделки» (PDF).

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
- `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_HOST` / `SMTP_PORT` (email-уведомления)
- `REDIS_URL` (Celery)
- `CORS_ORIGINS` (T1.19 whitelist доменов)
- `RATE_LIMIT_ENABLED` (T1.19 slowapi; в тестах = `false`)

**Notifications (Фаза 1):**
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` / `TELEGRAM_WEBHOOK_SECRET` (T1.7 Telegram)
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_WHATSAPP_FROM` (T1.7 WhatsApp)

**Admin (Фаза 1, T1.18):**
- `ADMIN_API_TOKEN` (защита waitlist read endpoint)
- `ADMIN_TELEGRAM_CHAT_IDS` (comma-separated chat_ids для уведомлений о новом waitlist)

**Фаза 2:**
- OCR/санкции — без API-ключей, всё локально (PaddleOCR + публичные CSV).

**Фаза 3.5:**
- `NOSTR_RELAY_URL` (наш публичный wss endpoint)
- `NOSTR_RELAY_PRIVKEY` (служебный ключ для NIP-42 challenges + deletion events)
- `NOSTR_FRIENDLY_RELAYS` (comma-separated whitelist wss:// адресов)

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
- **При изменении `.env`** — обязательно `up --force-recreate --remove-orphans` (просто `restart` **не подхватит** переменные окружения, см. [feedback_docker_compose_env]).
- **Миграции `alembic upgrade head` — НЕ в стандартный шаблон.** Запускать только если в коммите есть новый файл в `backend/alembic/versions/`. Alembic идемпотентна, но лишняя `docker exec` — трата времени и шума в логах. Проверка: `git diff --name-only HEAD~1 HEAD -- backend/alembic/versions/`. Если пусто — миграцию не запускать.
- **Тесты и билды выполняются только на сервере**, никогда локально (см. `feedback_no_local_tests_builds`).
