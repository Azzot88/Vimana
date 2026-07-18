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

### T1.16 — Cascade выбор аэропорта: страна → город → аэропорт + мультиязычный поиск ✅
- [x] Backend: `Airport` обогащён полем `country_iso` (ISO 3166-1 alpha-2). Маппинг `country_name → iso` через `pycountry` + alias-словарь (Russia, South Korea, Vietnam, Iran, Taiwan и др.) для нестандартных имён OpenFlights.
- [x] Backend endpoints:
  - `GET /api/airports/countries` — `[{iso, count}]`, сортировка по количеству desc.
  - `GET /api/airports/cities?country=XX` — `[{city, count}]`, сортировка по количеству desc.
  - `GET /api/airports/by-city?country=XX&city=Y` — список аэропортов; 404 если пусто.
- [x] Frontend: `AirportSelect` переработан как **unified search + subtitle** (вариант A):
  - Одно поле input; dropdown группирован по 3 секциям — Countries / Cities / Airports.
  - Страны — локализованы через `Intl.DisplayNames(i18n.language, {type:'region'})`; поиск на UI-языке **и** английском.
  - Клик по стране → dropdown фильтруется по стране, чип-подзаголовок 🇦🇪 UAE появляется над полем мелким жирным шрифтом.
  - Клик по городу → чип 🇦🇪 UAE · Dubai, dropdown показывает аэропорты города.
  - Клик по аэропорту → в поле IATA, чип остаётся; кнопка «×» очищает.
  - Backend endpoint `GET /api/airports/lookup?q=` возвращает cities + airports одним запросом.
- [x] **Мультиязычный поиск городов** через GeoNames `cities15000.txt` (5MB в репо, ~34k городов с `alternatenames` — переводы на десятки языков: кириллица, китайский, арабский, ...). `Airport` обогащён полями `alt_names` (все переводы города) и `population`. Пример: user печатает **«Москва»** → находится Moscow (RU) → аэропорты MOW/DME/SVO/VKO.
- [x] **Сортировка аэропортов внутри города по популярности**: `airports_in_city` сортирует по OpenFlights `order` (id из датасета — старые/крупные хабы идут первыми). Пример: Dubai → DXB (id=2188) перед DWC (id=8681).
- [x] Backend-тесты (11): countries, cities, by-city (positive/404), country_iso, lookup positive/empty, cyrillic Moscow (search + lookup), Ukrainian Київ, DXB sorted first in Dubai.
- [x] i18n-ключи `airports.{notWorking,selectCountry,selectCity,selectAirport}` + `common.search` — во всех 6 локалях.
**Acceptance:** пользователь без геолокации через 3 клика (страна → город → аэропорт) выбирает нужный аэропорт; названия стран локализованы на 6 языков; поиск страны работает и на английском, и на языке UI. ✅

### T1.17 — Расширяемые категории груза (animal + custom) ✅
- [x] Backend: новая модель `Category(id, name_key, is_default, usage_count, created_at)`. Дефолтные категории засеиваются миграцией `0003_category_freeform.py`: `document, medicine, electronics, gift, animal, other`.
- [x] Enum `OrderCategory` удалён; `Order.category` теперь `String(50)`. Миграция: `ALTER TABLE ... TYPE VARCHAR(50) USING ...; DROP TYPE ordercategory`. Backfill не нужен (enum-values уже совместимы с текстом).
- [x] Endpoints:
  - `GET /api/categories?q=` — поиск по substring; сортировка `is_default DESC, usage_count DESC, name_key ASC`; до 15 результатов.
  - `POST /api/deals/match` — если `category` не в справочнике, создаётся запись `is_default=false`; при повторе `usage_count += 1`.
- [x] Frontend: `CategorySelect` компонент с autocomplete + allow-new (Enter добавляет custom). `TripsPage` (форма заявки) — одиночный выбор. `NewTripPage` (allowed_categories) — chip-мультивыбор через тот же компонент.
- [x] i18n: `categories.{document,medicine,electronics,gift,animal,other,placeholder,addNew}` в 6 локалях. Пользовательские категории — показываются как ввёл создатель.
- [x] Backend-тесты (5): defaults включают animal, `is_default` отмечен, поиск по префиксу, новая категория регистрируется при match, `usage_count` инкрементируется.
**Acceptance:** в форме заявки/рейса пользователь видит autocomplete со всеми категориями (включая animal); может ввести свою (например, «drone»); категория появляется в общей базе и доступна другим. ✅

### T1.18 — Лендинг + Waitlist: главная страница и сбор email-адресов ✅

**Контекст:** `LandingPage.tsx` (React, ~486 строк, bento-дизайн) стал публичной главной страницей `/`. Аутентифицированное приложение переехало на `/dashboard`. Уведомления админу пошли через **Telegram** (SMTP-подтверждение пользователю отложено — см. ниже).

- [x] **Модель:** `WaitlistEntry(id, email, name, source, created_at)` — миграция `0004_waitlist.py`. Поле `notified_at` отложено вместе с SMTP.
- [x] **Backend endpoints:**
  - `POST /api/waitlist` — принять `{email, name?, source?}`; email нормализуется (`.strip().lower()`); дубликат → `409 Conflict`; невалид → `422`; иначе `201 Created` + Telegram-уведомление админам через `send_telegram` в цикле по `ADMIN_TELEGRAM_CHAT_IDS`.
  - `GET /api/waitlist` — список всех заявок; защита через header `X-Admin-Token` (сравнивается с env `ADMIN_API_TOKEN`); отсутствие/несовпадение → `403`.
- [x] **Уведомления админу через Telegram** (вместо SMTP на этом этапе):
  - Используется существующий `send_telegram` из T1.7 (bot token уже настроен).
  - Сообщение: `Vimana · Waitlist +1\n{email}\n{name?}\nsource: {source?}`.
- [x] **Frontend `LandingPage.tsx`:** модалка + `POST /api/waitlist` (source `'landing'`); ошибочные ответы больше не показываются как успех — рендерится `submitError` под кнопкой; сбрасывается при `closeModal`. При 409 всё равно считается успехом («Вы уже в списке»).
- [x] **Роутинг:** `/` → `LandingPage` (публичный); `/dashboard` → `DashboardPage` (protected); `Navbar` логотип и Dashboard-линк ведут на `/dashboard`. Аутентифицированный пользователь на `/` автоматически редиректится на `/dashboard`.
- [x] **Backend-тесты (7):** success (201), нормализация email (upper→lower + trim), duplicate (409), invalid email (422), list без токена (403), list с неверным токеном (403), list с правильным токеном (200 + запись присутствует).
- [x] `.env.example` дополнен: `ADMIN_API_TOKEN`, `ADMIN_TELEGRAM_CHAT_IDS`.

**Acceptance:** форма на лендинге сохраняет email в БД; админу приходит Telegram-уведомление; повторная попытка с тем же email → 409 без дублирования; список доступен по admin-токену; все тесты зелёные. ✅

**Отложено на потом (не блокирует V1):**
- SMTP-подтверждение пользователю с текстом «Vimana · You're on the list» + «Safe skies».
- Поле `notified_at` в модели для отслеживания отправки писем.
- Отдельная Celery-задача `send_waitlist_confirmation`.

### T1.8 — Staging-деплой, домен и smoke test V1 ✅
- [x] AWS EC2 (Ubuntu 22+), Docker + Docker Compose установлены и работают.
- [x] Elastic IP получен, домен `vimana.dealvault.club` привязан A-записью.
- [x] `.env` заполнен prod-значениями (`CORS_ORIGINS=https://vimana.dealvault.club`, `ADMIN_API_TOKEN`, `ADMIN_TELEGRAM_CHAT_IDS`).
- [x] Alembic мигрирован до `0004_waitlist`.
- [x] Nginx с SSL: TLS 1.2/1.3, HTTP→HTTPS редирект, ACME challenge на 80, `.well-known/acme-challenge/` через webroot, `X-Forwarded-Proto https` во все upstream'ы, `client_max_body_size 15M` для DealVault аттачей.
- [x] Let's Encrypt сертификат получен через `certbot certonly --standalone -d vimana.dealvault.club`; `/etc/letsencrypt` смонтирован в nginx read-only.
- [x] Cron автообновления сертификата: `0 3 * * *` с `--pre-hook` (stop nginx) / `--post-hook` (start nginx).
- [x] Smoke test: сайт открывается по HTTPS (валидный сертификат); в `docker compose logs backend nginx | grep -i error` — пусто.
**Acceptance:** приложение доступно по `https://vimana.dealvault.club`; SSL валидный; в логах контейнеров нет критических ошибок. ✅

> **🎉 ФИНИШ V1** — Фаза 1 (Ядро доверия) завершена. Приложение в продакшн-доступе.
> Дальнейшие шаги перед открытием для реальных пользователей — T1.19 (pre-production hardening).

### T1.19 — Pre-production hardening (перед открытием для реальных пользователей)

> **Контекст:** глубокое ревью кодовой базы (2026-07-06) обнаружило 5 групп критичных проблем, которые не блокируют staging, но обязательны до открытия для внешних пользователей.

- [ ] **Race conditions — атомарные upsert'ы:**
  - `Category` в `POST /deals/match` (`api/deals.py:44-51`): заменить read-modify-write на Postgres `INSERT ... ON CONFLICT (name_key) DO UPDATE SET usage_count = categories.usage_count + 1 RETURNING *`.
  - `InviteLink accept` в `api/social.py:86-123`: добавить `UNIQUE(user_id, connected_user_id)` на `Connection`; условный `UPDATE invite_links SET used_by = :uid WHERE token = :t AND used_by IS NULL` — 0 rows → 409.
  - `WaitlistEntry`: обернуть `db.add(...)` в `try/except IntegrityError → 409` (сейчас race → 500).
  - `Trip.status` при `match_deal`: `SELECT ... FOR UPDATE` + перевод в `matched` (если бизнес-правило — один груз на рейс).
