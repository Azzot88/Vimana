# Vimana — Sacred Logistics · TASKS.md

> NAV ──────────────────────────────
> ↑ старший (читать ДО, при конфликте — он прав): IMPLEMENTATIONPLAN.md
> ↓ младший (читать ПОСЛЕ, определяется этим файлом): — лист
> Поток: PLANNING — пишется старший→младший · UPDATES — правится по минимальному подъёму
> ───────────────────────────────────

## Executable Backlog · Single Source of Execution

> ⚠️
> - Этот файл — **единственный**, который меняется в процессе работы.
> - Задачи выполняются **строго по порядку** (сверху вниз).
> - Нельзя перескакивать фазы из IMPLEMENTATIONPLAN.md.
> - Если задачи нет здесь — её не существует.
> - После выполнения — обновить статус здесь и зафиксировать в TECHSTATE.md / CHANGELOG.md (если применимо).
> - **Тесты (ОБЯЗАТЕЛЬНО после T_TEST.1):** каждая задача добавляет тесты новой функциональности; перед закрытием задачи весь backend-сьют должен проходить (`docker compose exec backend pytest`); frontend-сборка не должна падать (`npm run build`). Правила изоляции — ENVIRONMENT.md §8. До завершения T_TEST.1 это правило не применяется.
> - **Версия:** после каждой закрытой задачи — обновить `frontend/src/version.ts` (см. CLAUDE.md).

---

## ⚙️ ЭТАП 0 — Инфраструктура / DevOps

### T0.1 — Инициализация репозитория и окружения ✅
- [x] Ознакомиться с PROJECT.md и всей PRD-документацией.
- [x] Структура директорий (`backend/`, `frontend/`).
- [x] `docker-compose.dev.yml` с PostgreSQL + Redis.
- [x] `.env.example`.
- [x] `TECHSTATE.md` инициализирован (существовал, статусы обновлены).
**Acceptance:** чистая структура, БД поднимается локально через Docker, TECHSTATE инициализирован. ✅

---

## 🧱 ЭТАП 1 — Ядро доверия (Фаза 1, V1)

### T1.1 — FastAPI + SQLAlchemy + Alembic ✅
- [x] Инициализировать FastAPI.
- [x] Подключение к PostgreSQL (SQLAlchemy async).
- [x] Инициализировать Alembic.
**Acceptance:** сервер стартует, отвечает на `/health`, Alembic готов к первой миграции. ✅

### T1.2 — Доменные модели ✅
По IMPLEMENTATIONPLAN §4 §1.1:
- [x] `User` (+ nullable-заглушки `business_activity_level`, `nostr_pubkey`).
- [x] `Connection`, `InviteLink` (социальный граф).
- [x] `Trip`, `Order` (с `category` enum), `Deal`.
- [x] `DealEvent` (append-only), `DealVaultMessage`, `Attachment` (+ `file_hash`, nullable `ipfs_cid`).
- [x] Миграция `0001_initial_models.py` создана. Применить: `docker compose exec backend alembic upgrade head`.
**Acceptance:** таблицы созданы, Foreign Keys корректны, append-only ограничения на месте, все nullable-заглушки присутствуют. ✅

### T1.3 — Аутентификация + Социальный граф ✅
- [x] JWT регистрация/логин.
- [x] `POST /api/invites` — генерация InviteLink (одноразовая, TTL 7 дней).
- [x] `POST /api/invites/{token}/accept` — принять приглашение → двусторонняя Connection.
- [x] `GET /api/me/connections` — список связей с профилями.
- [x] Guest-invite: `recipient_contact` принимается в body `/api/invites`.
**Acceptance:** пользователь создаёт аккаунт, генерирует инвайт, друг принимает, оба видят связь. ✅

### T1.4 — API маршрутов и сделки ✅
- [x] `POST /api/trips`, `GET /api/trips` (фильтры origin/destination/date).
- [x] `POST /api/deals/match`, `POST /api/deals/{id}/accept`.
- [x] `POST /api/deals/{id}/event` (handoff/in_transit/received).
- [x] `POST /api/deals/{id}/confirm`, `GET /api/deals`.
**Acceptance:** перевозчик публикует маршрут; две стороны создают сделку, проходят статусы до закрытия. ✅

