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
> - **Тесты (ОБЯЗАТЕЛЬНО после T_TEST.1) — 100% покрытие новой функциональности:** каждая задача обязана закрываться только после того, как:
>   1. **Все новые endpoints backend** покрыты тестами (positive + negative кейсы).
>   2. **Все новые ветки в существующих endpoints** покрыты (например, новое поле в PATCH — отдельный тест).
>   3. Весь backend-сьют проходит зелёным: `docker compose -f docker-compose.dev.yml exec -w /app backend pytest -v`.
>   4. Frontend-сборка не падает: `docker compose exec frontend npm run build` (если менялся frontend).
>   Проактивно предлагать недостающие тесты, не ждать напоминания. Правила изоляции — ENVIRONMENT.md §8. До завершения T_TEST.1 правило не применяется. Frontend-компоненты будут покрыты в T_TEST.2.
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
- [x] `POST /api/invites` — генерация InviteLink (одноразовая, TTL 14 дней — было 7, увеличено в T1.14).
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

### T1.10 — База аэропортов + геолокация ✅
- [x] Файл `backend/app/data/airports.dat` (OpenFlights, 7698 записей, 1.1 МБ) хранится **в репозитории**; при старте backend читает его локально в память (`list[Airport]` с dataclass `Airport{iata, city, country, lat, lon}`). Работает офлайн.
- [x] Скрипт `backend/scripts/update_airports.py` — скачивает свежую версию с `https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat` и перезаписывает файл. Запускается вручную.
- [x] `GET /api/airports?q=` — поиск с ранжированием: exact IATA → IATA prefix → city prefix → substring в city/country; до 10 результатов.
- [x] `GET /api/airports/nearest?lat=&lon=&limit=5` — Haversine, отсортировано по расстоянию.
- [x] Названия города и страны — на английском (OpenFlights).
- [x] Фронтенд: `AirportSelect` — autocomplete (200ms debounce), дропдаун `max-h-[9rem]` (~3 строки видно, дальше прокрутка), кнопка-иконка геолокации, click-outside закрывает.
- [x] Кнопка геолокации: `navigator.geolocation.getCurrentPosition` → `nearestAirports` (limit=10) → дропдаун с ближайшими.
- [x] `AirportSelect` подключён в `NewTripPage` (origin/destination) и в форме заявки `TripsPage` (origin/destination).
- [x] Тесты backend (`test_airports.py`): search by IATA, search by city, empty query, лимит 10, nearest Dubai, nearest default limit, invalid coords 422.
- [x] i18n-ключ `trips.useGeolocation` во всех 5 локалях.
**Acceptance:** поиск отдаёт релевантные аэропорты; геолокация показывает ближайшие; выбранное значение — IATA-код; backend стартует без интернета; все тесты зелёные. ✅

### T1.11 — Телефон в профиль; убрать из регистрации ✅
- [x] Убрать поле «Телефон» из RegisterPage; email обязателен.
- [x] В ProfilePage — поле телефона: `CountryCodeSelect` (флаг + код через `libphonenumber-js/min`, названия стран через нативный `Intl.DisplayNames` — локализованы автоматически) + numeric input + кнопка Save.
- [x] При загрузке существующего `user.phone` — парсится через `parsePhoneNumberFromString`, ISO страны и national number раскладываются в поля.
- [x] Сохранение: `+{dial}{national}` → `PATCH /api/auth/me` (эндпоинт уже был готов в T1.7).
- [x] Миграция не нужна (`phone` уже nullable).
- [x] i18n-ключи `profile.phoneSelectCountry`, `profile.phoneSearchCountry` во всех 5 локалях.
- [x] Backend-тесты: `test_patch_me_updates_phone`, `test_register_without_phone_succeeds`.
**Acceptance:** регистрация проходит без телефона (только email + пароль); в ЛК можно выбрать страну (с поиском по названию на языке UI) и ввести номер, сохранить; при повторной загрузке страна и номер восстанавливаются. ✅

### T1.12 — Мобильная версия (responsive) ✅
- [x] Tailwind breakpoints (`sm:` / `md:`) на страницах; layout mobile-first.
- [x] Нижняя навигация (`BottomNav`) — 4 иконки (Dashboard/Trips/Deals/Profile), только `md:hidden`; десктопная навигация в Navbar скрыта на мобильном (`hidden md:flex`); Layout добавляет `pb-24` под BottomNav.
- [x] Логотип «Vimana» кликабельный (ведёт на `/`) — частично закрывает T1.15.
- [x] Формы (Login/Register/NewTrip/Trips filter/Profile phone/DealVault): поля на всю ширину, тач-зоны `min-h-[2.75rem]` (44px+).
- [x] Карточки рейсов/сделок: `flex-col sm:flex-row`, grid `grid-cols-1 sm:grid-cols-2`.
- [x] `DealPage` boarding pass: header стакается вертикально на мобильном, ID сделки `break-all`, кнопки действий стакаются.
- [x] `DealVaultPage`-чат: адаптивная высота `h-[calc(100vh-8rem)]`, форма отправки и выбор типа фото — flex-wrap.
- [x] `AirportSelect` и `CountryCodeSelect` — dropdown корректно открываются на мобильном благодаря `absolute` + `w-full` / `w-72`.
**Acceptance:** ключевые флоу проходятся на мобильном экране (375-390px) без горизонтального скролла и мелких тач-целей. ✅