- [ ] **Upload attachment безопасность** (`api/dealvault.py:113-161`):
  - Лимит размера `MAX_UPLOAD_SIZE = 10MB` (config), проверка через заголовок `Content-Length` до чтения.
  - Стриминг SHA-256 + upload в R2 через `iter_chunks(65536)` вместо `file.read()` целиком.
  - Whitelist MIME по `kind`: `image/{jpeg,png,heic,webp}` для `handoff_photo`/`receipt_photo`, `application/pdf` + images для `doc`.
  - Санитизация extension: только whitelist, ключ `r2_key` без пользовательских частей (только uuid).
- [ ] **CORS + rate limiting + admin token:**
  - `CORS_ORIGINS` — жёсткий whitelist в prod (`vimana.dealvault.club`), убрать `*`.
  - `slowapi` (или nginx `limit_req`): `/api/auth/login` — 5/минуту/IP; `/api/waitlist` — 3/минуту/IP; `/api/dealvault/.../attachments` — 20/минуту/user.
  - Admin token comparison через `secrets.compare_digest` вместо `!=` (`api/waitlist.py:47`).
  - Telegram webhook: секретный path (`/api/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}`) или Telegram `secret_token` header.
- [ ] **Pagination:**
  - Cursor-based (`?after=<uuid>&limit=50`) для `GET /deals`, `GET /trips`, `GET /deals/{id}/dealvault`, `GET /waitlist`.
  - Ответ формата `{items: [...], next_cursor: "..."}` для всех коллекций.
  - Обновить frontend: infinite-scroll или «Загрузить ещё» для длинных списков.
- [ ] **Error handling + logging + JWT rotation:**
  - Global exception handler в `main.py`: `@app.exception_handler(Exception)` → `{error: {code, message, request_id}}` + `logging.exception(...)`.
  - Заменить все `except Exception: pass` (в `core/telegram.py:10-13`, `core/whatsapp.py:15-16`, `api/waitlist.py:75-78`, frontend `catch { /* silent */ }`) на `logger.exception(...)` (backend) / user-facing error (frontend).
  - JWT rotation: короткий `access_token` (15 мин) + `refresh_token` (30 дней) с полем `User.token_version`; endpoint `POST /api/auth/refresh`.
- [ ] **Обязательно перед V1.1:**
  - Обновить `dependency_overrides` в `conftest.py` для новых зависимостей (rate limit, exception handler).
  - Новые backend-тесты: concurrent upsert категорий (`asyncio.gather`), upload > 10MB → 413, wrong MIME → 415, rate limit trigger 429, admin timing-safe compare, pagination cursor.

**Acceptance:** конкурентные запросы не создают дубликатов и не роняют 500; upload не жрёт RAM и валидирует MIME; брутфорс `/login` блокируется на 6-м запросе; списки поддерживают пагинацию; unhandled exceptions логируются и возвращают стандартный JSON. Все тесты зелёные (ожидаемо: 78 + ~15 новых).

### T1.20 — Cloudflare R2 / S3 setup для DealVault-аттачей ✅

**Контекст:** сейчас `storage.py:16-26` работает в graceful-degradation режиме — если `R2_ENDPOINT` пуст, `upload_file` возвращает key без реальной записи, `get_presigned_url` возвращает `None`. Фотографии в DealVault и inquiry-чате не загружаются в UI.