### T1.5 — DealVault (API + хранилище) ✅
- [x] `GET/POST /api/deals/{id}/dealvault/messages` + GET /{id}/dealvault.
- [x] Загрузка фото в R2/S3 (graceful без R2), SHA-256 → `file_hash`, `ipfs_cid` nullable.
- [x] Запрет удаления/редактирования — DELETE/PATCH эндпоинтов нет; только INSERT на уровне API.
- [x] Структура DealVaultMessage совместима с Nostr event — `nostr_sig` nullable-заглушка Фазы 2.
**Acceptance:** стороны переписываются, грузят файлы; записи иммутабельны; SHA-256 хеш сохраняется. ✅

### T1.6 — Frontend (дашборд, социальный граф, сделка) ✅
- [x] Vite + React + TypeScript + TailwindCSS; Space Grotesk / Inter / IBM Plex Mono; цвета navy/cyan/amber/ivory.
- [x] Дашборд (Я везу / Мне везут / Я отправляю).
- [x] Мастер рейса (NewTripPage) и заявки (TripsPage → matchDeal).
- [x] Экран сделки (DealPage) с посадочным талоном + кнопки по роли/статусу; DealVaultPage.
- [x] Профиль: заглушка УБА + секция «Контакты» (Connections).
- [x] Поток инвайта: InvitePage + AcceptInvitePage.
- [x] GET /api/deals/{id} — обогащённый DealDetailOut (trip + order + user names).
**Acceptance:** полный флоу доставки проходится через UI; инвайт end-to-end; Connections в профиле. ✅

### T1.7 — Уведомления ✅
- [x] Celery beat — проверка дедлайнов/статусов (каждый час).
- [x] Email о статусах и приближении прибытия (мягкие формулировки).
- [x] Telegram-уведомления: поле `telegram_chat_id` в профиле; привязка через бота (`/start {token}`); уведомления о статусах сделки.
- [x] WhatsApp-уведомления: поле `whatsapp_number` в профиле; интеграция Twilio; те же события.
- [x] В профиле: секция «Уведомления» — включить/отключить каждый канал (email / Telegram / WhatsApp).
**Acceptance:** пользователь выбирает каналы уведомлений в профиле; при смене статуса сделки приходит уведомление в подключённые каналы. ✅

### T1.9 — Интернационализация (i18n) ✅
- [x] Подключить `react-i18next`; namespace `common`, `auth`, `trips`, `deals`, `profile`.
- [x] Языки: EN (по умолчанию), UK, PL, FR, ES. Переключатель в шапке/профиле.
- [x] Перевести все пользовательские строки (кнопки, лейблы, сообщения об ошибках, статусы).
- [x] Выбранный язык сохраняется в `localStorage`.
- [x] Бэкенд: сообщения об ошибках API остаются на EN (клиент переводит по коду или ключу).
**Acceptance:** интерфейс полностью переключается на один из 5 языков без перезагрузки; выбор сохраняется между сессиями. ✅