### T1.13 — Локализация: UK→UA, добавить RU, endonym-переключатель ✅
- [x] Переименован `frontend/src/i18n/locales/uk.json` → `ua.json`; импорты в `i18n/index.ts` обновлены (`ua: {...}`).
- [x] Правило: Ukraine всегда сокращается до **UA**.
- [x] Миграция localStorage: `LEGACY_LANG_MAP = { uk: 'ua' }` при инициализации; старое `lang=uk` перезаписывается на `lang=ua`.
- [x] Создан `frontend/src/i18n/locales/ru.json` — все ключи `en.json` переведены (nav, auth, common, dashboard, trips, deals, profile).
- [x] Добавлен `ru` в `i18n/index.ts`. Итого 6 языков: EN / UA / RU / PL / FR / ES.
- [x] `LanguageSwitcher.tsx` переработан как **выпадающий список** с endonym-названиями:
  - `en` → **English**, `ua` → **Українська**, `ru` → **Русский**, `pl` → **Polski**, `fr` → **Français**, `es` → **Español**.
  - Кнопка-триггер компактная (endonym + chevron), click-outside закрывает, активный язык подсвечен `text-cyan bg-cyan/5`.
  - Без флагов.
**Acceptance:** переключатель — компактный dropdown; открытие показывает 6 языков endonym-названиями; выбор мгновенно меняет UI; сохраняется в localStorage; старые пользователи с `lang=uk` автоматически на `ua`. ✅

### T1.14 — Раздел «Инвайты» в личном кабинете ✅
- [x] Бэкенд: `GET /api/invites/mine` — список инвайтов, созданных текущим юзером; поля: `token`, `created_at`, `expires_at`, `status` ∈ {`pending`, `accepted`, `expired`}, `accepted_by_display_name` (nullable).
- [x] Статус вычисляется на бэке: `accepted` если `used_by != null`; `expired` если `expires_at < now()`; иначе `pending`. `accepted_by_display_name` подгружается одним запросом по `used_by`.
- [x] TTL инвайта увеличен с 7 до **14 дней** (`INVITE_TTL_DAYS = 14` в `app/api/social.py`).
- [x] В `ProfilePage` — секция «Мои инвайты» между «Контактами» и «Уведомлениями»:
  - Кнопка «+ Создать инвайт» — вызывает `POST /api/invites`, затем перезагружает список.
  - Список: бейдж статуса (цвет по статусу), для `pending` — мелким текстом «истекает через 3д 4ч» (формат **только дни + часы, без минут**).
  - Для `accepted` — «→ {display_name}»; для `pending` — кнопка «Copy link» на `{origin}/invite/{token}`.
- [x] i18n-ключи `profile.invites`, `profile.inviteCreate`, `profile.noInvites`, `profile.inviteExpiresIn`, `profile.inviteCopy`, `profile.inviteStatus.{pending,accepted,expired}` — во всех 6 локалях.
- [x] Backend-тесты: `test_create_invite_ttl_is_14_days`, `test_list_my_invites_returns_pending_status`, `test_list_my_invites_reflects_accepted`, `test_list_my_invites_empty_for_new_user`.
**Acceptance:** в ЛК видно список выданных инвайтов со статусом и обратным отсчётом «3д 4ч»; можно создать новый инвайт; после принятия статус меняется на «Принят» с именем принявшего; ссылка копируется. ✅

### T1.15 — UX-полишинг: формы, логин, логотип ✅
- [x] **Персистентность форм в браузере** через универсальный хук `usePersistedState(key, initial)` в `frontend/src/hooks/`:
  - `LoginPage`: `loginVal` (email/phone) сохраняется в `localStorage['login:login']`. Пароль **не** сохраняется.
  - `RegisterPage`: `displayName`, `email`, `isCarrier` сохраняются (`register:*`). Пароль **не** сохраняется.
  - `TripsPage`: фильтры `origin`, `destination`, `date` сохраняются (`trips:filter:*`).
- [x] **Логин case-insensitive**:
  - Фронт: input `login` уже с `autoCapitalize="none"`, `autoCorrect="off"`, `spellCheck={false}` (сделано в T1.11 для email/login).
  - Бэк: при регистрации email нормализуется в lowercase; при логине сравнение через `.strip().lower()`. Whitespace обрезается. Пароль остаётся case-sensitive.
- [x] **Кликабельный логотип «Vimana»** — в `Navbar.tsx` обёрнут в `<Link to="/">` с hover-состоянием (сделано в T1.12). На публичных LoginPage/RegisterPage остаётся декоративный `<h1>`.
- [x] Backend-тесты: `test_register_normalizes_email_lowercase`, `test_login_is_case_insensitive_for_email`, `test_login_trims_whitespace`.
**Acceptance:** повторный вход не требует набирать email заново; логин работает независимо от регистра и лишних пробелов; клик по логотипу возвращает на Dashboard. ✅

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