- [x] Заведён Cloudflare R2 bucket `vimana` (endpoint `https://1742351dcc4d64320934d6659abdef6f.r2.cloudflarestorage.com/vimana`).
- [x] Bucket policy: **private** (default), доступ только через presigned URL.
- [x] CORS: разрешён домен приложения.
- [x] API-ключ с правами PutObject/GetObject/DeleteObject.
- [x] `.env` prod: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT`.
- [x] Проверено: `POST /api/deals/{id}/dealvault/messages/{mid}/attachments` → 201 с валидным `url`; `GET /health/storage` → 200 reachable.
- [x] Фронтенд рендерит `<img>` из presigned URL; лайтбокс открывает полноразмер.
- [x] Мониторинг расходов: R2 — 10 ГБ бесплатно/мес, egress = $0.

**Acceptance:** пользователь может загрузить фото в DealVault через UI; фото открывается по presigned URL; в логах нет ошибок storage; расходы в пределах free tier. ✅

### T1.21 — At-rest шифрование сообщений DealVault (Фаза 1, переходное) ✅

**Контекст:** до появления Nostr-keypair (T2.2) и threshold-encryption (T2.3) сообщения должны быть **не в открытом виде** в БД. Реализуем symmetric AES-256-GCM с server-side ключом из env — защищает от утечки БД и любопытного read-only админа. Сервер расшифровать может (не e2e), но это честно позиционируется как «encrypted at rest».

- [x] Env: `MESSAGE_ENCRYPTION_KEY` — 32 байта base64 (`openssl rand -base64 32`); отсутствие ключа → `RuntimeError` при первом encrypt/decrypt (fail-loud).
- [x] `app/core/crypto.py`: `encrypt(plaintext) → (nonce, ct)`, `decrypt(nonce, ct) → plaintext`. AES-256-GCM через `cryptography==44.0.0`.
- [x] `DealVaultMessage`: колонки `text_ciphertext: bytes`, `text_nonce: bytes` (BYTEA); `text` — Python property (getter расшифровывает, setter шифрует). Существующий код `DealVaultMessage(text=...)` работает без изменений через SQLAlchemy `setattr`.
- [x] Миграция `0007_encrypt_messages.py`: добавляет колонки, шифрует существующий `text`, удаляет старую колонку. Идемпотентная.
- [x] `_build_message_out` возвращает plaintext через `msg.text` (property decrypt on the fly).
- [x] Аналогично будет применено к `InquiryMessage` в T1.22 (модель ещё не создана).
- [x] Backend-тесты (7): roundtrip, разные nonce, missing key → RuntimeError, bad key length, DB хранит bytes, API отдаёт plaintext, system-message тоже шифруется.
- [x] Прямой SQL `SELECT text_ciphertext FROM deal_vault_messages LIMIT 1` — bytes, не читается глазом.

**Acceptance:** сообщения хранятся в шифрованном виде; API отдаёт plaintext (сервер расшифровывает); dump БД без ключа = мусор; 119/119 тестов зелёные. ✅

### T1.22 — Right-side inquiry chat panel + модель `TripInquiry` ✅

**Контекст:** пользователь хочет чат «до сделки» — sender открывает опубликованный рейс, справа появляется панель для общения с carrier'ом. Начинает заявку — панель остаётся. После `match_deal` — история переносится в DealVault (или ссылается на неё). Все сообщения — через `InquiryMessage` с at-rest шифрованием из T1.21.

- [x] Модели:
  - `TripInquiry(id, trip_id, sender_id, carrier_id, deal_id nullable, created_at)` — UNIQUE(trip_id, sender_id).
  - `InquiryMessage(id, inquiry_id, sender_id, text_ciphertext, text_nonce, created_at)` — та же схема шифрования, что у DealVaultMessage.
- [x] Миграция `0008_inquiry.py` — идемпотентная, guard'ы через `information_schema.tables`.
- [x] Endpoints:
  - `POST /api/trips/{trip_id}/inquiry` — идемпотентно создаёт или возвращает существующий тред.
  - `GET /api/inquiries` — список моих тредов (как sender и как carrier).
  - `GET /api/inquiries/{id}/messages` — cursor pagination, ASC.
  - `POST /api/inquiries/{id}/messages` — проверка `user ∈ {sender, carrier}`.
- [x] `POST /deals/match` — при наличии `TripInquiry(trip, sender)` линкует `inquiry.deal_id = new_deal.id`.
- [x] Frontend:
  - `InquiryPanel.tsx` — правая панель `w-[380px]` на десктопе, full-screen drawer с backdrop-blur на мобиле.
  - Открывается кнопкой «Chat» на карточке рейса в `TripsPage`.
  - Cyan-пузыри свои / ivory-пузыри чужие, время в футере, auto-scroll, «🔒 encrypted at rest» индикатор.
- [x] Backend-тесты (8): open thread, идемпотентность, own trip → 400, encrypted roundtrip, outsider → 403, empty message → 422, inquiry.deal_id линкуется после match, carrier видит свои inquiries.
- [x] i18n: `inquiry.*` (9 ключей) + `common.close` в 6 языках.

**Acceptance:** sender видит рейс → справа появляется чат; отправляет сообщение → carrier видит; после `match_deal` `inquiry.deal_id` линкуется; сообщения зашифрованы (BYTEA в БД); mobile → drawer; 127/127 backend тестов зелёные; `npm run build` без ошибок. ✅

### T1.23 — User Zero + роль arbiter + модель Dispute (invite-only доступ) ✅

**Контекст:** нужен супер-юзер с правом видеть всех пользователей и назначать арбитров, плюс отдельная роль арбитра. Арбитр читает переписку **только по приглашению** (через `Dispute`), когда один из участников не выходит на связь при незавершённой перевозке. Открытие переписки арбитром **явно** пишется в чат (`DealEvent.arbiter_opened` + автосообщение в DealVault) — обе стороны видят. Полноценный threshold-decryption придёт в T2.3; пока — заглушка доступа при валидном Dispute.

- [x] **User Zero:** `User.is_superuser: bool`, миграция 0006 промоутит `nyxter@dealvault.club`; startup-hook `ensure_user_zero()` идемпотентный. Superuser автоматически имеет все права арбитра.
- [x] **Роль arbiter:** `User.is_arbiter: bool`; один аккаунт может быть sender+carrier+arbiter одновременно; арбитр не может судить свою сделку (403).
- [x] **Модель `Dispute`:** `id, deal_id, opened_by, arbiter_id nullable, reason, status ∈ {open, claimed, resolved}, verdict nullable, created_at, resolved_at`. UNIQUE(deal_id).
- [x] **Endpoints:** `POST /api/deals/{id}/dispute`, `GET /api/admin/disputes`, `POST /api/disputes/{id}/claim`, `GET /api/admin/deals/{id}/vault` (с audit trail: `DealEvent(arbiter_opened)` + system-message), `POST /api/disputes/{id}/resolve`, `GET /api/admin/users`, `POST /api/admin/users/{id}/promote-arbiter`.
- [x] **Deps:** `get_arbiter`, `get_superuser` в `app/api/deps.py`.
- [x] **Скрипт `scripts/make_arbiter.py <email> [--off]`** — backup путь для superuser'а.
- [x] **Frontend:** DealPage — кнопка «Open dispute» + модалка с textarea; DealVaultPage — красный баннер при arbiter_opened system-message; `/admin/disputes` (арбитр/superuser) с claim/resolve/view; `/admin/users` (superuser) с toggle «Make/Revoke arbiter»; `/admin/deals/{id}/vault` — вид арбитра с audit-notice; Navbar показывает Disputes/Users только флажным.
- [x] Backend-тесты (9): open by participant/outsider/duplicate, arbiter cannot claim own deal, vault access without claim → 403, with claim → 200 + audit, admin users requires superuser, promote-arbiter only by superuser.
- [x] i18n `dispute.*`, `admin.*`, `nav.disputes/users` в 6 языках.

**Acceptance:** User Zero (`nyxter@dealvault.club`) видит всех пользователей и назначает арбитров. Арбитр открывает переписку только через claimed Dispute; при открытии — запись в `DealEvent` + system-message в чате. Один аккаунт может быть sender/carrier/arbiter одновременно. 127/127 backend + чистый `npm run build`. ✅

### T1.24 — Dual role + RBAC permissions + explicit mode switcher ✅

**Контекст:** сейчас `User.is_carrier: bool` — один из двух. Реальные пользователи могут и везти, и отправлять — платформа должна разрешать оба режима без пересоздания аккаунта. UI режимов **явно разный** (визуально), но текущий режим **не подписывается** — понимание идёт из контекста. Кнопка переключения показывает **противоположный** режим: «Switch to Deliver» когда ты sender, «Switch to Send» когда ты carrier. **По ходу выполнения — заменили ad-hoc булевы флаги (`is_superuser`/`is_arbiter`) на permission-based RBAC** (`app/core/permissions.py`), см. миграция 0010.

- [x] Миграция `0009_dual_role` — `can_carry`, `can_send`, `active_mode`; backfill из `is_carrier`; drop legacy.
- [x] Миграция `0010_role_permissions` — единая колонка `user.role` заменяет `is_superuser`+`is_arbiter`; идемпотентный backfill.
- [x] `app/core/permissions.py` — `Permission` enum (8 permissions), `Role` enum, `ROLE_PERMISSIONS` map, `perms_of()`, `require()`, `require_perm()` FastAPI-фабрика. Мост между capabilities (can_carry → TRIP_PUBLISH) и ролями.
- [x] `POST /api/trips` — проверяет `can_carry`; endpoints admin.py — через `Depends(require_perm(...))`.
- [x] `UserOut` schema без `is_carrier`/`is_superuser`/`is_arbiter`; `role` string + `can_carry`, `can_send`, `active_mode`.
- [x] `PATCH /api/auth/me` принимает `active_mode`, `can_carry`, `can_send`.
- [x] `conftest.py` + все тесты обновлены под новую модель.
- [x] Frontend `User` тип обновлён; `lib/permissions.ts` — зеркало backend; auth store `switchMode()`; admin страницы + Navbar под role check.
- [x] `ModeSwitcher.tsx` — кнопка в Navbar, текст **противоположного** режима, скрыта если недоступно (`can_carry=false` блокирует переход в carrier). Иконка 📤 в carrier / ✈️ в sender.
- [x] Визуальное различие в `DashboardPage`: cyan-gradient bar + ✈️ в carrier mode; amber + 📦 в sender mode. Основной CTA: «Publish trip» (cyan) для carrier / «Find a trip» (amber) для sender. Режим текстом **не подписан**.
- [x] i18n `mode.switchToSend`/`mode.switchToDeliver` в 6 языках.
- [x] Backend-тесты (7 dual_role + 6 permissions): PATCH active_mode, `can_carry=false` → 403, invalid mode → 422, deriv-таблица permissions.

**Acceptance:** пользователь видит явную кнопку переключения (текст противоположного режима); клик меняет визуальный акцент Dashboard; `can_carry=false` → 403 на POST /trips; backend-схема без `is_carrier`/`is_superuser`/`is_arbiter`; 140/140 backend тестов зелёные; frontend build без ошибок. ✅

### T1.25 — NewTripPage redesign (главное окно создания рейса, hook-points для EXP) ✅

**Контекст:** сейчас `NewTripPage.tsx` — линейная форма с 6 полями. По мере роста платформы это становится главным touch-point'ом для перевозчика (создание рейса — самая частая операция после логина). Redesign — превратить в **основное окно рейса**: Bento-компоновка (по BENTO_DESIGN_SKILL) с яркими зонами (карта маршрута, категории, capacity, preview). Одновременно **закладываем hook-points** для будущих экспериментов из MASTERPLAN §10: `EXP-03` Voice Input, `EXP-04` Ticket Scan — оба лягут на этот же экран.

- [ ] **Bento layout** (`md:grid md:grid-cols-3 md:gap-4`, ячейки 1×1, 2×1, 1×2):
  - **Route cell (2×1)** — origin/destination AirportSelect в единой карточке с большой моно-типографикой между ними («DXB → JFK»).
  - **Date & Time cell (1×1)** — календарь + время вылета.
  - **Capacity cell (1×1)** — слайдер kg (0.5 – 20 кг) с визуальным indicator.
  - **Categories cell (1×2)** — checkboxes с иконками (document/medicine/electronics/…) + free-text override.
  - **Preview cell (2×1, sticky bottom)** — «карточка рейса как она будет выглядеть в ленте» — real-time preview с той же типографикой что и в списке TripsPage. Photo of route line if API есть, иначе схематичный рисунок.
  - **Publish cell (1×1)** — большая амбер-кнопка «Publish trip» + маленькая опция «также как Nostr-event» (checkbox, включён по умолчанию после T3.5).
- [ ] **Hook-points для экспериментов (feature-flagged sockets)**:
  - Верхний ряд карточки-заголовка — три иконки в углу: `🎤` (Voice, `EXP_VOICE_INPUT`), `📷` (Scan ticket, `EXP_TICKET_SCAN`), `⌨️` (обычный ввод, default). Клик по 🎤/📷 при выключенном флаге — tooltip «coming soon».
  - Флаги читаются из `import.meta.env.VITE_EXP_*` (build-time) или из user-настроек в профиле (runtime).
- [ ] **UX улучшения:**
  - Автосохранение draft в localStorage (`trips:draft`) — если пользователь закрыл вкладку, при возврате форма prefilled.
  - Клавиатурный shortcut `Cmd+Enter` для publish.
  - Валидация: не даём отправить с прошедшей датой; предупреждение если capacity > 15 кг (unusual).
- [ ] Frontend-тесты (vitest): все 6 ячеек рендерятся, submit собирает валидный JSON, hook-icons показывают tooltip если флаги off.
- [ ] Backend без изменений — API `POST /api/trips` уже готов из T1.4.
- [ ] Обновить `frontend/src/version.ts` до `0.01.25`.

**Acceptance:** перевозчик открывает `/trips/new`, видит красивую Bento-сетку с preview снизу; publish создаёт рейс; форма запоминается при перезагрузке; иконки hook-points видны и готовы принять EXP-03/EXP-04 без переработки layout'а.

### T1.26 — Receiving Address в профиле (private + share by button) ✅

**Контекст:** удобство отправителей, когда я — получатель. Один основной адрес, хранится приватно на моей стороне; никто не видит его без явного share. При inquiry/DealVault-чате появляется кнопка «📍 Share my address» — адрес отправляется в чат как system-message с красивой карточкой (страна, город, улица, индекс, note). Приватность по умолчанию — принцип «не показывать пока не решил показать».

- [ ] **Модель** — расширение `User` (миграция `0011_receiving_address`):
  - `receiving_country_iso: str | None` — ISO 3166-1 alpha-2 (напр. `AE`, `US`).
  - `receiving_city: str | None` — название города (может отличаться от GeoNames базы если пользователь ввёл вручную).
  - `receiving_city_geoname_id: int | None` — опциональная связь с GeoNames для стандартизации/фильтров.
  - `receiving_street: str | None` — улица, дом, квартира.
  - `receiving_postal_code: str | None` — индекс.
  - `receiving_note: str | None` — этаж, домофон, ориентир, время приёма (свободный текст ≤500 симв).
  - **Индексов и уникальности нет** — адрес приватный, поиск по нему не нужен.

- [ ] **Endpoints:**
  - `PATCH /api/auth/me` расширен полями `receiving_*` (все optional, все обновляемы отдельно).
  - `GET /api/cities?q=<prefix>&country=<iso>` — новый endpoint для autocomplete городов. Использует **существующий GeoNames dataset** из T1.16 (`cities15000.txt`) — 34k городов с alt_names (мультиязычный поиск уже работает). Возвращает `[{geoname_id, name, country_iso, population}]`, top 10.
  - `GET /api/countries` — уже существует из T1.16 cascade, переиспользуем.
  - `POST /api/deals/{id}/dealvault/messages/share-address` — helper endpoint: копирует текущий `user.receiving_*` в новое `DealVaultMessage(is_system=true, text=formatted_address)`. Один вызов — одно system-message.
  - `POST /api/inquiries/{id}/messages/share-address` — то же для inquiry-чата.

- [ ] **Приватность:**
  - Адрес отдаётся **только** через `GET /api/auth/me` — владельцу.
  - **Никогда не в `UserOut` при list-endpoints** (`/admin/users` показывает всех — там `receiving_*` отсутствуют).
  - Однажды расшаренный через chat — становится частью `DealVaultMessage` (иммутабельно) и виден участникам сделки; это **осознанный выбор** пользователя.
  - Rate-limit на share-address: 5 per hour per deal (защита от спама-шаринга).

- [ ] **Формат system-message для share:**
  - `text` = многострочная markdown-подобная структура:
    ```
    📍 SHARED ADDRESS
    Country: {country_name_localized}
    City: {city}
    Street: {street}
    Postal: {postal_code}
    Note: {note}
    ```
  - Frontend парсит по префиксу `📍 SHARED ADDRESS` → рендерит как **карточку** вместо plain text: страна с флагом, копирование в clipboard, ссылка «Open in Maps» (google.com/maps/place/{urlencoded}).

- [ ] **Frontend (`ProfilePage.tsx`):**
  - Новая секция «Receiving address» между «Contacts» и «Notifications».
  - Форма:
    - **Country** — dropdown (existing `Intl.DisplayNames` из T1.11).
    - **City** — autocomplete из `GET /api/cities?q=&country=` (реиспользует поиск из T1.16 но по городам, не аэропортам). Optional override — пользователь может ввести не-GeoNames название вручную.
    - **Street** — text input.
    - **Postal code** — text input.
    - **Note** — textarea, placeholder «Floor 3, intercom 12, prefer weekends».
  - Save с автосохранением через `PATCH /me`.
  - Индикатор «🔒 Private — visible only to you until you share in a chat».

- [ ] **Frontend (`InquiryPanel.tsx` + `DealVaultPage.tsx`):**
  - Кнопка «📍 Share my address» рядом с input (только для sender-role в inquiry; для любой стороны в DealVault — получатель может тоже расшарить).
  - Клик → confirm-модалка «Share your saved address? Other party will see it.» → если yes → `POST /messages/share-address` → сообщение появляется в чате как карточка.
  - Если `user.receiving_country_iso === null` → tooltip «Set your address in profile first» + ссылка на профиль.

- [ ] **i18n**: `profile.address.*` (country, city, street, postal, note, saveHint, privacy) + `chat.shareAddress`, `chat.addressCard.*` в 6 языках.

- [ ] **Backend-тесты:**
  - `PATCH /me` с `receiving_*` полями → сохранение работает; `GET /me` возвращает.
  - `GET /admin/users` (superuser) → `receiving_*` **отсутствуют** в ответе.
  - `GET /api/cities?q=Dub&country=AE` → возвращает Dubai, Abu Dhabi (etc), top 10.
  - `POST /messages/share-address` без `receiving_country_iso` → 422 «address not set».
  - `POST /messages/share-address` → создаёт `is_system=true` message с правильным префиксом.
  - Rate-limit: 6-й share подряд в одной сделке → 429.
  - Chat participant не может прочитать чужой `receiving_*` через любой endpoint кроме message-share.

- [ ] Обновить `frontend/src/version.ts` до `0.01.26`.

**Acceptance:** пользователь заполняет адрес в профиле (страна/город с autocomplete/улица/индекс/note); адрес приватен по умолчанию (нет в public API); в inquiry- и DealVault-чате есть кнопка «📍 Share my address» → адрес попадает в чат как красивая карточка с копированием и Open in Maps; другой участник видит адрес только после явного share; никаких других способов узнать чужой адрес не существует.

---

## 🧪 ТЕСТИРОВАНИЕ — Расширение сьюта

> T_TEST.1 (базовый backend-сьют) перенесён вверх — сразу после T1.9, чтобы стать фундаментом. Правила изоляции — ENVIRONMENT.md §8. Каждая новая задача T1.x обязана добавлять свои тесты в этот сьют.

### T_TEST.2 — Frontend smoke-тесты ✅
- [x] `vitest` + `@testing-library/react` + `@testing-library/user-event` + `jsdom` + `@testing-library/jest-dom`.
- [x] `vite.config.ts` — блок `test` c `environment: 'jsdom'`, `globals: true`, `setupFiles: ['./src/test/setup.ts']`.
- [x] Setup: `jest-dom` matchers, `localStorage.clear()` + `cleanup()` в `afterEach`, mock `window.matchMedia`.
- [x] `renderWithProviders` — helper с `MemoryRouter` + `I18nextProvider`.
- [x] Smoke-тесты (7 кейсов):
  - `LoginPage`: заголовок, subtitle, оба input'а, link на /register, version badge.
  - `RegisterPage`: name + email + password inputs; **phone НЕ рендерится**; carrier checkbox.
  - `LanguageSwitcher`: dropdown с 6 endonym-названиями; выбор меняет `i18n.language` и `localStorage['lang']`.
  - `StatusBadge`: рендерит переведённый label (accepted → «Accepted»/«Принято»/…).
- [x] Скрипты `npm test` (watch) и `npm run test:run` (one-shot).
**Acceptance:** `docker compose exec frontend npm run test:run` проходит; тесты не требуют сервера/бэкенда; сборка `npm run build` не ломается. ✅

---

## 🪪 ЭТАП 2 — Идентификация и ключи (Фаза 2)

### T2.1 — Peer Identity Verification + Verification Levels (P2P KYC) ✅ MVP

> **Статус:** MVP (backend + frontend) закрыт 2026-07-17. Остаётся follow-up: реальный PaddleOCR (сейчас `doc_type`/`doc_country` из body), реальный OFAC/EU sanctions match (сейчас stub `clean`), self-custody upload path (сейчас 422 — ожидает T2.3 threshold).

**Контекст:** классический regulatory KYC/AML уезжает в Фазу 4 (T4.1) — до того как через платформу пойдут деньги, у нас нет обязательств перед регулятором раскрывать identity пользователей. Вместо этого в Фазе 2 вводим **три уровня верификации** для любого пользователя:

| Level | Название | Кто/чем проверяет | Trust weight | Стоимость |
|---|---|---|---|---|
| **1** | `auto` | Локальный OCR (PaddleOCR) + санкционный чек (OFAC SDN, EU) | Слабый (документ мог быть фальшивым) | Бесплатно |
| **2** | `peer` | Другой участник платформы (sender подтверждает carrier или наоборот) в момент передачи | Сильный (человек видел документ) | Бесплатно, но требует встречи |
| **3** | `kyc` | Regulatory KYC-провайдер (Sumsub/Onfido/Jumio) из Фазы 4 | Легальный вес (формальная валидация) | Платно (Фаза 4+) |

**Идея:** сеть сама подтверждает своих участников — платформа хранит **зашифрованный контейнер** (владелец получает ключ через T2.2 Nostr-keypair), уровни накапливаются. **Перевозчик тоже может стать owner'ом** контейнера — по желанию, для получения verified-badge (см. §T2.1.3 ниже). При отказе перевозчика показывать документы — **никаких санкций**, в отличие от sender'а: чат получает уважительное системное сообщение «В целях собственной безопасности перевозчик решил не раскрывать своё имя».

- [ ] **Модели:**
  - `VerificationLevel` enum: `auto` / `peer` / `kyc`. Порядок соответствует силе доверия.
  - `VerificationRequest(id, deal_id, requested_by_id, target_role ∈ {sender, carrier}, status ∈ {pending, upload, later_in_person, declined, verified, escalated}, created_at, resolved_at)`. `target_role=carrier` для запросов перевозчику; asymmetric UX ниже.
  - `IdentityContainer(id, owner_id, owner_role ∈ {sender, carrier, both}, blob_encrypted BYTEA, doc_hash, doc_country, doc_type, sanctions_check_status, created_at)` — encrypted at rest, ключ = owner's Nostr nsec из T2.2. **Роль владельца — sender ИЛИ carrier ИЛИ both** (пользователь в dual-role из T1.24 может использовать один контейнер в обоих режимах). Multi-doc allowed.
  - `VerificationBadge(id, subject_id, level ∈ VerificationLevel, source ∈ {auto_ocr, peer, arbiter_review, kyc_provider}, container_ref_id, verified_by_id?, in_deal_id?, verified_at, expires_at?, revoked_at?)` — append-only событие сети. Замена `PeerVerification` — одна модель для всех trust-источников. `verified_by_id` nullable: для `auto` — null, для `peer` — user, для `kyc_provider` — reference на `KycRecord.id` в Фазе 4.
  - Индекс `(subject_id, level, revoked_at IS NULL)` для быстрого получения highest active level.

- [ ] **Уровневая логика:**
  - `user.highest_verification_level: VerificationLevel | None` — денормализованное поле в User, обновляется при `VerificationBadge` INSERT (Celery hook или DB trigger). MAX по всем не-revoked badges.
  - **Аккумуляция**: один пользователь может иметь одновременно и `auto`, и `peer`, и `kyc` — они не заменяют, а накапливаются. UI показывает highest, но detail view — все.
  - **Expiry**: `kyc` badge со сроком `expires_at` (по данным провайдера); `peer` — бессрочно (пока не revoked); `auto` — 12 месяцев (санкционные списки обновляются, требуется re-check).
  - **Revoke**: verifier может отозвать peer-verification в течение 30 дней (если понял что документ фальшивый); арбитр может revoke любую badge через escalation.
- [ ] **Три варианта ответа отправителя на VerificationRequest (`target_role=sender`):**
  1. `later_in_person` → «Покажу лично при встрече». В момент передачи перевозчик через приложение фотографирует (OCR) **или** визуально проверяет (`method=in_person_visual`, без загрузки — только запись факта).
  2. `declined` → «Не готов показывать». Deal получает пометку `verification_declined`, перевозчик вправе отказаться (`deal.status → cancelled`). У отправителя на профиле — badge «declined verification N times».
  3. `upload` → «Показать сейчас». Открывается окно загрузки → фото на бэкенд → OCR + санкционный чек + шифрование → контейнер + `VerificationBadge(level=auto)` + запись в чат DealVault.

- [ ] **T2.1.3 — Carrier verification flow (симметричная опция, асимметричные последствия):**
  - **Опциональный upload перевозчиком:** в профиле новая секция «Verify identity» → загрузка документа → OCR + sanctions → `IdentityContainer(owner_role=carrier)` + `VerificationBadge(level=auto, source=auto_ocr)`. Badge появляется в профиле и на карточке Trip.
  - **Возможность peer-share:** sender может попросить carrier документы в момент передачи через `VerificationRequest(target_role=carrier)`. Три варианта ответа carrier'а:
    1. `upload_now` — загружает если хочет → `VerificationBadge(level=peer, verified_by=sender)`.
    2. `later_in_person` — показать в момент встречи, sender фото/визуально подтверждает.
    3. **`declined_polite`** → **НЕТ пометки declined**, **НЕТ последствий**. В чат уходит system-message: *«В целях собственной безопасности перевозчик решил не раскрывать своё имя. Sender вправе отменить сделку без штрафа.»* Sender может cancel или продолжить.
  - **Асимметрия обоснована**: перевозчик пересекает границы и его identity — оперативный риск для него, а не для sender'а; sender передаёт ценное — его identity нужна другой стороне как гарантия.
- [ ] **Badge на карточке Trip и в поиске:**
  - Endpoint `GET /api/trips` возвращает `carrier_verification_level: 'auto' | 'peer' | 'kyc' | null` (denormalized).
  - Frontend `TripsPage` → chip на карточке: `🔓 auto-verified` / `👤 peer-verified` / `🛡️ KYC-verified`. Кликабельный — открывает detail модалку.
  - Filter в поиске `?min_level=peer` — только рейсы от перевозчиков с ≥peer.
  - Sorting boost — verified выше в фиде (soft signal, weight ~1.2× base ranking).
- [ ] **Влияние на другие фазы:**
  - **Фаза 3 T3.1 (УБА)**: новый бонус-компонент `V_verify_factor` в формуле — множитель [1.0…1.3] в зависимости от highest verification level. `auto → 1.05`, `peer → 1.15`, `kyc → 1.3`. Обновляется в TECHSTATE §4 Phase 3 + IMPLEMENTATIONPLAN §6 §3.1.
  - **EXP-01 Missions**: `required_verification_level: VerificationLevel` — миссия видима только carrier'ам с ≥ указанного уровня.
  - **T6.4 ZK-Proof**: заменяет encrypted-blob на ZK-native вариант хранения — тот же API, другой backend (см. T6.4 обновление ниже).
- [ ] **Multi-document подтверждение** (по принципу US DMV):
  - Если у перевозчика есть сомнения → `POST /verification/{id}/request-additional` — просит второй документ (тип на выбор: паспорт / driver license / national ID / bank card).
  - Отправитель загружает через тот же флоу; несколько `IdentityContainer` привязываются к одной `PeerVerification`.
  - Порог верификации — параметр (например: 1 паспорт **или** 2 non-passport документа + facematch).
- [ ] **Escalation при подозрении на фальшивку:**
  - Перевозчик жмёт `POST /verification/{id}/escalate` с `reason` → создаётся `Dispute` (из T1.23) с типом `identity_fraud`, `deal.status → disputed`, чат замораживается для новых сообщений.
  - Арбитр видит и чат, и контейнеры (через уже существующий `require_perm(VAULT_READ_AS_ARBITER)` + новый `IDENTITY_CONTAINER_READ`).
  - **UX-открытый вопрос:** заморозка чата = read-only или полностью locked. Уточнить на этапе UI-дизайна T2.1.
- [ ] **OCR — локальный, без внешних API:**
  - **PaddleOCR** (лучше tesseract для MRZ-строк паспортов) как основной; tesseract как fallback.
  - Post-processing MRZ: парсим `<<` разделители, извлекаем name / dob / doc_number / issuing_country / expiry.
  - Для non-passport (driver license, bank card) — универсальный OCR по regex-паттернам страны.
  - Docker image: `paddleocr` + `tesseract` + модельки в `backend/models/ocr/`; ~1.5 GB, добавляется отдельный worker `ocr-worker` в docker-compose.
- [ ] **Санкционные списки — публичные CSV:**
  - **OFAC SDN** от treasury.gov — скачиваем ежедневно Celery-beat'ом, кешируем в Redis + Postgres таблица `sanctions_list(source, name_normalized, dob, country, added_at)`.
  - **EU consolidated financial sanctions list** — analog.
  - `POST /verification/{id}/check-sanctions` — сравнение по normalized name + dob (fuzzy match на level Levenshtein < 2). Результат в `IdentityContainer.sanctions_check_status ∈ {clean, match, review_needed}`.
- [ ] **Endpoints:**
  - `POST /api/deals/{id}/verification` — участник создаёт запрос, тело `{target_role: 'sender' | 'carrier'}`; в чат уходит system-message «⚠️ {actor} requested {target} identity verification».
  - `POST /api/deals/{id}/verification/{req_id}/respond` — target отвечает; для sender — 3 варианта (later/decline/upload), для carrier — 3 варианта (upload_now/later/decline_polite).
  - `POST /api/deals/{id}/verification/{req_id}/submit-document` — загрузка файла (multipart, MAX_UPLOAD_SIZE из T1.19).
  - `POST /api/deals/{id}/verification/{req_id}/request-additional` — multi-doc branch.
  - `POST /api/deals/{id}/verification/{req_id}/escalate` — вызов арбитра.
  - `POST /api/me/verification/self-upload` — self-inited upload (не в контексте сделки, для profile-verify) → создаёт `VerificationBadge(level=auto)` сразу.
  - `GET /api/users/{id}/verifications` — публичный список: highest level, breakdown по всем уровням (count по auto/peer/kyc), даты, verifiers для peer. **Без раскрытия документов.**
  - `POST /api/verifications/{badge_id}/revoke` — verifier может revoke свою peer-badge в течение 30 дней; арбитр — любую.
- [ ] **Permissions (расширение T1.24 RBAC):**
  - `IDENTITY_REQUEST` — участник сделки может создать VerificationRequest (в любую сторону).
  - `IDENTITY_SELF_UPLOAD` — любой user может self-verify свои документы.
  - `IDENTITY_CONTAINER_READ_OWN` — базовое право владельца читать свой контейнер.
  - `IDENTITY_CONTAINER_READ` — арбитр читает через escalation.
  - `VERIFICATION_REVOKE_OWN` — verifier revokes свою peer-badge в течение 30 дней.
  - `VERIFICATION_REVOKE_ANY` — только арбитр (any badge, any time).
- [ ] **Frontend:**
  - На `DealPage` в статусах `accepted`/`in_transit` — две кнопки: «Ask sender for ID» (для carrier), «Ask carrier for ID» (для sender). Обе доступны, вариант ответа определяется target_role.
  - Модалка ответа: для sender — 3 кнопки (later/decline/upload); для carrier — 3 кнопки (upload/later/polite decline). Copy отличается.
  - **Profile `Verify identity` section** (доступно всем): 3 tiles уровней — Auto (быстрый OCR self-upload) / Peer (get verified в момент передачи) / KYC (Фаза 4, disabled сейчас с надписью «coming with card payments»). Каждый tile показывает статус: not verified / verified at DATE / expired.
  - **Trip card**: chip verification-level справа от carrier name — `🔓 auto` / `👤 peer` / `🛡️ KYC`. Отсутствие — просто нет chip'а.
  - **Trip filter panel**: dropdown «Min verification level» с 4 опциями (any/auto+/peer+/kyc).
  - Профиль перевозчика — блок «Verified as carrier by N senders»; полезно как social proof.
  - При **polite decline** — красивое system-message в чате: «В целях собственной безопасности перевозчик решил не раскрывать своё имя. Отправитель вправе отменить сделку без штрафа.» — не красное, а нейтрально-серое; кнопка «Cancel deal» рядом.
- [ ] **Backend-тесты:**
  - Create/respond/submit флоу для sender (3 варианта) и carrier (3 варианта).
  - `polite decline` от carrier — system message появляется, deal НЕ помечен как cancelled, profile carrier'а НЕ получает `declined` badge.
  - Multi-doc: два контейнера привязаны к одному VerificationBadge.
  - Escalate → Dispute создаётся, deal.status = disputed.
  - Sanctions list match → `IdentityContainer.sanctions_check_status = 'match'`.
  - OCR extraction MRZ smoke-test (детерминированное тестовое фото).
  - Owner расшифровывает container, чужой user не может (owner-only decrypt).
  - **Level aggregation**: user с auto + peer badges → `highest_verification_level = peer`; после revoke peer → снова `auto`.
  - **Self-upload** flow: `POST /me/verification/self-upload` создаёт badge level=auto без Deal.
  - **Peer revoke**: verifier revokes свою badge в течение 30 дней → OK; после 30 дней → 403 (только арбитр).
  - **Trip API возвращает `carrier_verification_level`**: денормализация верна после INSERT/revoke badge.
- [ ] **i18n**: `verification.*` в 6 языках.

**Acceptance:**
- Перевозчик в чате может запросить документы отправителя; отправитель выбирает 1 из 3 (later/decline/upload).
- Отправитель в чате может запросить документы перевозчика; перевозчик выбирает 1 из 3 (upload/later/**polite decline без последствий**).
- Любой user может self-verify в профиле (level=auto) без Deal-контекста.
- При upload — файл проходит OCR + санкции + шифруется в контейнер, создаётся `VerificationBadge(level=auto)`.
- Multi-doc branch работает; escalation вызывает арбитра из T1.23; профиль показывает счётчик verifications без раскрытия содержимого.
- **Trip карточка показывает `carrier_verification_level` chip**; поисковый фильтр `min_level` работает.
- **User.highest_verification_level** денормализован и обновляется при INSERT/revoke.
- Regulatory KYC отсутствует — это Фаза 4 (level=kyc badge появляется тогда).
- **Асимметрия соблюдена**: sender declined = badge + возможная cancel; carrier declined = нейтральное сообщение, никаких последствий.

### T2.2 — Keypair + Nostr-совместимость (D10: Вариант A + D)

**Разбит на две части** по архитектурной причине: полный NIP-07 (D) требует backend signing в формате Nostr event (kind + tags + content, `event_id` per NIP-01), потому что browser-extensions (Alby, nos2x) могут подписать только event JSON, не произвольный хеш. Текущий backend signing = raw `sha256(canonical_json)` — годится для custodial (server держит nsec), но несовместим с NIP-07.

#### T2.2 pt.1 — Custodial + Keypair Management UI ✅ (backend + frontend)
- [x] При регистрации: генерация secp256k1-keypair; `nsec` шифруется AES-256-GCM с отдельным `NSEC_ENCRYPTION_KEY` (env, не MESSAGE_ENCRYPTION_KEY); `npub` → `User.nostr_pubkey`.
- [x] `User.key_self_custody: bool = False`; `User.nsec_encrypted BYTEA`, `User.nsec_nonce BYTEA` — миграция 0012 + backfill для существующих юзеров.
- [x] Server-side подпись: `DealVaultMessage` и `DealEvent` подписываются server-side через `sign_vault_message()` / `sign_deal_event()` (`app/core/signing.py`). Payload = canonical JSON + sha256 + Schnorr. `nostr_sig` заполняется во всех местах создания (dealvault.py, deals.py, admin.py). System messages (`sender_id=None`) не подписываются.
- [x] `GET /api/me/keypair/status` — `{npub, key_self_custody, has_encrypted_nsec}`.
- [x] `POST /api/me/keypair/export` — требует password re-auth; возвращает `{nsec_hex, npub_hex}`.
- [x] `POST /api/me/keypair/claim` — DELETE nsec_encrypted, `key_self_custody=True` (backend готов, но UI пока не даёт кнопку — см. pt.2).
- [x] `POST /api/me/keypair/import` — `{nsec_hex}` или `{npub_hex}`; всегда `key_self_custody=True`; foreign nsec **никогда** не сохраняется.
- [x] Frontend Keypair section в ProfilePage: показывает `npub`, статус custody, кнопки Export / Import (nsec или npub-only). Claim скрыт до pt.2. Детект `window.nostr` — показывает info-баннер «NIP-07 extension detected», без функциональности.
- [x] Backend-тесты (9+): keypair generation, nsec never plaintext in DB, export password re-auth, claim удаляет nsec, import с nsec / только npub, bad hex 422, server-signs new user's message, self-custody → 422 без pre-signed.
- [x] i18n `profile.keypair.*` в 6 языках.

**Acceptance pt.1:** новый аккаунт получает keypair; DealVault-события подписаны и верифицируемы через `verify_event(payload, sig, npub)`; user может увидеть свой npub, экспортировать nsec с re-auth, импортировать foreign keypair; в UI видно наличие NIP-07 extension (но клиент им ещё не пользуется). ✅

#### T2.2 pt.2 — NIP-07 signing + full self-custody ✅

- [x] **Backend refactor `signing.py`**: полноценный NIP-01 event формат — `event_id = sha256([0, pubkey, created_at, kind, tags, content])`. Kind: **4801** vault_message, **4802** deal_event. Tags vault_message: `[["k","vault_message"],["deal",<uuid>]]` (+ `["system","1"]` для системных). Tags deal_event: `[["k","deal_event"],["deal",<uuid>],["e",event_type]]`. Content vault_message = plaintext (client-reproducible); content deal_event = canonical JSON `{event_type, actor_id, payload}`.
- [x] Backend endpoints принимают `nostr_sig` + `nostr_created_at` (unix) в body; backend recomputes `event_id` с client-provided `created_at` (±5 min clock-skew guard).
- [x] `keypair.py`: `sign_event_id(event_id_hex, nsec)` / `verify_event_id(event_id, sig, npub)` — signing над готовым 32-byte id (NIP-01 стиль). Legacy `sign_event`/`verify_event` (pt.1 raw-hash) сохранены для старых записей.
- [x] Frontend `lib/nostr.ts` — `signVaultMessageViaNip07(dealId, text, isSystem)` через `window.nostr.signEvent()`, возвращает `{nostr_sig, nostr_created_at}`.
- [x] `api/dealvault.ts` — при self-custody + NIP-07 автоматически подписывает и добавляет поля в POST body. Custodial проходит без sig (сервер сам подпишет).
- [x] UI: кнопка «Claim self-custody» доступна если `has_encrypted_nsec && nip07`. Модалка с warn + hint + confirm.
- [x] Миграция подписей: старые pt.1 sigs остаются в БД неизменёнными (маркер — `nostr_event_id IS NULL`). Новые записи — всегда NIP-01. Dual-verify не понадобился (read-time verify пока не используется).
- [x] Асимметрия self-custody:
  - **Vault message** (user-authored content): строгий режим — self-custody без `nostr_sig` → 422.
  - **Deal event** (server-produced state change): лениво — self-custody → `nostr_sig=None`. Actor attribution via `actor_id` сохраняется.
- [x] Модель + миграция `0015`: `deal_vault_messages` и `deal_events` получают `nostr_event_id VARCHAR(64)`, `nostr_created_at BIGINT`, `nostr_pubkey VARCHAR(64)` (все nullable).
- [x] 7 backend-тестов: pre-signed accept + wrong sig + missing ts + stale ts + custodial NIP-01 event_id populated + self-custody deal event lenient + вспомогательный keypair-тест обновлён.
- [x] i18n `profile.keypair.claim*` в 6 языках + selfCustodyHint/nip07Detected обновлены.

**Acceptance pt.2:** self-custody user с Alby/nos2x подписывает vault-сообщения client-side; backend верифицирует по NIP-01 event_id; state-change endpoints остаются работоспособными для self-custody (unsigned). ✅

**Follow-up:** (1) добавить `nostr_sig`/`nostr_event_id`/`nostr_created_at`/`nostr_pubkey` в `InquiryMessage` (сейчас inquiry чат вообще без sig — вне scope pt.2). (2) Snapshot pubkey per-record уже есть, можно поднять read-time verify endpoint для аудита.

### T2.3 — Threshold-encryption 2-of-3 для DealVault (V2 замена at-rest) ✅ MVP

**Контекст:** T1.21 (at-rest AES с server-side ключом) был переходным — сервер видит plaintext. T2.3 переводит на **истинный end-to-end** с threshold 2-of-3: расшифровать могут любые 2 из 3 участников `{sender, carrier, arbiter}`. Один — не может, даже арбитр. Схема — Shamir's Secret Sharing над сессионным ключом сообщения. Зависит от T2.2 (Nostr secp256k1 keypair).

- [x] Библиотеки: **backend** — `cryptography` (AES-CBC PKCS7) + `coincurve` (secp256k1 ECDH сырой x-координаты, `PublicKey.multiply()`). **Frontend** — `@noble/ciphers` (AES-256-GCM), `@noble/curves` (secp256k1), `@noble/hashes` (utils), `shamir-secret-sharing`. Обмен ключами через **NIP-04** (совместим с Alby/nos2x — `window.nostr.nip04.encrypt/decrypt`).
- [x] Роль **арбитра** — platform arbiter: `User` с `role="arbiter"`, ID указывается в env `ARBITER_USER_ID`. Custodial nsec хранится через `NSEC_ENCRYPTION_KEY` (T2.2), сервер расшифровывает свою wrapped share при arbiter-reveal. Если env не задан → endpoint отвечает 503.
- [x] **Формат сообщения** (`E2EPayload`):
  ```
  {
    ciphertext: b64(AES-256-GCM(session_key, plaintext)),
    nonce: b64(gcm_nonce, 12 bytes),
    wrapped_shares: {
      sender:  <NIP-04 ct>,   // sender_priv → sender_pub
      carrier: <NIP-04 ct>,   // sender_priv → carrier_pub
      arbiter: <NIP-04 ct>    // sender_priv → arbiter_pub
    },
    read_packages: {          // session_key для нормального чтения
      sender:  <NIP-04 ct>,
      carrier: <NIP-04 ct>
    }
  }
  ```
  `wrapped_shares` используется только при dispute; `read_packages` — быстрый path для нормального чтения (клиент unwrap'нёт свой read_pkg NIP-07 расширением, получит session_key, дешифрует ciphertext).
- [x] Отправка (клиент `frontend/src/lib/threshold.ts::encryptE2E`):
  1. `session_key = random(32)`.
  2. `ciphertext = AES-256-GCM(session_key, plaintext)` через `@noble/ciphers/aes`.
  3. `shares = shamir.split(session_key, 3, 2)`.
  4. Каждая share NIP-04-обёрнута под соответствующий npub через `window.nostr.nip04.encrypt`.
  5. session_key дополнительно NIP-04-обёрнут в read_packages.sender/carrier.
- [x] Чтение (клиент `decryptE2E`):
  1. `session_key = nip04.decrypt(msg.nostr_pubkey, own_read_package)`.
  2. `plaintext = AES-GCM.decrypt(session_key, nonce, ciphertext)`.
- [x] Dispute-reveal (клиент `decryptFromShares`):
  1. Arbiter получает свою распакованную share через `/threshold/disputes/{deal_id}/arbiter-reveal`.
  2. Одна из сторон вручную даёт свою share (`POST /threshold/dealvault/messages/{id}/reveal-my-share` → own NIP-04 envelope → расшифровка через свой NIP-07).
  3. `session_key = shamir.combine([shareA, shareB])` → decrypt.
- [x] Endpoints (`backend/app/api/threshold.py`):
  - `GET /api/threshold/arbiter-info` — `{user_id, npub}` платформенного арбитра; 503 пока `ARBITER_USER_ID` не задан.
  - `POST /api/threshold/dealvault/messages/{id}/reveal-my-share` — возвращает свою NIP-04 wrapped_share для участника сделки (роль автоматически определяется по `sender_id`/`carrier_id`). 403 для не-участников.
  - `POST /api/threshold/disputes/{deal_id}/arbiter-reveal` — arbiter (permission `THRESHOLD_ARBITER_REVEAL`) при наличии открытого Dispute получает расшифрованные (сервером через custodial nsec) `arbiter_share_b64` для всех e2e-сообщений сделки + пишется `DealEvent(event_type=arbiter_opened, payload={kind:"arbiter_share_revealed", count:N})` как append-only audit.
- [x] Миграция `0016_threshold_encryption`: `deal_vault_messages` получает `is_e2e BOOLEAN DEFAULT false`, `wrapped_shares JSONB`, `read_packages JSONB`. Старые записи T1.21 остаются как есть (`is_e2e=false`). Backfill в **этой** миграции НЕ делается — старые сообщения продолжают шифроваться server-side, новые — client-side. Полная миграция всех записей — отдельный follow-up (нужен пользовательский flow "re-encrypt my history").
- [ ] UI (клиент):
  - Нормальный флоу: расшифровка прозрачна — user видит plaintext.
  - Спор: экран «попросить арбитра расшифровать» → confirm → фронт отправляет свою share.
  - Аудит: карточка «арбитр раскрыл share для спора» в timeline сделки.
- [ ] Backend-тесты: пакет с корректными 3 shares → шифруется; сервер не может recover session_key без 2 shares; audit trail при arbiter reveal; NIP-44 совместимость (event проверяем в Nostr-клиенте).

**Acceptance MVP ✅:** сервер сохраняет opaque blob (`is_e2e=true`), `msg.text` property возвращает None для e2e-записей → API не выдаёт plaintext даже при полном доступе к БД. Sender+carrier с NIP-07 расширением расшифровывают прозрачно через own read_package. Arbiter при open Dispute получает свою распакованную share через `/arbiter-reveal` + audit-событие. Не-участник получает 403 на `/reveal-my-share`. 9 backend-тестов (arbiter-info OK/503, e2e write, mutual-exclusive text vs e2e_payload, invalid shape 422, reveal-my-share sender/carrier, forbidden outsider, arbiter-reveal happy path + audit event + require-arbiter-role, NIP-04 round-trip sanity).

**Follow-up (документировано):**
1. **Backfill старых T1.21 сообщений в e2e** — отдельный user-инициированный flow «re-encrypt my history» (нужен доступ к текущим pubkey всех участников каждой сделки).
2. **Inquiry-чат** — пока не e2e (только DealVault); дублирование схемы на `InquiryMessage` — отдельный item.
3. **Attachments** — R2-загрузки пока не threshold-шифруются; в MVP файл_hash даёт целостность, но не конфиденциальность от сервера. Client-side chunk-encrypt перед presigned-upload — follow-up.
4. **NIP-44 v2** — сейчас NIP-04 (простой AES-CBC). Позже переехать на NIP-44 v2 (ChaCha20+HMAC, лучше защита от replay), когда extensions устаканятся.
5. **Custodial e2e fallback** — если ops хочет разрешить не-self-custody юзерам писать e2e, добавить server-side signing endpoint (backend расшифрует своё через NSEC_ENCRYPTION_KEY, session_key на сервере на мс — компромисс на безопасности).

### T2.4 — Trust Graph (Web-of-Trust) — круги доверия ✅ MVP

> **Статус:** MVP закрыт 2026-07-17 (миграция 0014). Follow-up: Redis-кэш BFS с TTL 5 мин (сейчас всё on-the-fly), UserBadge chip на TripCard, hourly Celery-task бэкапа counters (сейчас on-mutation refresh).

**Контекст:** T2.1 создаёт **атомарные** `VerificationBadge` записи. T2.4 превращает их в граф — «круги доверия». Первый круг = кого лично подтвердил; второй = кого подтвердили те, кого подтвердил я; N-й круг = глубина сети. Модель — транзитивный граф в духе Nostr WoT / PGP web-of-trust.

- [x] **Модели:** `TrustEdge(id, from_user_id, to_user_id, kind ∈ {peer_verified, dealt_with, invited}, weight FLOAT, source_ref, created_at, revoked_at)` + UNIQUE(from, to, kind, source_ref) + partial indexes на активных рёбрах.
  - `peer_verified` weight 1.0 — из T2.1 (MVP: авто-INSERT не сделан до T2.1 pt.2, где появится peer flow).
  - `dealt_with` weight 0.5 — auto-INSERT симметрично при `POST /deals/{id}/confirm` (см. app/api/deals.py).
  - `invited` weight 0.2 — auto-INSERT симметрично при `POST /invites/{token}/accept` (см. app/api/social.py).
- [x] **Sybil-guard**: `add_edge(kind=peer_verified, check_sybil=True)` требует closed/confirmed Deal между парой — иначе `SybilGuardError`. Проверка через `_pair_has_closed_deal()`. (Пометка «unverified sybil-risk» для новых аккаунтов — follow-up.)
- [x] **Endpoints:**
  - `GET /api/me/trust-circle?depth=N&kind=?` — BFS до глубины 1..6, `{depth, kind, circles: {"1": [...], "2": [...]}, total_reachable}`. Пропускает revoked, self-loops, deduplicated across levels.
  - `GET /api/users/{id}/trust-metrics` — публично `{subject_id, verifications_issued_count, verifications_received_count, dealt_with_count, distance_from_viewer}`. Distance null для self / unauthenticated.
- [x] **Денормализация**: `User.verifications_issued_count`, `verifications_received_count`, `dealt_with_count` (int, default 0). `refresh_trust_counts()` вызывается при `confirm_deal` и при manual add_edge. (Hourly Celery backup — follow-up.)
- [x] **Frontend `TrustCirclesSection` в ProfilePage**: 3 counter-tile'а, depth-selector 1–6, list кругов «N people at hop K». `getMyTrustCircle` + `getUserTrustMetrics`.
- [ ] `UserBadge` chip «You know them through 2 hops» на TripCard — **не сделан** (нужен endpoint для batch distance queries или отдельный запрос на каждую карточку — оптимизировать в T2.4 pt.2).
- [x] i18n `trust.*` в 6 языках (10 ключей с plural forms).
- [x] Backend-тесты: invite accept → symmetric invited edges, deal confirm → dealt_with edges + counts, BFS depth validation, kind filter validation, self trust-metrics (distance=None), Sybil-guard блокирует peer_verified без closed deal, идемпотентный insert, revoked edges не в BFS, refresh_trust_counts работает.

**Acceptance MVP:** пользователь видит в своём профиле counters + circles по уровням; закрытие deal автоматически добавляет `dealt_with`; принятие invite — `invited`; Sybil-guard откидывает peer_verified без deal. Distance from viewer доступен через `/users/{id}/trust-metrics`. ✅

---

## 📈 ЭТАП 3 — УБА и арбитраж (Фаза 3)

### T3.1 — Уровень Бизнес-Активности (УБА) ✅ MVP

По IMPLEMENTATIONPLAN §6 §3.1 (полная формула там).

- [x] Celery beat task `app.tasks.uba.recompute_all_uba` — раз в час пересчитывает УБА для всех user-ов, у кого был `Deal.created_at` за последние 90 дней (окно формулы). Кеш в `User.business_activity_level`.
- [x] `F_norm = min((F / 3) / 8, 1.0)` — F = closed deals как carrier за 90 дней; деление на 3 = месячная скорость.
- [x] `Q_norm = min(log₁₀(Q+1) / log₁₀(51), 1.0)` — Q = сделки с **обоими** DealVault-фото (`handoff_photo` + `receipt_photo` через `EXISTS` sub-queries).
- [x] `V_norm = min(log₁₀(V+1) / log₁₀(50001), 1.0)` — `SUM(Order.declared_value)` по closed deals как carrier.
- [x] `D_factor = 1.0 + 0.5 × min(D / 5000, 1.0)` — бонус от 1.0 до 1.5. **D=0 пока Collateral модели нет** (T5.x); factor остаётся 1.0 (нейтральный, не штраф).
- [x] **V_verify_factor** (T2.1 расширение): множитель `[null → 1.00, auto → 1.05, peer → 1.15, kyc → 1.30]`. Нормализуется на 1.30 (V_verify_norm = factor / 1.30) чтобы max УБА оставался 1000.
- [x] `УБА = round(F_norm × Q_norm × V_norm × D_factor × V_verify_norm × 1000)`, clamp [0, 1000].
- [x] Маппинг на уровень (slugs stable для i18n): `newbie` 0–49 / `verified` 50–199 / `reliable` 200–449 / `trusted` 450–749 / `elite` 750–1000. `level_of(uba)` → slug.
- [x] Endpoints: `GET /api/me/uba` + `GET /api/users/{id}/uba` — возвращают `{uba, level, components: {f_count, q_count, v_sum, d_peak, verify_level}}`. Компоненты пересчитываются on-demand; кеш обновляется одновременно.
- [x] Frontend: `UBASection` в профиле — число, level-chip с цветовой семантикой (navy/cyan/amber в градации), 4 tile'а компонент (F/Q/V/D). Плейсхолдер "Available in next phase" заменён живым виджетом.
- [x] i18n `profile.uba.*` (title/hint/levels.{newbie|verified|reliable|trusted|elite}/components.{f|q|v|d}+Hint) в 6 языках.
- [x] 10 backend-тестов: zero → 0, saturation → ≈1000, verify-factor scaling, D — мультипликатор не штраф, F монтжлы, Q log shape, level thresholds, level slugs stable, `/me/uba` для fresh user, `/users/{id}/uba` 404, e2e closed deal без фото → Q=0 → УБА=0.

**Acceptance ✅:** УБА пересчитывается по расписанию Celery beat; Q засчитывает **только** полностью задокументированные сделки (оба фото); без залога factor = 1.0 (нейтральный); уровень отображается в профиле.

**Follow-up:** (1) `Collateral` модель в T5.x → D_factor заработает; (2) UBA chip на карточке участника (TripCard/DealCard) — сейчас только в профиле; (3) миграция Redis-кэш для endpoint (`(user_id, quarter_hour)` TTL 15 мин) когда трафик вырастет.

### T3.2 — Оператор-арбитр и споры
- [ ] Роль `Operator` + консоль.
- [ ] `Dispute`, `OperatorAccessGrant` (доступ к DealVault по запросу стороны).
- [ ] Вердикт фиксируется в `DealEvent`; при наличии эскроу (Фаза 5) — разблокировка.
**Acceptance:** спор открывается, оператор изучает DealVault, выносит вердикт; всё в логе.

---

## 📡 ЭТАП 3.5 — Vimana Nostr Relay + Federation (Фаза 3.5)

### T3.5 — strfry-relay + publish trip-events + whitelist federation

**Контекст:** Vimana идёт по «Nostr-slope» (см. MASTERPLAN §7). Фаза 2 дала пользователям keypair, Фаза 3 закрыла арбитраж. Теперь запускаем **собственный Nostr-relay** и делаем каждый trip Nostr-событием: наши рейсы становятся видимыми в любом стандартном Nostr-клиенте (damus, amethyst, coracle), а пользователи получают точку внешней децентрализации своих данных. Subscribe (чтение чужих events) откладываем до Фазы 4+ — сначала осваиваем publish-стек и spam-protection.

- [ ] **Relay-runtime:** **strfry** — production-ready C++ relay от hoytech (LMDB storage, ~50 MB idle). Docker-контейнер `nostr-relay` в compose. NIP-01, NIP-11 (relay info), NIP-42 (auth), NIP-99 (classified listings).
- [ ] **Событийная модель trip:**
  - Kind: **30402** (NIP-99 Classified Listing, replaceable per `d`-tag).
  - Tags: `["d", trip_id]`, `["l", origin_iata]`, `["l", destination_iata]`, `["t", "vimana"]`, `["t", "trip"]`, `["published_at", ts]`, `["expires_at", depart_at]`, `["capacity", "kg"]`, для каждой allowed_category — отдельный `["t", cat]`.
  - Content: JSON `{origin, destination, depart_at, capacity, allowed_categories, carrier_pubkey, platform_url}`.
  - Подписывается **user's nsec** (из T2.2) — не платформенным ключом.
- [ ] **Publish bridge:**
  - При `POST /api/trips` (после Postgres commit) отправляется в Celery task `publish_trip_to_nostr(trip_id)`.
  - Task формирует Nostr event, подписывает user's nsec (через `decrypt_nsec` из T2.2 или через NIP-07 pre-signed event с фронта), публикует в свой relay + broadcast в **whitelist friendly relays**.
  - Идемпотентность через `Trip.nostr_event_id` (unique) — повторный publish обновляет replaceable event.
  - При `DELETE trip` (или status → cancelled) — публикуется event kind 5 (deletion request).
- [ ] **Whitelist friendly relays** (конфиг):
  - `NOSTR_FRIENDLY_RELAYS=wss://relay.damus.io,wss://nostr.wine,wss://relay.nostr.band` — Env variable, comma-separated.
  - Фиксируется список в TECHSTATE D-NOSTR-FEDERATION с обновлением каждые 3-6 мес по популярности.