### T_TEST.1 — Backend тест-сьют (фундамент) ✅
> Перенесено из блока «Тестирование» — базовый сьют строится **до** T1.10, потому что все последующие задачи обязаны его расширять и прогонять.
- [x] Добавить в `backend/requirements.txt`: `pytest`, `pytest-asyncio`.
- [x] `backend/pytest.ini`: конфигурация pytest, `asyncio_mode = "auto"`.
- [x] `.env.example` дополнен `TEST_DATABASE_URL=postgresql+asyncpg://vimana:vimana_dev@db:5432/vimana_test`; БД создаётся автоматически в conftest при первом запуске через psycopg2 (`CREATE DATABASE IF NOT EXISTS`).
- [x] `backend/tests/conftest.py`: сид-фикстуры `scope="session"` — два пользователя (`seed-carrier@vimana.test` + `seed-sender@vimana.test`), один рейс (`SEED-ORIGIN→SEED-DEST`), одна сделка. Создаются идемпотентно (`WHERE email = ...`).
- [x] Тесты auth (`test_auth.py`): register (новый / duplicate 409 / нет email+phone 422), login (валид / wrong pw / unknown), me (200 / 401), PATCH me.
- [x] Тесты trips (`test_trips.py`): создание carrier'ом (201), запрет sender'у (403), список + фильтр origin.
- [x] Тесты deals (`test_deals.py`): match, accept (200 carrier / 403 sender), event handoff → in_transit, confirm → closed, list deals, GET /deal/{id} outsider 403.
- [x] Тесты dealvault (`test_dealvault.py`): list, create message, forbidden для outsider.
- [x] Тесты social (`test_social.py`): create invite, accept → двусторонний Connection, own invite 400, reused 409, unknown 404.
- [x] Инструкция запуска в ENVIRONMENT.md §8: `docker compose -f docker-compose.dev.yml exec -w /app backend pytest -v`.
- [x] Celery `notify_deal_status.delay` замокан в autouse-фикстуре (тесты не требуют Redis для side-effect'ов).
**Acceptance:** `pytest` проходит зелёным на чистой `vimana_test`; повторный прогон идентичен первому; сид-данные не удаляются. ✅

### T1.10 — База аэропортов + геолокация
- [ ] Бэкенд загружает `airports.dat` (OpenFlights, ~7 000 записей, ~1 МБ) при старте из публичного источника; хранит в памяти (Python dict); поля: IATA-код, город, страна, lat, lon.
- [ ] `GET /api/airports?q=` — поиск по IATA-коду или названию (город/страна); возвращает до 10 результатов: `{iata, city, country, lat, lon}`.
- [ ] `GET /api/airports/nearest?lat=&lon=&limit=5` — ближайшие аэропорты по формуле Haversine (D11); возвращает до 5, отсортированных по расстоянию.
- [ ] Названия города и страны — на языке пользователя (i18n lookup или поле `name_{lang}` в данных).
- [ ] Фронтенд: компонент `AirportSelect` — текстовый поиск с autocomplete; дропдаун: 3 видимых строки, остальные — прокрутка; кнопка-иконка геолокации рядом с полем.
- [ ] Кнопка геолокации: `navigator.geolocation.getCurrentPosition` → запрос `/nearest` → заполнить дропдаун ближайшими аэропортами.
- [ ] Заменить свободный ввод `origin`/`destination` на `AirportSelect` в NewTripPage и форме заявки.
**Acceptance:** поиск по тексту отдаёт релевантные аэропорты; кнопка геолокации показывает ближайшие (топ-3 видимы, дальше прокрутка); выбранное значение — IATA-код.

### T1.11 — Телефон в профиль; убрать из регистрации
- [ ] Убрать поле «Телефон» из RegisterPage.
- [ ] В ProfilePage добавить секцию «Контакты»: селект кода страны (+XX) + поле номера телефона.
- [ ] Бэкенд: `PATCH /api/auth/me` — обновление `phone`, `display_name`; телефон не обязателен.
- [ ] Миграция не нужна (`phone` уже nullable в `User`).
**Acceptance:** регистрация проходит без телефона; телефон добавляется/редактируется в личном кабинете.

### T1.12 — Мобильная версия (responsive)
- [ ] Tailwind breakpoints (`sm:` / `md:`) на всех страницах; базовый layout — mobile-first.
- [ ] Нижняя навигация (`BottomNav`) на мобильном вместо боковой/верхней; скрывается на `md:`.
- [ ] Карточки рейсов/сделок — одна колонка на мобильном, сетка на десктопе.
- [ ] Формы (регистрация, новый рейс, заявка) — поля на всю ширину, крупные тач-зоны (min-height 44px).
- [ ] DealVault-чат: на мобильном занимает весь экран, кнопка отправки снизу.
- [ ] `AirportSelect` дропдаун — корректно открывается на мобильном (без выхода за экран).
- [ ] Проверить на viewport 375px (iPhone SE) и 390px (iPhone 14).
**Acceptance:** все ключевые флоу (регистрация, публикация рейса, сделка, DealVault) проходятся на мобильном экране без горизонтального скролла и мелких тач-целей.

### T1.13 — Локализация: UK→UA, добавить RU
- [ ] Переименовать `frontend/src/i18n/locales/uk.json` → `ua.json`; обновить импорты в `frontend/src/i18n/index.ts` (`uk: {...}` → `ua: {...}`).
- [ ] `LanguageSwitcher.tsx`: код `'uk'` → `'ua'`, label `'UK'` → `'UA'`. Правило: Ukraine всегда сокращается до **UA** (не UK — во избежание конфликта с United Kingdom).
- [ ] Миграция localStorage: при старте, если `localStorage.getItem('lang') === 'uk'` → заменить на `'ua'`.
- [ ] Создать `frontend/src/i18n/locales/ru.json` со всеми ключами из `en.json` (nav, auth, common, dashboard, trips, deals, profile).
- [ ] Добавить `ru` в `i18n/index.ts` и в `LANGS` в `LanguageSwitcher`. Итого 6 языков: EN / UA / RU / PL / FR / ES.
- [ ] Обновить упоминания UK в PRD-файлах (уже сделано в этой задаче).
**Acceptance:** переключатель показывает 6 языков (EN / UA / RU / PL / FR / ES); UA выводит украинский, RU — русский; старые пользователи с `lang=uk` в localStorage автоматически переезжают на `ua` без потери выбора.

### T1.14 — Раздел «Инвайты» в личном кабинете
- [ ] Бэкенд: `GET /api/invites/mine` — список инвайтов, созданных текущим юзером; поля: `token`, `recipient_contact`, `created_at`, `expires_at`, `status` ∈ {`pending`, `accepted`, `expired`}, `accepted_by_display_name` (nullable).
- [ ] Статус вычисляется на бэке: `accepted` если есть Connection по этому инвайту; `expired` если `expires_at < now()`; иначе `pending`.
- [ ] В `ProfilePage` добавить секцию «Мои инвайты» между «Контактами» и «Уведомлениями»:
  - Кнопка «+ Создать инвайт» (открывает `InvitePage` или inline-форму с полем `recipient_contact`).
  - Список выданных инвайтов: `recipient_contact`, статус (бейдж), для `pending` — мелким текстом «истекает через 3д 4ч» (dynamic countdown из `expires_at`).
- [ ] Срок жизни инвайта остаётся **7 дней** (уже задан в T1.3, не менять).
- [ ] i18n-ключи: `profile.invites`, `profile.inviteCreate`, `profile.inviteExpiresIn`, `profile.inviteStatus.{pending,accepted,expired}`.
**Acceptance:** в ЛК видно список выданных инвайтов со статусом и обратным отсчётом; можно создать новый инвайт из ЛК; после принятия статус меняется на «Принят».

### T1.15 — UX-полишинг: формы, логин, логотип
- [ ] **Персистентность форм в браузере** (localStorage):
  - `LoginPage`: сохранять `login` (email/phone) при вводе, восстанавливать при монтаже. **Пароль НЕ сохранять.**
  - `RegisterPage`: сохранять `display_name`, `email`, `phone`, `is_carrier`. **Пароль НЕ сохранять.**
  - `TripsPage`: сохранять фильтры `origin`, `destination`, `date`.
  - Универсальный хук `usePersistedState(key, initialValue)` — в `frontend/src/hooks/`.
- [ ] **Логин case-insensitive**:
  - Фронт: у input `login` добавить `autoCapitalize="none"`, `autoCorrect="off"`, `spellCheck={false}`.
  - Бэк: в `POST /api/auth/login` сравнивать email через `LOWER(email) = LOWER(:login)`; при регистрации сохранять email в lowercase.
  - Пароль остаётся case-sensitive (bcrypt как есть).
- [ ] **Кликабельный логотип «Vimana»** — во всех разделах ведёт на `/`:
  - В `Navbar.tsx`: обернуть `<span>Vimana</span>` в `<Link to="/">`.
  - На `LoginPage` / `RegisterPage`: логотип остаётся декоративным `<h1>` (уже на публичной странице, некуда вести).
**Acceptance:** повторный вход не требует набирать email заново; логин работает независимо от регистра; клик по логотипу в любой аутентифицированной странице возвращает на Dashboard.

### T1.8 — Staging-деплой, домен и smoke test V1
- [ ] Поднять VPS / облачный сервер (Ubuntu 22+ или Debian 12), установить Docker + Docker Compose.
- [ ] Клонировать репо, скопировать `.env.example` → `.env`, заполнить production-значения.
- [ ] `docker compose -f docker-compose.dev.yml up -d --build` + `docker compose exec backend alembic upgrade head`.
- [ ] Nginx reverse proxy: домен → backend `:8000` (API) и frontend `:5173` (SPA). SSL через Let's Encrypt или Cloudflare.
- [ ] Smoke test: зарегистрировать два аккаунта (Отправитель + Перевозчик), опубликовать маршрут, убедиться что DealVault открывается и ошибок в логах нет.
**Acceptance:** приложение доступно по домену через HTTPS; регистрация и публикация маршрута работают end-to-end; в логах контейнеров нет критических ошибок.

> **Финиш V1** достигается после T1.8 (см. критерий ниже).

---

## 🧪 ТЕСТИРОВАНИЕ — Расширение сьюта

> T_TEST.1 (базовый backend-сьют) перенесён вверх — сразу после T1.9, чтобы стать фундаментом. Правила изоляции — ENVIRONMENT.md §8. Каждая новая задача T1.x обязана добавлять свои тесты в этот сьют.

### T_TEST.2 — Frontend smoke-тесты
- [ ] `vitest` + `@testing-library/react`.
- [ ] Smoke: рендер LoginPage, RegisterPage, DashboardPage без ошибок.
- [ ] Проверка i18n: переключение языка меняет текст.
**Acceptance:** `npm run test` проходит; тесты не требуют сервера.

---

## 🪪 ЭТАП 2 — Идентификация и ключи (Фаза 2)

### T2.1 — KYC и комплаенс
- [ ] `KycRecord`, интеграция KYC-провайдера.
- [ ] `ComplianceAck` (версионируемое подтверждение запрещёнки/ответственности).
- [ ] Санкционный периметр коридора, строгий ToS.
**Acceptance:** пользователь проходит KYC; подтверждение запрещёнки зафиксировано; стороны проверяются по периметру.

### T2.2 — Keypair + Nostr-совместимость (D10: Вариант A + D)
- [ ] При регистрации: генерация secp256k1-keypair; `nsec` хранится зашифрованно (AES-256-GCM, ключ в env/KMS); `npub` → `User.nostr_pubkey`.
- [ ] `User.key_self_custody: bool = False` — миграция Alembic.
- [ ] `User.password_hash` сделать nullable (миграция) — для аккаунтов только с keypair, без пароля.
- [ ] Server-side подпись: `DealVaultMessage` и `DealEvent` подписываются `nsec` при создании; `nostr_sig` сохраняется.
- [ ] Сервер верифицирует подпись через `npub` перед сохранением каждого события.
- [ ] `GET /api/me/keypair/status` — custodial / self-custody, npub.
- [ ] `POST /api/me/keypair/export` — вернуть зашифрованный nsec (требует re-auth/2FA).
- [ ] `POST /api/me/keypair/claim` — пометить self-custody, платформа удаляет nsec.
- [ ] `POST /api/me/keypair/import` — импортировать существующий npub; `key_self_custody = True`.
- [ ] Frontend: определение `window.nostr` (NIP-07); если есть — предложить подпись через extension; сервер принимает pre-signed event и верифицирует.
**Acceptance:** новый аккаунт автоматически получает keypair; DealVault-события подписаны и верифицируемы по `npub` без обращения к платформе; export/claim/import работают; NIP-07 extension перехватывает подпись если обнаружен.

---

## 📈 ЭТАП 3 — УБА и арбитраж (Фаза 3)

### T3.1 — Уровень Бизнес-Активности (УБА)

По IMPLEMENTATIONPLAN §6 §3.1 (полная формула там).

- [ ] Celery task: пересчёт УБА каждый час, кеш в `User.business_activity_level`.
- [ ] `F_norm = min(завершённых рейсов за 90 дней / 3 / 8, 1.0)`.
- [ ] `Q_norm = min(log₁₀(Q+1) / log₁₀(51), 1.0)` — только сделки с **двумя** DealVault-фото.
- [ ] `V_norm = min(log₁₀(V+1) / log₁₀(50001), 1.0)` — сумма `Order.declared_value` по closed deals.
- [ ] `D_factor = 1.0 + 0.5 × min(MAX(Collateral.amount) / 5000, 1.0)` — бонус от 1.0 до 1.5.
- [ ] `УБА = round(F_norm × Q_norm × V_norm × D_factor × 1000)`.
- [ ] Маппинг на уровень: 0–49 Новичок / 50–199 Проверенный / 200–449 Надёжный / 450–749 Доверенный / 750–1000 Элита.
- [ ] Отображение в профиле и карточке участника (заглушка → реальное значение).
**Acceptance:** УБА пересчитывается автоматически; Q засчитывает только полностью задокументированные сделки; без залога factor = 1.0 (не ноль); уровень отображается в профиле.

### T3.2 — Оператор-арбитр и споры
- [ ] Роль `Operator` + консоль.
- [ ] `Dispute`, `OperatorAccessGrant` (доступ к DealVault по запросу стороны).
- [ ] Вердикт фиксируется в `DealEvent`; при наличии эскроу (Фаза 5) — разблокировка.
**Acceptance:** спор открывается, оператор изучает DealVault, выносит вердикт; всё в логе.

---

## 💳 ЭТАП 4 — Карточные платежи (Фаза 4)

### T4.1 — Платежи на платформе (карта)
- [ ] `Payment` (card), комиссия платформы.
- [ ] Интеграция карточного процессинга.
- [ ] Все транзакции пишут событие в `DealEvent`.
**Acceptance:** карточная оплата проходит на платформе, событие фиксируется, берётся комиссия.

---

## 🔐 ЭТАП 5 — Крипто-эскроу (Фаза 5)

### T5.1 — Эскроу BTC (HodlHodl-схема) и залог
- [ ] `Escrow`, `Collateral`.
- [ ] 2-of-3 multisig (плательщик / перевозчик / платформа-арбитр); релиз 2 подписи.
- [ ] Ключ арбитра у платформы; подпись только при споре.
- [ ] Некастодиальный кошелёк для возвратов.
- [ ] Фи за безопасную сделку (эскроу) — основной поток монетизации.
**Acceptance:** для дорогого груза залог блокируется и разблокируется по 2-of-3; платформа не держит средств; берётся эскроу-фи.

### T5.2 — USDT-эскроу
- [ ] Аналог BTC-эскроу для USDT (не-кастодиальная 2-of-3 / арбитр-подпись).
**Acceptance:** USDT-сделка обеспечивается без кастодиальности.

---

## ✨ ЭТАП 6 — Премиум + IPFS-портативность (Фаза 6)

### T6.1 — Премиум (хранение документов + учёт)
- [ ] `PremiumSubscription`, хранилище документов, отчёты/экспорт.
**Acceptance:** подписчик хранит документы и получает учётные отчёты.

### T6.2 — DealVault → IPFS
- [ ] SHA-256 → multihash → CID для каждого `Attachment`; пин в IPFS; запись `ipfs_cid`.
- [ ] `DealVaultMessage` сериализуется как signed Nostr event JSON; пин в IPFS; CID сохраняется.
- [ ] Экспорт полного DealVault сделки как IPFS DAG; CID корня = верификационный хеш.
**Acceptance:** каждое вложение имеет CID; CID верифицируется по SHA-256; полный DealVault экспортируется и проверяется без платформы.

### T6.3 — Полная Nostr + IPFS портативность
- [ ] Экспорт пакета аккаунта: профиль, все DealVault как Nostr-события, CID вложений.
- [ ] Аккаунт совместим с Nostr-клиентами: npub идентифицирует, события проверяемы.
- [ ] Решение по операторской/админ-панели зафиксировано в Decision Log TECHSTATE.
**Acceptance:** пакет данных экспортируется и верифицируется; аккаунт работает в Nostr-клиенте.

---

## ✅ Критерий финиша V1

V1 завершена, если:
Отправитель и Перевозчик находят друг друга на платформе, согласуют условия, фиксируют **передачу и получение фото в иммутабельном Чёрном ящике**, проходят статусы доставки до подтверждения получения — и всё это **в спокойной, безопасной визуальной среде**, без иллюзии, что платформа везёт сама или держит деньги. (Оплата на этом этапе — вне платформы / лично.)

---

### 🔒 Правила (Reminder)
- Для начала работы: берите `T0.1`.
- Не знаете, что дальше? Берите следующую задачу со статусом `[ ]`.
- Сделали задачу? Ставьте `[x]`, опишите сделанное, синхронизируйте TECHSTATE/ENVIRONMENT/CHANGELOG.
- **После каждой выполненной задачи обновить `frontend/src/version.ts`** по схеме `0.{фаза:02}.{задача}` (например, T1.12 → `0.01.12`). Это обязательно.