- [ ] **Auth & abuse prevention (наш relay):**
  - NIP-42 auth: только зарегистрированные Vimana-npub могут писать.
  - Rate-limit: 30 events/hour per pubkey (strfry native).
  - WoT-gate: события от npub не в T2.4 trust-graph — read-only permission на наш relay.
- [ ] **Env:**
  - `NOSTR_RELAY_URL` (наш публичный wss endpoint).
  - `NOSTR_RELAY_PRIVKEY` — служебный ключ для admin-событий (NIP-42 challenges, deletion).
  - `NOSTR_FRIENDLY_RELAYS` — whitelist.
- [ ] **Модель:** `Trip.nostr_event_id: str | None` (unique index), `Trip.nostr_published_at: datetime | None`.
- [ ] **Endpoints:**
  - `GET /api/trips/{id}/nostr-event` — возвращает Nostr event JSON (для верификации / экспорта).
  - `POST /api/nostr/republish` (admin) — force-republish в случае разрыва.
- [ ] **Мониторинг:** metric `nostr_publish_success_count`, `nostr_publish_error_count`, healthcheck `/health/nostr` — connectivity to friendly relays.

- [ ] **Multilingual publishing strategy (default approach D)**:
  - **Structured tags — universal, без перевода**: `l` (IATA), `depart_at` (ISO 8601), `capacity` (число+kg), `t` (category enum keys) — эти данные читаются любым Nostr-клиентом одинаково, наш frontend и внешние клиенты рендерят по своей локали через собственный i18n.
  - **Свободный текст описания рейса** (если пользователь его добавил) — публикуется **в оригинале + `["lang", <ISO 639-1>]`** тег. Один event, один `d`, ноль дублирования.
  - **Client-side translation в нашем frontend**: если `event.lang != user_ui_lang` — показываем translated inline с кнопкой «Show original». Backend `POST /api/nostr/translate` (deferred to Redis cache key `(event_id, target_lang)` TTL 30 дней). Provider — Claude Haiku (~$0.0002/call) либо DeepL Free API (500k символов/мес). Уточнить в TECHSTATE D-TRANSLATION при подходе к T3.5.
  - **Опциональная публикация переводов** — feature-флаг для пользователя (см. EXP-06). По умолчанию OFF: не мусорим relay-фиды 6× копиями.
  - **Все trip events всегда несут `lang` тег** — обязательное поле, даже если description пустой (для консистентности фильтров у клиентов).

- [ ] **Frontend:**
  - На `TripsPage`, `NewTripPage` — маленький badge «📡 Also on Nostr · npub…» с копированием event ID.
  - На карточке чужого trip — если `event.lang` не совпадает с UI-локалью → «🌐 translated» chip с tooltip «original in {lang}, click to see».
  - В профиле — секция «Nostr identity» с npub, ссылкой на relay, кнопкой export.
- [ ] Backend-тесты: publish → event попадает в наш relay (запрос через WebSocket subscriber); подпись валидна для user's npub; deletion event публикуется при cancelled; rate-limit срабатывает после 30 events; `lang` tag присутствует всегда; translation cache hit не делает LLM-call.
- [ ] i18n `nostr.*` в 6 языках.

**Acceptance:** после `POST /api/trips` — рейс появляется как kind 30402 event в нашем relay и минимум в 2 из friendly relays; любой Nostr-клиент, подписанный на `#t: vimana`, видит новые рейсы; deletion event корректно обрабатывается; всегда присутствует `lang` tag; наш frontend показывает translated текст для non-matching locale с кнопкой «show original». Vimana становится **видима в глобальной Nostr-сети на любом языке**.

---

## 💳 ЭТАП 4 — Карточные платежи + Regulatory KYC (Фаза 4)

### T4.1 — Классический regulatory KYC / AML

**Контекст:** до Фазы 4 через платформу не идут деньги — P2P-верификации (T2.1) достаточно для доверия между участниками. Перед вводом карточных платежей (T4.2) регулятор требует **формальный KYC** и санкционный скрининг: kyc-провайдер интегрируется, `KycRecord` привязывается к аккаунту, санкционный периметр коридоров становится жёстким блоком.

- [ ] Выбор провайдера — фиксируется в TECHSTATE Decision Log. Варианты:
  - **Sumsub** — популярный на СНГ/EU, ~€1.5/verification, поддержка 220+ стран.
  - **Onfido** — UK/EU/US, ~$1.5, лидер по SDK-качеству.
  - **Jumio** — enterprise, дороже, максимум коридоров.
- [ ] `KycRecord(id, user_id, provider, external_id, status ∈ {pending, verified, rejected, expired}, verified_at, expires_at, level)` — уровень зависит от suma/paйect (basic / enhanced).
- [ ] `ComplianceAck(id, user_id, doc_version, category, acknowledged_at)` — версионируемое подтверждение запрещёнки и ответственности.
- [ ] Санкционный периметр коридора: `CorridorRestriction(origin_country, destination_country, requires_kyc_level, blocked)` — таблица правил. При `POST /api/trips`, `POST /api/deals/match` — проверка.
- [ ] Webhook от провайдера → обновляет `KycRecord.status` → триггерит evaluation прав.
- [ ] Frontend: onboarding-модалка при первой попытке карточной оплаты; SDK провайдера в iframe/webview.
- [ ] Permissions (расширение RBAC): `PLATFORM_PAYMENT_INITIATE` — требует `KycRecord.status = verified`.
- [ ] Backend-тесты: user без KYC не может создать `Payment`; webhook меняет статус; санкционный чек блокирует match.

**Acceptance:** пользователь проходит formal KYC перед первой карточной оплатой; санкционный периметр коридоров блокирует запрещённые пары стран; ComplianceAck обязателен на каждую версию условий.

### T4.2 — Платежи на платформе (карта)
- [ ] `Payment` (card), комиссия платформы.
- [ ] Интеграция карточного процессинга.
- [ ] Все транзакции пишут событие в `DealEvent`.
- [ ] **Зависит от T4.1** — пользователь без verified KYC не может инициировать платёж.
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

### T6.4 — ZK-Proof of Verification (ZK-native migration for IdentityContainer)

**Контекст:** T2.1 хранит фото документов в encrypted-контейнере (доступен владельцу и через escalation арбитру). T6.4 — это **эволюционный путь**, не переписывание: тот же API `IdentityContainer` / `VerificationBadge`, но backend хранения заменяется на ZK-native. Пользователь может доказать «у меня есть валидный verified document» **не раскрывая сам документ и не полагаясь на платформу** как посредника. Даже platform admin не видит содержимое. Настоящий ZK-SNARK: proof генерируется на клиенте, проверяется криптографически без обращения к серверу с документом. Зависит от T2.1 (есть контейнер и badge-механика), T2.2 (есть keypair как identity anchor), и T3.5 (Nostr relay для публикации merkle-root'ов). Задача исследовательская — вероятно нужен приглашённый cryptographer.

**Стратегия миграции:**
- T2.1 создаёт `IdentityContainer.storage_mode = 'encrypted_blob'` (default).
- T6.4 добавляет `storage_mode = 'zk_snark'` — новые контейнеры пользователь может создать в ZK-native режиме.
- Оба режима сосуществуют. Старые контейнеры можно мигрировать (client-side re-encrypt через новую схему), но не обязательно.
- Все VerificationBadge остаются валидными между режимами — они ссылаются на container, а не на схему хранения.

- [ ] **Circuit** (Circom/halo2): доказательство `∃ passport : owner_pubkey = derive(passport.private_hash) AND passport.expiry > NOW AND hash(passport) ∈ set_of_verified_passport_hashes`.
- [ ] Merkle tree of verified passport hashes — обновляется on-chain-style Nostr event'ами; клиент строит proof membership.
- [ ] Runtime: **snarkjs** (Circom) или **halo2-wasm** для генерации proof в браузере (5-30 сек на mobile).
- [ ] Event формат: новый Nostr NIP (уточнить номер / propose upstream) — «verified identity proof», содержит только proof + npub.
- [ ] Endpoint `POST /api/verifications/proof` — верифицирует proof и записывает соотв. факт (без пересохранения identity).
- [ ] **UX:** переключатель в профиле «Reveal encrypted identity to platform» ↔ «Prove verification via ZK-proof». Для параноидальных пользователей — путь без хранения фото у платформы вообще.
- [ ] Совместимость: старая (T2.1) и новая (T6.4) системы работают параллельно; арбитр через escalation в T2.1 работает как раньше, но пользователи ZK-режима остаются приватными.
- [ ] Возможно: приглашение cryptographer'а для audit'а circuit'а — фиксируется в TECHSTATE.

**Acceptance:** пользователь генерирует ZK-proof в браузере; платформа принимает его без раскрытия документа; badge «Verified» на профиле показывается без хранения фото на сервере.

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
