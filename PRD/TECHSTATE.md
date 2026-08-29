# Vimana — Sacred Logistics · TECHSTATE.md

> FILL ──────────────────────────────
> Назначение: детальное состояние системы, связи компонентов, принятые tech-решения (Decision Log) и обнаруженная логика (Capture Discovered Logic).
> Когда обновлять: при изменении логики/моделей и каждый раз, когда разобрался, как работает блок системы (до завершения задачи).
> Что НЕ дублировать: стек/версии/инфра (живут в ENVIRONMENT), стратегию (MASTERPLAN), задачи (TASKS).
> Формат записи: Status — отметка готовности; Decision Log — Решение / Причина / Дата; Обнаруженная логика — Механика → файлы реализации.
> ───────────────────────────────────

---

> **АРХИВ ДЕТАЛЕЙ:** [archive/TECHSTATE_ARCHIVE_01.md](archive/TECHSTATE_ARCHIVE_01.md) — полные строки §1, §2 и §3.
> Здесь остались **имя механики, статус и файлы реализации**; объяснение «почему именно так» перенесено в архив.
>
> ⚠️ **Правило обращения к архиву — обязательное, игнорировать нельзя (PROJECT.md §6.4).** Архив не читается в начале
> сессии. Если задача трогает, переписывает или опирается на строку, у которой стоит `→ [детали]`, исполнитель
> **обязан остановиться и запросить у владельца разрешение** прочитать её, назвав якорь. Догадываться о содержании
> архива вместо запроса — нарушение правила.

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
| Уведомления (email + Telegram + WhatsApp) | 1 | 🟨 **код готов, доставку даёт только почта** (T1.7, 2026-08-06) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S09) |
| Интернационализация (i18n, 6 языков EN/UA/RU/PL/FR/ES) | 1 | ✅ готово (T1.9, T1.13, T_UX.9, 2026-08-08) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S10) |
| База аэропортов + геолокация (Haversine, D11) | 1 | ✅ готово (T1.10, T1.16) |
| Мобильная версия (responsive + BottomNav) | 1 | ✅ готово (T1.12) |
| Телефон в профиль (убран из регистрации) | 1 | ✅ готово (T1.11) |
| Расширяемые категории (Category модель + autocomplete) | 1 | ✅ готово (T1.17) |
| Waitlist + публичный Landing | 1 | ✅ готово (T1.18, T_UX.8, 2026-08-08) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S15) |
| SSL / HTTPS / staging deploy | 1 | ✅ готово (T1.8) |
| Pre-production hardening (race conditions, upload security, rate-limit, exception handler, cursor pagination) | 1 | ✅ готово (T1.19) |
| Relay по TLS (`wss://<домен>/relay`) | 3.5 | ✅ MVP (T_SEC.4, 2026-08-01) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S18) |
| Форма доступа к данным (индексы, N+1, блокирующий I/O) | сквозная | ✅ MVP (T_PERF.1, 2026-08-01) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S19) |
| Периметр контейнеров и запуск (публикация портов, пароль Redis, uvicorn без `--reload`, пин образа relay) | сквозная | ✅ готово (T_SEC.3, 2026-08-01) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S20) |
| IDOR-матрица из роутера + ZAP baseline | сквозная | ✅ MVP (T_TEST.7, 2026-08-03) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S21) |
| Нагрузка (k6) | сквозная | ✅ разобрано (T_TEST.6, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S22) |
| Деплой без простоя | сквозная | 🟨 дешёвая часть готова (T_OPS.1, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S23) |
| Доступность (axe-core) | сквозная | ✅ **9 из 9 страниц, 0 нарушений** (T_TEST.8, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S24) |
| Мутационное тестирование (mutmut) | сквозная | ✅ **87,5 % на `permissions.py`, 78,3 % на `threshold.py`** при пороге 60 % (T_TEST.10, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S25) |
| Cloudflare R2 / S3 storage для DealVault-аттачей | 1 | ✅ готово (T1.20) |
| At-rest AES-256-GCM шифрование DealVault-сообщений | 1 | ✅ готово (T1.21, T2.3) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S27) |
| Inquiry chat panel (TripInquiry + InquiryMessage) | 1 | ✅ готово (T1.22) |
| User Zero + Arbiter role + Dispute model (базовая механика) | 1→3 | ✅ готово (T1.23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S29) |
| Dual role (can_carry/can_send/active_mode) + RBAC (Permission enum + Role) | 1 | ✅ готово (T1.24) |
| NewTripPage redesign (Bento + hook-points для EXP-03/04) | 1 | ✅ готово (T1.25) |
| Receiving Address в профиле + share-in-chat | 1 | ✅ готово (T1.26) |
| Peer Identity Verification (P2P KYC) | 2 | ✅ MVP (T2.1, T2.3) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S33) |
| Trust Graph (Web-of-Trust) | 2 | ✅ MVP (T2.4) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S34) |
| Keypair + Nostr-совместимость (D10: A+D) | 2 | ✅ MVP → [детали](archive/TECHSTATE_ARCHIVE_01.md#S35) |
| Threshold 2-of-3 encryption (замена at-rest из T1.21) | 2 | ✅ MVP (T2.3, T_KEYS.1, 2026-08-02) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S36) |
| Уровень Бизнес-Активности (УБА) | 3 | ✅ MVP (T3.1) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S37) |
| Оператор-арбитр и споры + Access Grants | 3 | ✅ MVP (T3.2) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S38) |
| Recipient role в DealVault | 3 | ✅ MVP (T3.3) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S39) |
| Vimana Nostr Relay (strfry) + Federation | 3.5 | ✅ MVP (T3.5) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S40) |
| DealVault Protocol: полнота цепи (msgs/files/seal) + контент-валидация + identity-пересечение | 3.6 | ✅ MVP: T3.7 (T3.7, T3.8, T3.9) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S41) |
| DealVault: презентация + лендинг | 3.6 | 🟨 в работе (T3.10) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S42) |
| Лестница владения личностью (Identity Vault) | 3.7 | 🟨 решение принято, кода нет (, 2026-08-01) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S43) |
| Идентичность и вход (email-подтверждение, npub, Passkeys, step-up, recovery) | 3.7 | 🟨 в работе (T3.11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S44) |
| Правовой и информационный контур (условия, политика, «о нас», принятие с версией) | 4 | ⬜ не начато (T4.0, 2026-08-12) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S45) |
| Regulatory KYC/AML (только KYC-провайдер + person-level SDN) | 4 | ⬜ не начато (T4.1, T_UX.2) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S46) |
| Route notes + platform disclaimers | 3 | ✅ MVP (T_UX.2) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S47) |
| Multiple receiving addresses + Edit profile + avatars + landing on logo | 3 | ✅ MVP (T_UX.4) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S48) |
| Agentic MCP server | 3 → 7 | ✅ MVP кода (T_AGENT.1) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S49) |
| Контакты: `user_contacts` + один код-механизм на все каналы | 3.8 | 🟨 **T3.25 ✅ код готов** (T3.25, 2026-08-09) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S50) |
| Вход и регистрация одним полем (код-first) | 3.8 | ✅ MVP (T3.28, 2026-08-10) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S51) |
| Telegram как канал кода и способ входа | 3.8 | ✅ MVP (T3.27, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S52) |
| Лимиты на запрос кода | 3.8 | ✅ MVP (T3.29, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S53) |
| SMS и WhatsApp как каналы кода | 3.8 | ⬜ SMS ❌ не делаем (T3.30, T3.31, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S54) |
| Матрица оповещений «событие × канал» + локализация | 3.8 | ✅ MVP (T3.32, T3.33, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S55) |
| Письмо о входе с нового устройства | 3.8 | ✅ MVP (T_SEC.6, 2026-08-11) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S56) |
| Протокол сделки в чате: типизация карточек | 3.9 | ✅ MVP (T3.34, 2026-08-16) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S57) |
| Договор о сделке (`terms.*`) | 3.9 | ✅ MVP (T3.35, 2026-08-16) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S58) |
| Параметры бизнес-логики в админке | 3.9 | ✅ MVP (T3.40, 2026-08-16) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S59) |
| Карточки сделки: логистика, владение, расчёты, исключения | 3.9 | ✅ MVP (T3.36, T3.39, 2026-08-16) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S60) |
| Единицы, форматы и правила перевозки | — | ✅ MVP (T_UX.14, T_UX.15, 2026-08-16) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S61) |
| Навигация по режиму, страница перевозчика, панель | — | ✅ MVP (T_UX.18, T_UX.19, 2026-08-17) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S62) |
| Публичные страницы по аудиториям + панель по адресу режима | — | 🟨 в работе (T_UX.23, 2026-08-25) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S63) |
| Профиль: витрина и операционка | — | ✅ MVP (T_UX.21, T_UX.22, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S64) |
| Профиль: боковая навигация по разделам | — | ✅ MVP (T_UX.20, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S65) |
| Роль как предложение: журнал, принятие, складывающиеся роли | 3.11 | ✅ MVP (T3.42, 2026-08-29) |
| Правила коридора: модель, юрисдикции, предикаты | 3.11 | ✅ MVP (T3.11.01, 2026-08-29) |
| Правила коридора: редактор, цикл статусов, калитка публикации | 3.11 | ✅ MVP (T3.11.02, 2026-08-29) |
| Правила коридора: справочник, корпуса, чеклист, пакет | 3.11 | ⬜ не начато (T3.11.03 … T3.11.13) |
| Карточка создания рейса: переработка | 3.10 | ➡️ перенесена в T3.11.07 (T3.41, T1.25, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S66) |
| Роль как предложение: принятие и журнал | 3.10 | ⬜ не начато (T3.42, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S67) |
| Карточные платежи | 4 | ⬜ не начато (T4.2) |
| Эскроу BTC + Залог | 5 | ⬜ не начато |
| USDT-эскроу | 5 | ⬜ не начато |
| Премиум | 6 | ⬜ не начато |
| DealVault → IPFS | 6 | ⬜ не начато |
| Полная Nostr + IPFS портативность | 6 | ⬜ не начато |
| ZK-Proof of Verification | 6 | ⬜ не начато (T6.4) |
| DealVault на Pubky: распределённые сейфы, эпохи ключа, гардианы | 8 | ⬜ не начато (T8.1, T8.10, 2026-08-23) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S75) |
| Агентский доступ по сети (транспорт MCP) | 7 | ⬜ не начато (T7.1, 2026-07-30) → [детали](archive/TECHSTATE_ARCHIVE_01.md#S76) |

*(Обновлять по мере выполнения: ⬜ → 🟨 в работе → ✅ готово.)*

---

## 2. Decision Log (Решение / Причина / Дата)

| # | Решение | Причина | Дата |
|---|---|---|---|
| D1 | Стек: FastAPI + SQLAlchemy(async) + PostgreSQL + R2/S3 | Выбор владельца; зрелость, async, ACID для сделок | 2026-06 |
| D2 | Эскроу BTC по схеме 2-of-3 multisig (образец HodlHodl); платформа держит только ключ арбитра | Не-кастодиальность снижает регуляторный риск money-transmitter | 2026-06 |
| D3 | Вместо репутации | Метрика делом, устойчивее к накрутке отзывами → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D3) | 2026-06 |
| D4 | Фазы = функциональные блоки (простое+важное → сложное); V1 = только Ядро доверия без денег/эскроу | Быстрый честный MVP, повторяющий работающий рынок | 2026-06 |
| D5 | Иммутабельная запись доставки переименована в **DealVault** (ранее «Чёрный ящик»). Ядро Vimana и будущих проектов. IPFS-ready с Фазы 1 | Авиа-метафора + vault = tamper-proof хранилище; легко портируется в IPFS | 2026-06-27 |
| D6 (open) | Админ/операторская панель: Django Admin vs SQLAlchemy-совместимая (SQLAdmin/Piccolo/starlette-admin) | Django ORM конфликтует с SQLAlchemy-стеком; решить до Фазы 3 | TBD |
| D7 (open) | USDT-эскроу: целевая сеть и контрактная схема не-кастодиальной 2-of-3 | BTC-multisig не переносится 1-в-1 на USDT; проектировать в Фазе 5 | TBD |
| D8 (open) | Портативность: формат экспортируемого пакета | DealVault как Nostr event JSON → пин в IPFS → CID = верификационный хеш; реализация в Фазе 6 → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D8__open_) | TBD |
| D9 (open) | Docker-only dev как жёсткое правило (да/нет) | Подтвердить владельцем; влияет на онбординг исполнителей | TBD |
| D11 | **Геолокация аэропортов: Haversine в Python.** | Датасет мал (< 1 МБ); Haversine даёт ответ за микросекунды; Redis GEO и PostGIS избыточны → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D11) | 2026-06-28 |
| D10 | **Nostr-совместимость: Вариант A + D.** | Масс-маркет онбординг без барьеров + поддержка существующей Nostr-идентичности для продвинутых пользователей → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D10) | 2026-06-27 |
| D-NOSTR-RELAY | **Vimana Nostr Relay = strfry** | strfry — production-ready, лёгкий (~50 MB idle), нативная поддержка нужных NIP-ов; NIP-99 = стандартный market … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-NOSTR-RELAY) | 2026-07-12 |
| D-NOSTR-FEDERATION | **Стартовый whitelist** | Три relay покрывают три разных клиентских экосистемы (damus/iOS, coracle/web, nostr.band/search-first). Достат … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-NOSTR-FEDERATION) | 2026-07-18 |
| D-TRANSLATION (open) | Провайдер on-the-fly перевода Nostr-описаний для мультиязычного UI | Варианты: **Claude Haiku** (~$0.0002/call, стабильно), **DeepL Free API** (500k символов/мес, бесплатно), **ло** … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-TRANSLATION__open_) | TBD (Фаза 3.5) |
| D-DOCS-EXPOSURE | ✅ **Реализовано T_SEC.1.** Prod: `EXPOSE_DOCS=false` → `/docs`, `/redoc`, `/openapi.json` возвращают 404 (FastAPI фабрика конструируется с `docs_url=N` … | Swagger UI = живая карта API + модели данных = разведка для атакующего. Полное отключение проще auth-протокола … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-DOCS-EXPOSURE) | 2026-07-17 → 2026-07-18 |
| D-STATIC-FRONTEND | ✅ **Реализовано T_SEC.2 (2026-07-19).** Frontend больше не запускает `npm run dev` в prod: multi-stage Dockerfile (`node:22-alpine` builds → `nginx:1.` … | Vite dev-server = HMR websocket, source код в контейнере, `eval` для module bootstrap, StrictMode double-fire … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-STATIC-FRONTEND) | 2026-07-19 |
| D-BENTO-BREAKPOINT | ✅ **Реализовано T_UX.1.** Bento 2 колонки на desktop/tablet, 1 колонка на phone **даже landscape**. Хук `useBentoLayout()` в `frontend/src/hooks/` + `` … | iPhone Pro Max landscape = 932px попадает в `md:` (768+), Tailwind width-only даёт 2 колонки → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-BENTO-BREAKPOINT) | 2026-07-17 → 2026-07-18 |
| D-AGENTIC-INTERFACE | Два канала параллельно: (A) Nostr publish trip-events (kind 30402) в наш strfry | Nostr = долгосрочная децентрализованная позиция (совпадает с Nostr-slope). MCP = быстрый вход для AI-агентов сегодня. REST + OpenAPI избыточно → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-AGENTIC-INTERFACE) | 2026-07-17 |
| D-ROLES-ADD-UP | **Роли складываются, и роль наступает только после принятия.** `users.roles` — массив, права это объединение; `users.role` удалена. Назначение — предложение, не факт: до принятия колонка не меняется, поэтому слою прав не нужно понятие «ожидает». Каждое изменение колонки добавляет строку в `role_grants` в той же транзакции (исключение — User Zero, чья роль не выдана никем). | Одна строка делала каждое принятие молчаливым снятием предыдущей роли, а один и тот же человек штатно бывает и арбитром, и редактором правил — это разные работы, а не лестница. Предложение вместо назначения — потому что арбитр получает доступ к чужому сейфу: каждое такое чтение пишется в цепь, то есть запись о **применении** роли была иммутабельной, а записи о её **происхождении** не существовало вовсе. | 2026-08-29 |
| D-COMPLIANCE-STANCE | **Платформа не блокирует направления.** | Блокировка коридоров смещает Vimana в юр. позицию посредника-цензора → потеря децентрализованной идентичности … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-COMPLIANCE-STANCE) | 2026-07-18 |
| D-DVLT-PROTOCOL | **DealVault = Verifiable Vault Protocol, Фаза 3.6 (T3.7–T3.10).** | `ipfs`\ | `ots`); для proof-of-time целевой второй бэкенд → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-DVLT-PROTOCOL) | 2026-07-25 |
| D-SEAL-SEMANTICS | **Seal замораживает контент, не audit-trail (T3.7).** | Проблемы обнаруживаются после подтверждения получения (продуктовая реальность); в коде нет запрета спора по cl … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-SEAL-SEMANTICS) | 2026-07-25 |
| D-REVOCATION-IS-BEST-EFFORT | **Отзыв JWT — best-effort, а не гарантия (2026-07-29).** | Доступность важнее для потока обычных запросов: массовая блокировка входа наносит больше вреда, чем окно, в ко … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-REVOCATION-IS-BEST-EFFORT) | 2026-07-29 |
| D-EVIDENCE-DECAYS | **Все доказательства устаревают; свежее сильнее старого (2026-07-27).** | Доверие в физической логистике опирается на недавнее поведение, а не на факт когда-то пройденной проверки. Бин … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-EVIDENCE-DECAYS) | 2026-07-27 |
| D-RETIRED-IS-ARCHIVE | **Завершённая личность — исторический документ, а не мёртвый аккаунт (2026-07-27).** | Продукт строится на том, что информация не исчезает. Логическое завершение жизненного цикла → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-RETIRED-IS-ARCHIVE) | 2026-07-27 |
| D-KEY-IS-IDENTITY ⚠️ частично отменено `D-KEY-TIERS` (2026-08-01) | **⚠️ Читать вместе с `D-KEY-TIERS`.** | Философия проекта ближе к Nostr и Bitcoin: «ключ и есть личность» (решение владельца, 2026-07-26). Вариант «кл … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-KEY-IS-IDENTITY____частично_отменено__) | 2026-07-26 |
| D-KEY-TIERS | **Владение личностью — лестница из четырёх ступеней, а не булев флаг (решение владельца 2026-08-01).** | Прежняя модель была бинарной: либо служебный ключ целиком у платформы, либо полный self-custody без страховки, … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-KEY-TIERS) | 2026-08-01 |
| D-MAIL-VIA-MAILU | **Исходящая почта — только через собственный Mailu (2026-07-29, доведено до работы 2026-07-30).** | Решение владельца: не заводить в приложении прямых интеграций с сервисами пересылки. Один набор учётных данных … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-MAIL-VIA-MAILU) | 2026-07-29 |
| D-VAULT-NIP44 | **Конверты сейфа — NIP-44 v2, NIP-04 снят целиком (2026-08-02, `T_KEYS.1`).** | \ | ct` (аутентификация, которой не было), паддинг по расписанию` → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-VAULT-NIP44) | 2026-08-02 |
| D-SHAMIR-DEP | **`shamir-secret-sharing@0.0.3` остаётся, выбор наконец записан (2026-08-02, `T_KEYS.1`).** | Примитив, на котором держится доступ арбитра к сейфу, не может быть выбран «по умолчанию из npm» без записанной причины. При этом подмена его собственной реализацией → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-SHAMIR-DEP) | 2026-08-02 |
| D-RECIPIENT-ROLE | Recipient — приглашённый sender'ом участник чата с собственным **невидимым custodial keypair** (генерится при регистрации через `generate_keypair` + `` … | Разделять sender's nsec с recipient'ом ломает изоляцию: recipient получит доступ ко ВСЕМ прошлым чатам sender' … → [детали](archive/TECHSTATE_ARCHIVE_01.md#D-D-RECIPIENT-ROLE) | 2026-07-18 |

---

## 2a. D-CONTACT-CHANNELS — контакты, каналы и оповещения (решение владельца 2026-08-06)

| # | Решение | Причина | Дата |
|---|---|---|---|
| D-CHANNELS-EMAIL-AND-CHAT | **SMS и Telegram Gateway выведены из планов; телефон не станет идентификатором входа (решение владельца 2026-08-10).** Почты и Telegram достаточно; WhatsApp появится ботом (`T3.31`). Следствие, которое важнее самого решения: ни один оставшийся канал не доказывает **номер** — Telegram и WhatsApp доказывают аккаунт в мессенджере, а это другой факт (`D-CONTACT-CHANNELS` планировал обратное, и `T3.26` эту ошибку уже исправил). Значит «одно поле: почта или телефон» из Фазы 3.8 сужается до **«одно поле: почта»**, а `users.phone` остаётся тем, чем был — контактом в профиле. `core/channels.PHONE_CHANNELS` пуст, `available_for` для номера возвращает пустой список, экран входа это объясняет, а не молчит. **Попутно снимается опасность,** записанная при `T3.25`: правило «доказательство контроля забирает контакт» было опасно из-за переиздания номеров операторами — почту так не переиздают, а чат доказывается заново при каждой привязке. Инвайт по номеру остаётся возможен только как подсказка, не как удостоверение. | SMS для коридора ОАЭ ↔ США — самый дорогой и медленный канал из пяти: недели A2P-регистрации, юрлицо для 10DLC в США, Sender ID с местной лицензией в ОАЭ. Gateway существовал ровно как его дешёвая замена и без него незачем. Убрав оба, продукт теряет только то, чего у него и не было, и избавляется от целой задачи антифрода: качать бесплатный канал бессмысленно. | 2026-08-10 |
| D-CONTACT-CHANNELS | **Телефон возвращается в auth-путь как подтверждаемый контакт; форма входа сводится к одному полю.** Отменяет решение №1 Фазы 3.7 («телефон убирается из регистрации и логина»). Пять частей. **(1) Контакт ≠ личность.** Личность остаётся npub; телефон, почта и Telegram — контакты и способы входа, наравне с passkey и Nostr-подписью. Лестница `D-KEY-TIERS` не затронута: регистрация по телефону даёт ту же ступень 1, что и по почте, служебный keypair выдаётся как в T3.12. **(2) Модель — `user_contacts`, а не колонки на `users`.** `(channel, value, verified_at, is_login)` + `verification_challenges`; уникальность подтверждённого контакта — **частичным** индексом `WHERE verified_at IS NOT NULL`, иначе неподтверждённая заявка на чужой номер навсегда запирает настоящего владельца. `users.email`/`users.phone` остаются денормализованным основным контактом. Машина кодов T3.11 обобщается на все каналы, а не форкается под каждый. **(3) Вход код-first, без пароля.** Одно поле → выбор канала → код; `POST /auth/otp/request` отвечает 202 **всегда**, иначе публичная форма входа становится оракулом перебора аккаунтов. Вход по паролю для существующих аккаунтов сохраняется. **(4) Каналы за флагами, приоритет по достижимости.** Абстракция пишется целиком сразу; живость канала — переменная окружения. Первая итерация: email + Telegram deep-link + Telegram Gateway. SMS и WhatsApp реализуются кодом и тестами, но выключены до A2P-регистрации (10DLC в США, Sender ID в ОАЭ) и верификации бизнеса в Meta. Антифрод обязателен **до** включения любого платного канала. **(5) Оповещения — матрица «класс события × канал»**, JSONB + дефолты в коде; класс «безопасность» неотключаем; локализация на шесть локалей + `users.locale`. | Решение №1 убирало телефон как «лишний идентификатор» — верно для модели, где идентификатор претендует на роль личности, и неверно для модели, где он всего лишь канал. Форма из пяти полей с паролем при этом оставалась главным барьером входа, а половина каналов доставки уже была построена (T1.7) и простаивала: Telegram-бот со связыванием, WhatsApp через Twilio, роутинг по трём каналам. Приоритет каналов выбран по срокам, а не по привычке: для коридора ОАЭ ↔ США SMS — самый зарегулированный и медленный из пяти вариантов (недели и юрлицо), Telegram Gateway даёт то же «код на телефон» за депозит и день. Матрица оповещений и локализация добавлены в тот же этап, потому что чинить доставку в четыре канала, оставляя текст только на русском при UI на шести языках, значит доставлять то, что часть аудитории не прочтёт. | 2026-08-06 |

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
| **Правило не публикуется без цитаты, и калитка стоит на переходе статуса (T3.11.02, 2026-08-29).** Не в форме редактора: правило, живущее в UI, обходят CLI-импорт, фикстура и первая же массовая загрузка корпуса — то есть ровно тот путь, которым придут корпуса `T3.11.04` / `T3.11.05`. Публикация идёт только через ревью, иначе разделение `rules:edit` / `rules:publish` существует лишь на бумаге. Опубликованный и вытесненный набор **заморожены целиком**: исправление — новая версия. | `core/rule_status.py`, `api/rules_admin.py`, `models/rules.py` (`RuleStatusEvent`), `alembic/versions/0057_rule_status_events.py`, `tests/test_rules_admin.py`, `frontend/src/{api/rules.ts,pages/AdminRulesPage.tsx}` |
| **Вытеснение прежней версии требует явного `flush` до установки новой (T3.11.02).** Postgres проверяет партиальный уникальный индекс **на каждый statement**, а unit of work не обещает порядок UPDATE'ов: публикация второй версии падала бы на `uq_rule_sets_published` посреди собственной транзакции. | `core/rule_status.transition` |
| **«Сотрудник» — это «держит хоть какую-то роль» (T3.11.02).** Панель админки и раздел профиля спрашивали `isArbiter`; это был тот же вопрос, пока `arbiter` был единственной не-суперпользовательской ролью. `compliance_editor` сломал совпадение — редактор не увидел бы всю панель, включая свой единственный экран. | `frontend/src/lib/permissions.ts` (`isStaff`), `components/AdminPanelSection.tsx`, `pages/{ProfileLayout,ProfileAdminPage}.tsx` |
| **Роль — предложение, и она складывается с другими (T3.42, 2026-08-29).** `users.roles` — массив, права это объединение бандлов по всем ролям. Предложение не трогает колонку вовсе, поэтому слою прав не нужно понятие «ожидает принятия»: непринятое предложение невидимо для `perms_of`, потому что там нечего видеть. Пишет колонку только `core/roles.py`, добавляя строку журнала в той же транзакции; единственное исключение — `core/superuser.py`, где роль берётся из адреса в окружении, а не из чьего-то решения. | `models/role_grant.py`, `models/user.py`, `core/roles.py`, `core/permissions.py` (`roles_of`, `has_role`, `is_superuser`, `perms_of`), `core/superuser.py`, `api/roles.py`, `api/deps.py`, `api/admin.py`, `tasks/nostr_whitelist.py`, `tasks/notifications.py` (`send_role_offered`), `schemas/user.py`, `alembic/versions/0055_role_grants.py`, `0056_roles_add_up.py`, `emails/locales/*.json` (`role_offered` ×6), `tests/test_role_offers.py`, `frontend/src/{api/roles.ts,api/admin.ts,lib/permissions.ts,components/RoleOfferSection.tsx,pages/AdminRolesPage.tsx,pages/AdminUsersPage.tsx}` |
| **Миграция и тестовая БД: три случая, и только один из них — одна вещь (T3.42, T3.11.02).** `Base.metadata.create_all` создаёт недостающие **таблицы**, не меняет существующие и **не сеет данные**. Отсюда: **новая таблица** → только миграция · **изменение существующей** → миграция **и** `_ensure_*` в conftest · **посев из миграции** → миграция **и** сеятель в conftest. Пропуск второй половины во втором случае уронил 340 тестов и 682 ошибки из одной колонки; в третьем — один тест на отсутствующей юрисдикции `US`. | `tests/conftest.py` (`_ensure_user_roles_column`, `_seed_jurisdictions`, `_seed_default_categories`), `alembic/versions/0056_roles_add_up.py`, `0054_corridor_rules.py` |
| **Правило коридора вычисляется, а не читается (T3.11.01, 2026-08-29).** Юрисдикция — дерево (`US → US-NY → US-NY-NYC`), коридор — цепочка; условие документа хранится предикатом `{attr, op, value}` с одним уровнем `all` / `any` и разбирается интерпретатором на конечном списке операций — без `eval`. Валидация стоит на модели, а не на эндпоинте, и незаполненный атрибут даёт исключение, а не `false`. | `models/rules.py`, `core/rule_conditions.py`, `alembic/versions/0054_corridor_rules.py`, `models/marketplace.py` (категория `art`), `models/__init__.py`, `tests/test_rules_model.py` |
| **Одна опубликованная версия правила на тройку — партиальным индексом (T3.11.01).** `uq_rule_sets_published` покрывает только `status='published'`, поэтому старые версии остаются в таблице: две опубликованные — это два ответа на один вопрос, а без архива нельзя ответить, что правило говорило в марте. | `models/rules.py` (`RuleSet.__table_args__`), `alembic/versions/0054_corridor_rules.py` |
| **Enum-колонку нельзя засеять связанным параметром (T3.11.01).** asyncpg шлёт bind-параметр как `VARCHAR`, и Postgres не приводит его к enum сам — литерал привёл бы, параметр нет. Посев требует `CAST(:x AS <enumtype>)`. Касается любого будущего посева `direction` и `obtained_by`. | `alembic/versions/0054_corridor_rules.py` |
| **Один адрес — два экрана, и почему это не таб (T_UX.23, 2026-08-25).** | `pages/ModeHomePage.tsx`, `components/landing/{LandingShell,AudienceLanding,FlowStrip}.tsx`, `pages/{Carrier,Sender,Business}LandingPage.tsx`, `entry-ssr.tsx`, `scripts/prerender.mjs`, `nginx.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L001) |
| **Один способ правки на все параметры профиля (T_UX.22, 2026-08-23).** | `components/StandingNoteSection.tsx`, `components/DisplayPrefsSection.tsx`, `components/{Connections,Invites}Section.tsx`, `pages/Profile{Rules,Trust,History}Page.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L002) |
| **Стоячие заметки перевозчика: три текста, два поведения (T_UX.21, 2026-08-23).** | `models/user.py`, `schemas/user.py`, `alembic/versions/0053_*.py`, `tests/test_carrier_notes.py`, `components/StandingNoteSection.tsx`, `pages/ProfileRulesPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L003) |
| **Разделы профиля — вложенные маршруты, и это условие, а не стиль (T_UX.20, 2026-08-23).** | `pages/ProfileLayout.tsx`, `pages/Profile{,Activity,Trust,Prefs,Admin,Keys}Page.tsx`, `pages/NotificationsPage.tsx`, `components/{Connections,Invites,PublicPage}Section.tsx`, маршруты в `App.tsx`, ключи `profile.nav.*` в шести локалях → [детали](archive/TECHSTATE_ARCHIVE_01.md#L004) |
| **Живость и готовность — разные вопросы, и одним эндпоинтом их не задать (T_OPS.1, 2026-08-11).** | `backend/app/core/readiness.py`, `backend/app/main.py`, `docker-compose.dev.yml`, `nginx/default.conf`, `backend/tests/test_readiness.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L005) |
| **Telegram — единственный канал, который нельзя попросить первым (T3.27, 2026-08-11).** | `backend/app/api/telegram.py`, `backend/app/api/auth.py`, `backend/app/core/contact_verification.py`, `backend/app/models/contact.py`, `backend/alembic/versions/0048_telegram_login_exchange.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L006) |
| **Подключение Telegram из профиля стало способом входа (T3.27, 2026-08-11).** | `backend/app/api/telegram.py`, `backend/app/api/auth.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L007) |
| **Пустой ключ в настройках — это дефолт, а не «выключено» (T3.32, 2026-08-11).** | `backend/app/core/notification_prefs.py`, `backend/app/core/avatar_url.py`, `backend/alembic/versions/0047_notification_prefs.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L008) |
| **Список того, что показывать, живёт на сервере в одном экземпляре (T3.32, 2026-08-11).** | `backend/app/core/notification_prefs.py`, `frontend/src/components/NotificationMatrix.tsx`, `frontend/src/components/ChannelsSection.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L009) |
| **«Безопасность нельзя выключить» стало свойством класса (T3.32, 2026-08-11).** | `backend/app/core/notification_prefs.py`, `backend/app/tasks/notifications.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L010) |
| **`X-Forwarded-For` читался слева, то есть со стороны вызывающего (T_SEC.6, 2026-08-11).** | `backend/app/core/client_ip.py`, `backend/app/core/rate_limit.py`, `backend/tests/test_sign_ins.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L011) |
| **Отпечаток устройства должен быть грубее, чем данные, из которых он сделан (T_SEC.6, 2026-08-11).** | `backend/app/core/sign_ins.py`, `backend/app/models/sign_in.py`, `backend/app/tasks/cleanup.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L012) |
| **Одно событие — одно письмо (T_SEC.6, 2026-08-11).** | `backend/app/core/sign_ins.py`, `backend/app/api/auth.py`, `backend/app/api/passkey.py`, `backend/app/api/nostr_auth.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L013) |
| **Считать запросы и считать адресатов — разные вещи (T3.29, 2026-08-11).** | `backend/app/core/code_limits.py`, `backend/app/api/auth.py`, `backend/tests/test_code_limits.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L014) |
| **Контраст приглушённого текста — осознанное отступление от AA (T_TEST.8, 2026-08-03, решение владельца после отката).** | `frontend/e2e/axe-rules.json`, `PRD/DESIGNGUIDELINES.md` §6 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L015) |
| **Деплой мог быть верным и невидимым (2026-08-04).** | `frontend/nginx.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L016) |
| **Референс жил вне репозитория, поэтому пропажу было не с чем сверить (T_UX.7, восстановлено 2026-08-04, принято владельцем 2026-08-06).** | `frontend/src/pages/LandingPage.tsx`, `~/Downloads/Output/peerflew-offer/` (вне репо) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L017) |
| **Компонент, объявленный внутри компонента, монтируется заново на каждый ререндер (2026-08-04).** | `frontend/src/pages/LandingPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L018) |
| **Анимация не решает, что за элемент в документе (T_TEST.8, 2026-08-03).** | `frontend/src/components/Reveal.tsx`, `frontend/src/pages/LandingPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L019) |
| **Рукописный тип фронта — утверждение о чужом коде, и его не проверяет никто (T_TEST.12, 2026-08-23).** | `frontend/src/api/social.ts`, `frontend/src/pages/ProfilePage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L020) |
| **Одноразовый тестовый аккаунт не может найти баг накопленного состояния (T_TEST.12, 2026-08-23).** | `frontend/e2e/helpers.ts`, `frontend/e2e/README.md` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L021) |
| **Тесты быстрее людей, и это не повод двигать лимит (T_TEST.12, 2026-08-23).** | `nginx/default.conf`, `frontend/e2e/specs/passkey.spec.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L022) |
| **Тест, молчащий о статусе ответа, врёт о причине (T_TEST.12, 2026-08-23).** | `frontend/e2e/specs/passkey.spec.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L023) |
| **Незамоканный запрос в jsdom-тесте — шум, который учит не смотреть в stderr (T_TEST.12, 2026-08-23).** | `frontend/src/test/LoginPage.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L024) |
| **Round-trip слеп к симметричным мутациям (T_TEST.10, 2026-08-23).** | `backend/tests/test_threshold_encryption.py`, `backend/app/core/threshold.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L025) |
| **Эшелонированная защита делает внешнюю проверку ненаблюдаемой (T_TEST.10, 2026-08-23).** | `backend/app/core/threshold.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L026) |
| **Сьют полагался на то, что прогон и процесс — одно и то же (T_TEST.10, 2026-08-23).** | `backend/tests/conftest.py`, `test_platform_params.py`, `test_code_limits.py`, `test_telegram_login.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L027) |
| **mutmut не приписывает ни одному тесту код, исполняемый на импорте (T_TEST.10, 2026-08-23).** | `backend/scripts/verify_survivors.py`, `backend/setup.cfg` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L028) |
| **У правила `label` в axe есть запасная проверка на непустой `placeholder` (T_TEST.8, 2026-08-23).** | `frontend/src/pages/TripsPage.tsx`, `frontend/src/components/AirportSelect.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L029) |
| **Тесту нужна сессия, а не регистрация (T_TEST.8, 2026-08-23).** | `frontend/e2e/helpers.ts`, `backend/app/tasks/cleanup.py`, `backend/app/core/step_up.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L030) |
| **Проверка прав идёт раньше проверки формы (T_TEST.7 pt.2, 2026-08-03).** | `backend/app/api/threshold.py`, `backend/tests/test_idor_matrix.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L031) |
| **Таблица ожиданий сверяется с роутером, а не пишется руками (T_TEST.7 pt.2, 2026-08-03).** | `backend/tests/test_idor_matrix.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L032) |
| **Порог сканера живёт в коде, а не в конфиге сканера (T_TEST.7 pt.1, 2026-08-03).** | `.zap/baseline.sh`, `.zap/rules.tsv`, `backend/app/cli/zap_report.py`, `backend/tests/test_zap_report.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L033) |
| **Одна система токенов, потому что четырёх не бывает (T_UX.7, 2026-08-02).** | `frontend/tailwind.config.js`, `frontend/src/index.css`, 52 файла в `src/` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L034) |
| **Порядок наложения сведён частично и намеренно (T_UX.7 pt.3, 2026-08-02).** | `frontend/src/components/{AirportSelect,CategorySelect,CountryCodeSelect,LanguageSwitcher}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L035) |
| **Язык интерфейса не должен попадать в цепь (T_UX.7 pt.3, 2026-08-02).** | `frontend/src/pages/DealPage.tsx`, `backend/app/api/deals.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L036) |
| **Путь-параметр проверяется до базы, а не после (T_KEYS.1, 2026-08-02).** | `backend/app/api/trust.py`, `backend/tests/test_trust_graph.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L037) |
| **Дата обязательна на уровне типа, а не соглашения (T_TRUST.1, 2026-08-02).** | `frontend/src/components/VerificationBadgeChip.tsx`, `frontend/src/pages/IdentityPage.tsx`, `frontend/src/components/VerificationSection.tsx`, `frontend/src/test/VerificationBadgeChip.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L038) |
| **Затухание гасит бонус, а не человека (T_TRUST.1, 2026-08-02).** | `backend/app/core/freshness.py`, `backend/app/core/uba.py`, `backend/tests/test_freshness.py`, `backend/tests/test_uba.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L039) |
| **`expires_at` писался и не читался (T_TRUST.1, 2026-08-02).** | `backend/app/core/verification.py`, `backend/app/api/verification.py`, `backend/tests/test_verification.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L040) |
| **`refresh_allowed_pubkeys` запускать только в `celery-worker` (2026-08-01).** | `docker-compose.dev.yml` (volumes), `backend/app/tasks/nostr_whitelist.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L041) |
| **Первый живой тик якорения вскрыл три отдельные поломки (T3.20, 2026-08-01).** | `backend/app/core/nostr_publish.py`, `backend/app/tasks/nostr_whitelist.py`, `backend/app/core/chain_anchor.py`, `nostr/write_policy.py` (режим), `.env.example` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L042) |
| **Якорь стоит ровно столько, сколько сторонних релеев его держат (T3.20, 2026-08-01).** | `backend/app/api/{deals,trust}.py`, `frontend/src/components/ArchiveRecordCard.tsx`, `backend/tests/test_deal_chain.py`, `frontend/src/test/ArchiveRecordCard.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L043) |
| **Якорение включается тремя значениями, а не одним (T3.20, 2026-08-01).** | `.env.example`, `PRD/ENVIRONMENT.md` §5, `backend/app/core/chain_anchor.py`, `backend/app/worker.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L044) |
| **Окно архива: решение хранится, срок вычисляется (T3.19, 2026-08-01).** | `backend/app/core/permissions.py`, `backend/app/api/{keypair,auth,trust}.py`, `backend/app/models/user.py`, миграция `0039_archive_notice`, `backend/tests/test_identity_establish.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L045) |
| **Архивные агрегаты: только счётное, и всегда со знаменателем (T3.19, 2026-08-01).** | `backend/app/api/trust.py`, `frontend/src/components/ArchiveRecordCard.tsx`, `frontend/src/test/ArchiveRecordCard.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L046) |
| **Модалка один раз, баннер всегда (T3.19, 2026-08-01).** | `frontend/src/components/{ArchiveNotice,Layout}.tsx`, `frontend/src/pages/{ProfilePage,IdentityPage,DashboardPage}.tsx`, `backend/app/schemas/user.py`, `frontend/src/test/ArchiveNotice.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L047) |
| **Тестовая БД не под alembic (T3.19, 2026-08-01).** | `backend/tests/conftest.py`, `PRD/ENVIRONMENT.md` §8 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L048) |
| **Периметр контейнеров (T_SEC.3, 2026-08-01).** | `docker-compose.dev.yml`, `.env.example`, `PRD/ENVIRONMENT.md` §5.1 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L049) |
| **Восстановление живёт на экране входа (T3.16 pt.2, 2026-08-01).** | `frontend/src/components/SecuritySection.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/api/auth.ts`, `frontend/src/i18n/locales/*.json`, `backend/app/tasks/notifications.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L050) |
| **Recovery-код — это step-up-доказательство, а не вторая дверь (T3.16 pt.1, 2026-08-01).** | `backend/app/api/{auth,deps,passkey}.py`, `backend/app/core/security.py`, `backend/app/models/user.py`, миграция `0035_recovery_codes`, `nginx/default.conf`, `backend/tests/test_step_up.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L051) |
| **Работа, сделанная один раз, а не на каждый запрос (T_PERF.1 pt.3, 2026-08-01).** | `backend/app/core/{airports,metrics}.py`, `backend/tests/{test_airports,test_nostr_pt2}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L052) |
| **Rate-limit слоями: nginx грубо, slowapi точно (T_PERF.1 pt.3).** | `backend/app/core/rate_limit.py`, `nginx/default.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L053) |
| **Блокирующие вызовы в async-эндпоинтах (T_PERF.1 pt.2, 2026-08-01).** | `backend/app/core/{storage,nostr_publish}.py`, `backend/app/api/{avatar,dealvault,verification}.py`, `backend/tests/{test_presign_ttl,test_nostr_publish}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L054) |
| **Индексы под названные запросы (T_PERF.1 pt.1, 2026-08-01).** | `backend/alembic/versions/0034_hot_path_indexes.py`, `backend/app/models/{deal,marketplace,trust,verification}.py`, `backend/tests/conftest.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L055) |
| **Число запросов не должно зависеть от объёма данных (T_PERF.1 pt.1).** | `backend/app/core/{deal_chain,trust}.py`, `backend/tests/test_vault_completeness.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L056) |
| **Канонизировать на записи, а не у каждого читателя (T_PERF.1, 2026-08-01).** | `backend/app/api/trips.py`, `backend/tests/test_trips.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L057) |
| **Фильтры рейсов: точное сравнение вместо подстроки (T_PERF.1 pt.1).** | `backend/app/api/trips.py`, `backend/tests/test_trips.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L058) |
| **Самодостаточный файл и CSP тянут в разные стороны (T3.24, 2026-08-01).** | `nginx/default.conf`, `frontend/reader.html`, `frontend/vite.config.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L059) |
| **Relay не запускался из-за `nofiles` (найдено 2026-08-01).** | `nostr/strfry.conf`, `docker-compose.dev.yml` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L060) |
| **Тест, зависящий от календарной даты, обязан ограничивать себя своим прогоном (2026-08-01).** | `backend/tests/test_trips.py`, `PRD/ENVIRONMENT.md` §7 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L061) |
| **Гоча `.env`: дубль ключа перекрывает правку (T_SEC.3, 2026-08-01).** | `.env`, `backend/app/core/{step_up,redis_client}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L062) |
| **`--reload` снят с prod-uvicorn (T_SEC.3).** | `docker-compose.dev.yml`, `PRD/ENVIRONMENT.md` §9 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L063) |
| **`weasyprint` не импортировался ни разу (T_SEC.3).** | `backend/requirements.txt`, `PRD/ENVIRONMENT.md` §1 → [детали](archive/TECHSTATE_ARCHIVE_01.md#L064) |
| **Образ relay'я пиновать (T_SEC.3).** | `docker-compose.dev.yml`, `nginx/default.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L065) |
| **Аудит IDOR (2026-07-29)** | `backend/app/core/storage.py`, `backend/app/api/dealvault.py`, `backend/tests/test_presign_ttl.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L066) |
| Расстояние маршрута | `backend/app/core/airports.py`, `backend/tests/test_route_distance.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L067) |
| **Курсорная пагинация теряла строки с одинаковым `created_at`** | `backend/app/core/pagination.py`, `backend/tests/test_pagination.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L068) |
| **Смена почты — через `pending_email`, а не заменой на месте (T3.15).** | `backend/app/api/auth.py`, `backend/app/core/email_verification.py` (`target_email`), миграция `0032_pending_email`, `backend/tests/test_email_verification.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L069) |
| **Смена пароля завершает остальные сессии (T3.15).** | `backend/app/{api/auth,api/deps,core/security}.py`, миграция `0033_sessions_valid_from`, `backend/tests/test_step_up.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L070) |
| **Healthcheck фронтенда 11 дней врал** | `docker-compose.dev.yml`, `frontend/nginx.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L071) |
| **`mcp-server` перезапускался вечно** | `mcp-server/server.py`, `docker-compose.dev.yml` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L072) |
| Step-up re-auth (T3.15) | `backend/app/core/step_up.py`, `backend/app/api/{keypair,passkey}.py`, `backend/tests/test_step_up.py`, `frontend/src/components/{StepUpDialog,KeypairSection,PasskeySection}.tsx`, `frontend/src/api/stepUp.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L073) |
| Отправка почты (T3.11, доведено 2026-07-30) | `backend/app/core/email.py`, `backend/tests/test_notifications.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L074) |
| Passkeys / WebAuthn (T3.14) | `backend/app/{core/webauthn,api/passkey,models/webauthn}.py`, миграция `0031`, `frontend/src/components/Passkey*.tsx`, `frontend/e2e/specs/passkey.spec.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L075) |
| Тестирование WebAuthn без железа | `frontend/e2e/specs/passkey.spec.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L076) |
| Вход и регистрация по Nostr-ключу (T3.13) | `backend/app/api/nostr_auth.py`, `backend/app/core/identity_proof.py`, `backend/tests/test_nostr_auth.py`, `frontend/src/components/NostrAuthButton.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L077) |
| Личность vs служебный ключ (T3.12) | `backend/app/api/keypair.py`, `backend/app/core/{identity,identity_proof,challenge,service_keys}.py`, миграция `0029_identity`, `backend/tests/{test_identity_establish,test_service_keys,test_identity_proof_contract}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L078) |
| Перешифровка сейфов при переходе (T3.12) | `backend/app/core/{verification,identity,threshold}.py`, `backend/app/api/{keypair,dealvault,threshold}.py`, миграция `0030_container_key_envelope`, `frontend/src/lib/threshold.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L079) |
| Публикация рейсов под платформенным ключом (T3.12) | `backend/app/core/{nostr_publish,publish_filter}.py`, `backend/app/tasks/{nostr_publish,nostr_whitelist}.py`, `backend/tests/test_platform_publish.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L080) |
| Клиентская криптография личности (T3.12) | `frontend/src/lib/identity.ts`, `frontend/src/test/identity.test.ts`, `backend/tests/test_identity_proof_contract.py`, `frontend/e2e/specs/identity-establish.spec.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L081) |
| Email-подтверждение по коду (T3.11) | `backend/app/core/email_verification.py`, `backend/app/api/auth.py`, `backend/app/tasks/notifications.py`, миграция `0028_email_verification`, `backend/tests/test_email_verification.py` (20 тестов) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L082) |
| Auth только по email (T3.11) | `backend/app/{models,schemas}/user.py`, `backend/app/api/auth.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L083) |
| E2E-обход подтверждения | `backend/app/core/config.py`, `backend/app/main.py`, `backend/tests/conftest.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L084) |
| **Гоча тестовой схемы** | `backend/tests/conftest.py` (`_ensure_email_verification_columns` и соседи) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L085) |
| **Перешифровка при `establish` — inline и с самопроверкой (T3.12 pt.2b).** | `backend/app/api/keypair.py`, `backend/app/core/verification.py` (`rewrap_container_to_identity`, `verify_container_envelope`) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L086) |
| **КРИТИЧНО — Celery-воркер работал с пустым реестром задач.** | `backend/app/worker.py`, `backend/tests/test_worker.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L087) |
| **КРИТИЧНО — отсечённые nginx'ем запросы возвращали `200` с HTML.** | `nginx/default.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L088) |
| **Гоча прокси-заголовков** | `docker-compose.dev.yml` (команда uvicorn) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L089) |
| **Гоча slowapi + PEP 563** | `backend/app/api/{nostr_auth,auth,keypair}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L090) |
| **Шум финализаторов Redis — точечно подавлен в conftest.** | `backend/tests/conftest.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L091) |
| **Гоча asyncio-Redis** | `backend/app/core/redis_client.py`, `backend/app/core/{challenge,token_blacklist}.py`, `backend/tests/conftest.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L092) |
| **КРИТИЧНО — `SyncSessionLocal` не изолирован тестами.** | `backend/tests/conftest.py` (`sync_sessions`), `backend/app/core/database.py`, `backend/app/tasks/*` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L093) |
| **⚠️ Гипотеза, НЕ подтверждённая** | `backend/app/tasks/cleanup.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L094) |
| FastAPI app + /health + CORS + роутеры + lifespan (User Zero promote) | `backend/app/main.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L095) |
| Настройки (pydantic-settings) | `backend/app/core/config.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L096) |
| JWT (HS256, 30д), bcrypt | `backend/app/core/security.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L097) |
| get_current_user dependency + is_superuser helper | `backend/app/api/deps.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L098) |
| Auth API: register/login/me + normalize/case-insensitive/trim (T1.15) | `backend/app/api/auth.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L099) |
| Invite + Connection API + /me/invites (T1.14) | `backend/app/api/social.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L100) |
| Trips API (POST/GET + фильтры) | `backend/app/api/trips.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L101) |
| Deals API (match/accept/event/confirm) + DealEvent append-only + inquiry.deal_id linking (T1.22) | `backend/app/api/deals.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L102) |
| DealVault API (чат + upload) | `backend/app/api/dealvault.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L103) |
| Inquiry API (TripInquiry + InquiryMessage) | `backend/app/api/inquiries.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L104) |
| Admin API (Dispute + Vault access + Users) | `backend/app/api/admin.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L105) |
| RBAC: Permission enum + Role + perms_of() + require_perm() FastAPI dep (T1.24 pt.1) | `backend/app/core/permissions.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L106) |
| Waitlist API + Telegram admin notify (T1.18) | `backend/app/api/waitlist.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L107) |
| Waitlist: подтверждение заявителю + письмо владельцу, разовая рассылка по долгу (T_UX.8) | `backend/app/tasks/notifications.py` (`send_waitlist_emails`, `send_pending_waitlist_confirmations`, `_send_waitlist_pair`), `backend/app/models/waitlist.py` (`confirmation_sent_at`), `backend/alembic/versions/0042_waitlist_confirmation_sent.py`, `backend/app/api/waitlist.py`. Отметка ставится только по `True` из `send_email` — см. строку ниже → [детали](archive/TECHSTATE_ARCHIVE_01.md#L108) |
| Авторизация чтения waitlist через роль, а не общий секрет (T_UX.8 pt.2) | `backend/app/core/permissions.py` (`Permission.WAITLIST_READ`, superuser-секция), `backend/app/api/waitlist.py`. `ADMIN_API_TOKEN` и `require_admin_token` удалены — это было единственное место, где авторизация шла статическим заголовком мимо `get_current_user`/`require_perm` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L109) |
| Шаблоны писем: один layout, шесть локалей, восемь писем (T_UX.9) | `backend/app/emails/layout.html`, `backend/app/emails/locales/{en,ru,ua,pl,fr,es}.json`, `backend/app/core/email_templates.py` (`render` — единственная точка входа), `backend/app/tasks/notifications.py` (`_send`, `_notify_user`, `_catalogue_for`). Текстовая часть строится из каталога, а не вырезается из HTML. `en` — и fallback, и эталон: недостающий ключ разрешается в него, а не в исключение → [детали](archive/TECHSTATE_ARCHIVE_01.md#L110) |
| Почтовая консоль в админке, два контура (T_UX.9 pt.2) | `backend/app/core/email.py` (`Circuit`, `live()`, `preview()`), `backend/app/api/admin.py` (`/admin/email/{status,templates,test}`), `backend/app/core/permissions.py` (`EMAIL_MANAGE`), `frontend/src/pages/AdminEmailPage.tsx`, `frontend/src/api/admin.ts`. **Контуры — раздельные наборы переменных, а не флаг:** `PREVIEW_SMTP_*` против `SMTP_*`. Тестовая отправка прошита на `preview()`, параметра до боевого нет. Отрисовка шаблонов не читает ни один контур — страница работает при сломанной почте. Пароль не отдаётся наружу ни в каком виде → [детали](archive/TECHSTATE_ARCHIVE_01.md#L111) |
| Граница ошибок рендера (T_UX.11) | `frontend/src/components/ErrorBoundary.tsx` (+ `RouteErrorBoundary` по умолчанию), подключён в `frontend/src/App.tsx` **внутри router'а и снаружи `Suspense`** — упавший `lazy()`-чанк отклоняет приостановленный промис, и видит это только граница выше. Различает две причины: устаревший чанк после деплоя (свой текст, одна автоперезагрузка под замком `sessionStorage`) и настоящую ошибку (текст ошибки показан для отчёта). Ключ — `location.pathname`, иначе граница залипает и вся сессия выглядит сломанной. Тесты: `frontend/src/test/ErrorBoundary.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L112) |
| Предпросмотр писем без отправки (T_UX.9) | `backend/app/cli/email_preview.py` — рендер в `/tmp/vimana-email-preview/*.html` + `index.html`; `mailpit` в `docker-compose.dev.yml` под профилем `mail` (SMTP 1025, веб 8025, оба на loopback). Браузер показывает идеальный случай, Mailpit — то, что реально ушло по SMTP: заголовки, обе MIME-части, кодировки → [детали](archive/TECHSTATE_ARCHIVE_01.md#L113) |
| Язык получателя (T_UX.9) | `backend/app/models/user.py` (`locale`), `backend/app/models/waitlist.py` (`locale`, nullable), `backend/alembic/versions/0043_locale_columns.py`, `backend/app/schemas/user.py`, `frontend/src/pages/{RegisterPage,LandingPage}.tsx` шлют `i18n.language`. Дефолт `en`, не `ru`; существующие аккаунты не бэкфилились — язык по имени не угадывают → [детали](archive/TECHSTATE_ARCHIVE_01.md#L114) |
| Сканирование загрузок общим clamd (T3.8 pt.2) | `backend/app/core/file_validation.py` (`scan_for_malware`, `_clamav_target`), `CLAMAV_HOST` → `172.31.20.59:3310`. Сканер **общий с Mailu**: база сигнатур ~2 ГБ уже в памяти почтового хоста, второй копии на `t3.small` места нет. Включено и проверено вживую 2026-08-09 (EICAR → `infected`, обычный текст → `clean`). Протокол clamd без TLS и без аутентификации, поэтому путь приватный: проброс только на приватный IP + правило SG от группы Vimana + общий VPC. Проброс — в `docker-compose.override.yml` у Mailu, **обязан пережить апгрейд Mailu**, иначе сканирование прекратится молча → [детали](archive/TECHSTATE_ARCHIVE_01.md#L115) |
| Elastic IP у Vimana (инфраструктура) | Публичный адрес инстанса **закреплён** — на него указывает домен `vimana.dealvault.club`, и он не меняется при stop/start. Уточнено владельцем 2026-08-09; более ранняя запись в памяти агента об «IP меняется при рестарте» устарела. Практическое следствие: правила по адресу (security group, allowlist) на этот инстанс держатся, а приватный адрес `172.31.19.152` в дефолтном VPC стабилен тем более. Почтовый сервер Mailu — **в том же регионе и VPC**, что открывает приватный путь к его `clamd` без выхода в интернет (`T3.8 pt.2`) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L116) |
| Почему письмо о смене пароля существует (T_SEC.5 pt.3, 2026-08-10) | Владелец спросил, как пароль вообще может смениться чужими руками, если перебор закрыт лимитами. Перебор и правда закрыт — но смена почти никогда с него не начинается. Реальные пути: **повторное использование пароля** (одна верная попытка, лимит на неё не срабатывает), фишинг, скомпрометированный ящик, незалоченное устройство. Письмо решает исход ровно в одном из них — **атакующий знает пароль, но не владеет ящиком**: он меняет пароль и запирает владельца, письмо уходит на адрес, которого у него нет, и владелец возвращает аккаунт через «Забыли пароль?». Это же и самый вероятный сценарий из перечисленных. Обратная сторона названа честно: при скомпрометированном ящике письмо будет удалено и пользы не принесёт. Отсюда формулировка — не тревога, а средство: где нажать и почему оно сработает. **Пробел, который остаётся:** после T3.28 вход возможен кодом на почту без пароля вовсе, и такой вход не порождает никакого письма. Сигналом для этого случая было бы «вход с нового устройства» — его нет → [детали](archive/TECHSTATE_ARCHIVE_01.md#L117) |
| Абстракция канала доставки (T3.26/T3.27) | `backend/app/core/channels.py` (`available_for`, `deliver`, `proves`, `enabled`), `backend/app/api/auth.py` (`/contact/channels`, `/contact/request-code`, `/contact/confirm`), `backend/app/tasks/notifications.send_channel_code`. **Канал доказывает то, куда доставляет, а не то, что ввёл пользователь:** `telegram` свидетельствует о чате и никогда о номере, поэтому для телефона не предлагается; `telegram_gateway` доставляет через Telegram, но свидетельствует о номере — отображение живёт в `proves()` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L118) |
| Контакты и коды как таблицы (T3.25) | `backend/app/models/contact.py`, `backend/app/core/contacts.py`, `backend/app/core/contact_verification.py`, `backend/alembic/versions/0045_user_contacts.py`. Уникальность — **частичным** индексом только по подтверждённым строкам: полный `UNIQUE` позволил бы неподтверждённой заявкой на чужой номер запереть настоящего владельца навсегда. `users.email`/`phone` остаются денормализованным основным контактом. Телефон нормализуется в E.164 при записи в профиль (422 на непарсимое) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L119) |
| `send_email` сообщает, ушло ли письмо (T_UX.8) | `backend/app/core/email.py`. Возвращает `bool`: `False` при незаданном SMTP или пустом получателе, `True` только после `sendmail`. Заведено потому, что молчаливый выход неотличим от успеха на стороне вызывающего — именно так `✅ готово` держалось у Telegram и WhatsApp. Кто пишет в БД «отправлено», обязан читать результат → [детали](archive/TECHSTATE_ARCHIVE_01.md#L120) |
| Categories API (search + auto-create on match, T1.17) | `backend/app/api/categories.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L121) |
| Airports API (search + nearest + cascade country→city→airport, T1.10/T1.16) | `backend/app/api/airports.py`, `backend/app/core/airports.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L122) |
| Telegram bot webhook + linking через /start {token} (T1.7) | `backend/app/api/telegram.py`, `backend/app/core/telegram.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L123) |
| R2/S3 клиент + health check (T1.20) | `backend/app/core/storage.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L124) |
| AES-256-GCM at-rest шифрование (T1.21) | `backend/app/core/crypto.py`, `backend/app/models/deal.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L125) |
| Cursor pagination utils Page[T] (T1.19) | `backend/app/core/pagination.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L126) |
| slowapi rate-limit + X-Forwarded-For key (T1.19) | `backend/app/core/rate_limit.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L127) |
| Global exception handler + X-Request-ID middleware + jsonable_encoder fix (T1.19) | `backend/app/main.py`, `backend/app/core/logging_setup.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L128) |
| Email + WhatsApp (Twilio) notifications | `backend/app/core/email.py`, `backend/app/core/whatsapp.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L129) |
| Celery worker + beat (notifications, dispute checks) | `backend/app/worker.py`, `backend/app/tasks/notifications.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L130) |
| Superuser (User Zero) startup promotion | `backend/app/core/superuser.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L131) |
| Boarding pass PDF (WeasyPrint) | *(планируется, слот под T6.1)* → [детали](archive/TECHSTATE_ARCHIVE_01.md#L132) |
| Async SQLAlchemy engine + Base + get_db() | `backend/app/core/database.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L133) |
| Alembic async migrations (0001–0010) | `backend/alembic/env.py`, `backend/alembic/versions/` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L134) |
| Все доменные модели (13 таблиц) | `backend/app/models/` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L135) |
| Изолированная тестовая БД `vimana_test` + идемпотентные seed-фикстуры | `backend/tests/conftest.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L136) |
| 140 backend-тестов (auth, trips, deals, dealvault, dealvault_attachments, arbiter, dual_role, permissions, hardening_block3/4/5, encryption, inquiry, … | `backend/tests/` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L137) |
| Frontend SPA | `frontend/src/` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L138) |
| Frontend RBAC: hasPerm() + Permission enum mirror | `frontend/src/lib/permissions.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L139) |
| ModeSwitcher в Navbar (T1.24) + разный визуал Dashboard | `frontend/src/components/ModeSwitcher.tsx`, `pages/DashboardPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L140) |
| InquiryPanel | `frontend/src/components/InquiryPanel.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L141) |
| ImageLightbox | `frontend/src/components/ImageLightbox.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L142) |
| Admin pages (`/admin/disputes`, `/admin/users`, `/admin/deals/:id/vault`) | `frontend/src/pages/Admin*.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L143) |
| Landing + Waitlist public route (T1.18) | `frontend/src/pages/LandingPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L144) |
| Frontend smoke-тесты (7 кейсов через vitest) | `frontend/src/test/`, `frontend/src/**/*.test.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L145) |
| Docker compose dev с nginx dynamic DNS resolver + SSL termination | `docker-compose.dev.yml`, `nginx/default.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L146) |
| **Тестовые прогоны: повседневный vs полный (2026-07-25)** | `backend/{pytest.ini,tests/conftest.py,app/core/security.py}` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L147) |
| **Деплой frontend после T_SEC.2 (D-STATIC-FRONTEND)** | `frontend/Dockerfile`, `docker-compose.dev.yml` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L148) |
| Nginx custom 502/503/504 page с auto-refresh + healthcheck-based startup (2026-07-14) | `nginx/_error.html`, `nginx/default.conf`, `docker-compose.dev.yml` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L149) |
| Vite build vendor chunk splitting (react/i18n/phone) | `frontend/vite.config.ts`, `frontend/package.json` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L150) |
| Receiving Address helper (T1.26) + share-address message prefix `📍 SHARED ADDRESS` | `backend/app/core/address.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L151) |
| GeoNames city autocomplete (T1.26) | `backend/app/core/cities.py`, `backend/app/api/cities.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L152) |
| Nostr keypair core (T2.2) | `backend/app/core/keypair.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L153) |
| Signing helper (T2.2 pt.2) | `backend/app/core/signing.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L154) |
| Keypair endpoints (T2.2) | `backend/app/api/keypair.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L155) |
| NIP-07 signing (T2.2 pt.2) | `frontend/src/{lib/nostr,api/dealvault}.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L156) |
| Claim self-custody UI (T2.2 pt.2) | `frontend/src/components/KeypairSection.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L157) |
| Nostr event schema fields (T2.2 pt.2) | миграция `0015_nostr_event_format` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L158) |
| Threshold e2e schema (T2.3) | миграция `0016_threshold_encryption` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L159) |
| Threshold NIP-44 v2 core (T2.3, переведён в `T_KEYS.1` 2026-08-02) | `backend/app/core/threshold.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L160) |
| Threshold endpoints (T2.3) | `backend/app/api/threshold.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L161) |
| Threshold client crypto (T2.3) | `frontend/src/lib/threshold.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L162) |
| Threshold client API + UI (T2.3) | `frontend/src/{api/threshold,api/dealvault,pages/DealVaultPage}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L163) |
| Nostr publish bridge core (T3.5 pt.1) | `backend/app/core/nostr_publish.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L164) |
| Nostr publish Celery + endpoints (T3.5 pt.1) | `backend/app/tasks/nostr_publish.py`, `backend/app/api/trips.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L165) |
| strfry контейнер (T3.5 pt.1) | `docker-compose.dev.yml`, `nostr/strfry.conf` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L166) |
| Nostr NIP-07 self-custody publish (T3.5 pt.2) | `backend/app/api/nostr.py::publish_signed_event` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L167) |
| Nostr WoT-gate (T3.5 pt.2) | `nostr/write_policy.py`, `backend/app/tasks/nostr_whitelist.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L168) |
| Nostr metrics + republish (T3.5 pt.2) | `backend/app/{core/metrics,models/metrics,api/nostr}.py`, миграция `0019_publish_metrics` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L169) |
| УБА core (T3.1) | `backend/app/core/uba.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L170) |
| УБА Celery beat (T3.1) | `backend/app/tasks/uba.py`, `backend/app/worker.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L171) |
| УБА endpoints (T3.1) | `backend/app/api/uba.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L172) |
| УБА UI (T3.1) | `frontend/src/{api/uba,components/UBASection,pages/ProfilePage}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L173) |
| Playwright smoke suite (T_TEST.3) | `frontend/e2e/{package.json,playwright.config.ts,helpers.ts,specs/*}` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L174) |
| E2E user cleanup (T_TEST.3) | `backend/app/tasks/cleanup.py`, beat schedule в `worker.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L175) |
| Admin users viewer (T_TEST.3) | `backend/app/api/admin.py`, `frontend/src/{api/admin,pages/AdminUsersPage}.ts(x)` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L176) |
| Receiving addresses (T_UX.4 A) | миграция `0023_receiving_addresses`, `backend/app/{models/address,api/addresses,core/address}.py`, `backend/tests/test_addresses.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L177) |
| User avatars (T_UX.4 B) | миграция `0024_user_avatar`, `backend/app/{api/avatar,core/avatar_url}.py`, `backend/tests/test_avatar.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L178) |
| Chat address picker (T_UX.4 C) | `backend/app/api/{dealvault,inquiries}.py`, `frontend/src/components/ShareAddressModal.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L179) |
| Tamper-evident deal chain (T3.6) | миграция `0025_deal_event_chain`, `backend/app/{core/deal_chain,models/deal,api/{admin,deals,threshold}}.py`, `backend/tests/test_deal_chain.py` (39 тестов) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L180) |
| Chain anchors to Nostr (T3.6) | `backend/app/{core/chain_anchor,tasks/chain_anchor,models/deal,worker}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L181) |
| Vault content chain (T3.7) | миграция `0026_vault_completeness`, `backend/app/{core/deal_chain,api/{dealvault,deals,admin},models/deal}.py`, `backend/tests/test_vault_completeness.py` (9 тестов) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L182) |
| Seal / unseal (T3.7, D-SEAL-SEMANTICS) | `backend/app/{core/deal_chain,api/{admin,deals,dealvault}}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L183) |
| Identity ↔ Deal пересечение (T3.9, D-DVLT-PROTOCOL) | миграция `0027_identity_doc_kind`, `backend/app/{api/verification,core/deal_chain,models/deal}.py`, `backend/tests/test_identity_ref.py` (6 тестов) → [детали](archive/TECHSTATE_ARCHIVE_01.md#L184) |
| Контент-валидация загрузок (T3.8) | `backend/app/core/file_validation.py`, `backend/app/api/{dealvault,avatar,verification}.py`, `backend/tests/test_file_validation.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L185) |
| Статические лендинги DealVault (T3.10) ⛔ **сняты из выдачи 2026-08-02**, владелец выбрал средний вариант (новый лендинг `T_UX.7`); файлы перенесены в … | `frontend/public/dealvault-v5-corporate.html`, `frontend/public/dealvault-v5-rebel.html` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L186) |
| CTA на статических страницах (T3.10) ⛔ **снят вместе со страницами 2026-08-02** | `frontend/public/vimana-cta.js` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L187) |
| УБА chip на карточке рейса (T3.2) | `backend/app/{api/trips,schemas/marketplace}.py`, `frontend/src/components/UBAChip.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L188) |
| OperatorAccessGrant (T3.2) | `backend/app/{models/deal,api/admin}.py`, миграция `0017_operator_access_grants` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L189) |
| Verification container encryption (T2.1) | `backend/app/core/verification.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L190) |
| Verification endpoints (T2.1) | `backend/app/api/verification.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L191) |
| Polite-decline контракт (T2.1 pt.3) | `backend/app/schemas/verification.py`, `backend/tests/test_verification.py`, `frontend/src/{api/verification.ts,pages/DealPage.tsx,components/VerificationDeclineBanner.tsx}` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L192) |
| Verification frontend components | `frontend/src/components/Verification*.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L193) |
| Trust Graph core (T2.4) | `backend/app/core/trust.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L194) |
| Trust Graph endpoints (T2.4) | `backend/app/api/trust.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L195) |
| Trust Graph auto-populate | `backend/app/api/{deals,social}.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L196) |
| Trust Circles UI (T2.4) | `frontend/src/{api/trust,components/TrustCirclesSection}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L197) |
| KeypairSection frontend | `frontend/src/components/KeypairSection.tsx`, `frontend/src/lib/nostr.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L198) |
| AddressForm / AddressCard | `frontend/src/components/Address{Form,Card}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L199) |
| **Тип карточки — колонка, а не префикс в тексте (T3.34, 2026-08-16).** | `backend/app/models/deal.py`, `backend/app/core/cards.py`, `backend/app/api/dealvault.py`, `backend/alembic/versions/0050_vault_card_typing.py`, `frontend/src/components/AddressCard.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L200) |
| **Роль подтверждающего проверяется на сервере, скрытая кнопка — украшение (T3.34, 2026-08-16).** | `backend/app/api/dealvault.py`, `backend/tests/test_vault_cards.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L201) |
| **Четыре группы карточек — одна кодовая дорога (T3.36–T3.39, 2026-08-16).** | `backend/app/core/cards.py`, `backend/app/api/cards.py`, `backend/app/schemas/cards.py`, `frontend/src/lib/cardForms.ts`, `frontend/src/components/{CardActions,DealCard}.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L202) |
| **Доказательство проверяется при подтверждении, а не при создании (T3.37, 2026-08-16).** | `backend/app/api/cards.py`, `backend/app/api/dealvault.py`, `frontend/src/components/DealCard.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L203) |
| **Передача после вылета — это другой рейс (T3.37, 2026-08-16).** | `backend/app/api/cards.py`, `backend/tests/test_cards_flow.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L204) |
| **Сьют, который запускают руками, умирает молча (T_TEST.8, 2026-08-22).** | `frontend/e2e/helpers.ts`, `frontend/src/App.tsx`, `backend/app/api/auth.py`, `backend/app/core/config.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L205) |
| **Пустой `baseURL` делает забытый префикс не ошибкой, а неверным ответом (T_UX.14, 2026-08-16).** | `frontend/src/api/client.ts`, `frontend/src/test/apiPaths.test.ts` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L206) |
| **Тот же `tsc` проверяет тесты и собирает браузерный бандл (T_UX.14, 2026-08-16).** | `frontend/src/test/apiPaths.test.ts`, `frontend/tsconfig.json` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L207) |
| **Выдача рейсов — доска, а не история (T_UX.19, 2026-08-17).** | `backend/app/api/trips.py`, `frontend/src/components/PublishedTripsSection.tsx`, `frontend/src/pages/DashboardPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L208) |
| **Отменять, а не удалять (T_UX.19, 2026-08-17).** | `backend/app/api/trips.py`, `backend/tests/test_trip_cancel.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L209) |
| **Тест, верный только в момент написания, — это будущее падение (T3.34→T3.36, 2026-08-16).** | `backend/tests/test_vault_cards.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L210) |
| **Согласие на условия идёт через тот же `ack`, что и любая карточка (T3.35, 2026-08-16).** | `backend/app/api/terms.py`, `backend/app/api/dealvault.py`, `backend/tests/test_terms.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L211) |
| **Нормализация условий считается на сервере, потому что иначе две точки входа разойдутся (T3.35, 2026-08-16).** | `backend/app/core/terms.py`, `backend/app/core/airports.py`, `backend/app/models/marketplace.py`, `backend/alembic/versions/0051_trip_terms_fields.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L212) |
| **Ставки уехали из констант в версионируемую таблицу с областью действия (T3.40, 2026-08-16).** | `backend/app/models/platform_params.py`, `backend/app/core/params.py`, `backend/app/api/platform_params.py`, `backend/alembic/versions/0049_platform_parameters.py`, `frontend/src/pages/AdminParamsPage.tsx` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L213) |
| **`op.add_column` не создаёт enum-тип — это делает только `create_table` (T3.34, 2026-08-16, найдено прогоном на сервере).** | `backend/alembic/versions/0050_vault_card_typing.py` → [детали](archive/TECHSTATE_ARCHIVE_01.md#L214) |

---

## 3a. Хвосты: код без вызывающих (ревизия 2026-08-08)

> **Правило обращения с этим списком.** Ничего отсюда **не удалено намеренно** — решение владельца 2026-08-08. Список существует для одного: **перед тем как использовать любую из этих сущностей или строить рядом новое — проверить её**. Функция без вызывающих не проверена ни одним тестом и не исполнялась ни разу; она выглядит рабочей ровно настолько, насколько выглядел рабочим `logger` в `tasks/notifications.py`, которого не было вовсе. Прежде чем опереться на строку отсюда: прочитать её целиком, убедиться, что сигнатура сходится с сегодняшними моделями, и покрыть тестом — иначе это не переиспользование, а перенос непроверенного кода в рабочий путь.
>
> Обновлять список при каждой такой ревизии: добавлять найденное, вычёркивать то, что получило вызывающего или было удалено.

**Функции без единой ссылки во всём репозитории (проверено grep'ом по `*.py`, `*.ts`, `*.tsx`):**

| Файл | Функция | Что это и почему важно |
|---|---|---|
| `frontend/src/api/admin.ts` | `roleJournal` | **Оставлена намеренно (T3.42, 2026-08-29), вызывающего нет.** Эндпоинт `GET /api/admin/users/{id}/roles` реализован и покрыт тестами; экран, который бы его показывал, не заведён — `/admin/roles` отвечает на «что ждёт ответа», а не «что вообще происходило». Журнал одного аккаунта сегодня читается только запросом. Заводить экран без спроса владельца не стал; клиент оставлен, чтобы он появился одной страницей, а не страницей плюс археологией по API |
| `backend/app/core/rule_conditions.py` | `evaluate`, `required_attributes` | **Оставлены намеренно (T3.11.01, 2026-08-29), вызывающего пока нет.** Это объявленная поверхность для `T3.11.06` (сборка чеклиста) и `T3.11.12` (инструмент MCP) — обе следующие задачи той же фазы. В отличие от строк ниже, обе покрыты тестами: `tests/test_rules_model.py` исполняет и ветки отказа, и обе формы группировки. Если фаза остановится до `T3.11.06` — перепроверить сигнатуры перед использованием, как и всё в этом списке |
| `backend/app/core/trust.py` | `revoke_edge` | **Не остаток, а недоделанная фича.** У `TrustEdge` есть колонка `revoked_at` и готовая функция её проставить, но вызывающего нет — значит связь доверия сегодня **невозможно отозвать** ни одним эндпоинтом. Прежде чем строить что-либо на отзыве доверия, начинать отсюда |
| `backend/app/core/signing.py` | `build_vault_message_event_skeleton` | Мост для подписи сообщений сейфа через NIP-07 на стороне клиента: возвращает форму события, которую собрал бы клиент. Фронт этим не пользуется. Возможный задел для Фазы 6 (портативность) — но непроверенный |
| `backend/app/core/signing.py` | `_b64` | приватный хелпер |
| `backend/app/core/nostr_publish.py` | `_content` | вытеснен `_platform_content` при T3.12 |
| `backend/app/core/cities.py` | `get_by_id` | лукап города по geoname_id |
| `backend/app/core/airports.py` | `all_airports` | отдаёт весь датасет целиком |
| `backend/app/api/notices.py` | `_is_active_now` | приватный хелпер активности нотиса |

~~**Отсутствует целиком: `ErrorBoundary`.**~~ → **закрыто `T_UX.11`** (2026-08-09): `frontend/src/components/ErrorBoundary.tsx` обёрнут вокруг `<Routes>`, различает устаревший чанк и настоящую ошибку, сбрасывается по смене пути.

~~**`backend/app/core/contact_verification.py` — без вызывающих намеренно (T3.25).**~~ → **закрыто `T3.26`** (2026-08-09): вызывающие появились — `api/auth.request_contact_code` и `confirm_contact_code`. Исходная запись ниже оставлена как пример того, зачем этот список нужен.

~~**Прежняя запись (T3.25, 2026-08-09).**~~ Обобщённая машина кодов на все каналы: `issue`, `verify`, `generate_code`. Вызывающие приходят в `T3.26` (абстракция канала) и `T3.28` (вход одним полем) — до тех пор подтверждение почты работает на колонках T3.11. Оставлено так сознательно: один обмен хранилища в момент, когда он необходим, лучше двух живущих одновременно механизмов. **Если очередь изменится и `T3.26` не случится — это хвост, и его надо либо подключить, либо удалить.**

**Пере-использование значений контакта (T3.25, 2026-08-09).** Подтверждение забирает значение у того, кто подтвердил его раньше (`core/contacts._release_elsewhere`). Иначе частичный уникальный индекс превращает обычное событие — оператор переиздал номер, телефон сменил владельца — в вечную блокировку, всплывающую как 500 в вебхуке. Удаляется **контакт**, не доступ. **`T3.28` делает контакты идентификаторами входа, и тогда это требует пересмотра:** аккаунт не должен терять единственный способ входа оттого, что кому-то достался его старый номер.

**Модули фронта, которые никто не импортирует:**

| Файл | Что это |
|---|---|
| `frontend/src/lib/permissions.ts` | Зеркало бэкендовой модели прав с комментарием «keep in sync when adding perms». **Уже рассинхронизировано:** нет `NOSTR_REPUBLISH`, `NOTICES_MANAGE`, `IDENTITY_*`, `THRESHOLD_*`, `WAITLIST_READ`. Если понадобится проверка прав на фронте — сверить с `core/permissions.py` целиком, а не доверять этому файлу |
| `frontend/src/components/BentoGrid.tsx` | Упоминается только в комментарии внутри `ProfilePage.tsx` |

**Мёртвые i18n-ключи (в шести локалях каждый):** `profile.keypair.{claimTitle,claimWarn,claimHint,claimConfirm,importTitle,importError,exportTitle,exportHint,exportWarn,exportBadPassword,exportError,selfCustody,custodialHint,nip07Detected}` — остатки T3.12, где `claim`/`import`/`export` были удалены. Плюс `chat.shareAddress.notSet`, `trips.{departureDate,allowedCategories}`, `profile.{levelPhase,levelNote}`, `profile.identity.{declareLostConfirm,errorPassword}`.

**`auth.errorCredentials` осиротел (T3.28 pt.4, 2026-08-10).** Его показывал `handleSubmit`, который заменён на `handleOneDoor`: 401 больше не трактуется как «неверный пароль», потому что сервер отвечает так же на незарегистрированный адрес. Ключ оставлен в шести локалях, а не удалён — если появится экран, честно различающий эти случаи (его сегодня нет и по соображениям перебора не должно быть), текст пригодится. Если через фазу он всё ещё здесь — удалять.

**`auth.emailOrPhone` — отдельный случай, не удалять.** Ключ осиротел в T3.11, когда телефон убрали из auth. **ЭТАП 3.8 возвращает ровно это поле** (`T3.28`, форма из одного поля «почта или телефон»), поэтому ключ оставлен сознательно и должен быть дописан до полноценного набора при реализации T3.28 — там же проверить, что текст во всех шести локалях описывает новое поведение, а не старое.

**Мелочь конфигурации:** `CORS_ORIGINS` объявлен в `Settings` (`backend/app/core/config.py`), но читается через `os.getenv` в `main.py` — поле в `Settings` не используется. При следующей правке CORS привести к одному способу.

**Чего в проекте нет:** ни одного `TODO`/`FIXME`/`HACK` в `backend/app` и `frontend/src` (проверено 2026-08-08).

---

## 4. Ключевые модели данных / контракты (целевые)

**Фаза 1 (в prod)**
- `User(id, email?/phone?, password_hash?, display_name, can_carry, can_send, active_mode ∈ {sender, carrier}, role ∈ {user, arbiter, superuser}, nostr_pubkey?, business_activity_level?, notify_email/telegram/whatsapp, telegram_chat_id?, telegram_link_token?, whatsapp_number?, created_at)` — колонки `is_carrier`/`is_superuser`/`is_arbiter` удалены миграциями 0009/0010
- `InviteLink(id, creator_id→User, token, expires_at 14д, used_by→User?)`
- `Connection(id, user_id→User, connected_user_id→User, created_at)` — двусторонняя запись, UNIQUE(user_id, connected_user_id) из T1.19
- `Trip(id, carrier_id→User, origin, destination, depart_at, capacity, allowed_categories JSON, status)`
- `Order(id, sender_id→User, recipient_contact, origin, destination, category VARCHAR(50), declared_value, currency, description, deadline?, status, trip_id→Trip?)`
- `Deal(id, order_id→Order, trip_id→Trip, sender_id, carrier_id, recipient_id?, status ∈ {draft, matched, accepted, in_transit, delivered, confirmed, closed, disputed}, sealed_at?, created_at)` — `sealed_at` (T3.7): vault запечатан; NULL = открыт (снимается `dispute_opened`).
- `DealEvent(id, deal_id→Deal, event_type ∈ {…, dispute_opened, arbiter_opened, dispute_resolved, message_added, file_added, sealed, identity_ref}, payload JSON, actor_id, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, timestamp)` — **append-only**. T2.2 pt.2 добавил NIP-01 event поля (nullable); self-custody lenient — остаётся `None`. T3.7: content-события (`message_added` payload = {message_id, content_hash, msg_event_id, is_e2e}; `file_added` = {attachment_id, message_id, file_hash, kind, size_bytes, mime}).
- `DealVaultMessage(id, deal_id→Deal, sender_id?, text_ciphertext BYTEA, text_nonce BYTEA, is_system, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, is_e2e, wrapped_shares JSONB?, read_packages JSONB?, created_at)` — **иммутабельно**. Легаси T1.21 (`is_e2e=false`): server-encrypted at-rest, property `text` decrypt on access. T2.2 pt.2: NIP-01 event поля. **T2.3 (`is_e2e=true`)**: opaque blob — `text_ciphertext`/`text_nonce` = AES-256-GCM(session_key, plaintext) от клиента, `wrapped_shares` = 3 NIP-44-конверты (SSS 2-of-3), `read_packages` = 2 NIP-44-конверты с session_key для sender/carrier normal-read. Property `text` возвращает `None` для e2e — сервер не может расшифровать.
- `Attachment(id, message_id→DealVaultMessage, r2_key, file_hash SHA-256, ipfs_cid?, kind ∈ {handoff_photo, receipt_photo, doc, payment_receipt}, created_at)` — **иммутабельно**
- `Category(id, name_key UNIQUE, is_default, usage_count, created_at)` — T1.17
- `TripInquiry(id, trip_id→Trip, sender_id, carrier_id, deal_id?, created_at)` — UNIQUE(trip_id, sender_id), T1.22
- `InquiryMessage(id, inquiry_id→TripInquiry, sender_id, text_ciphertext, text_nonce, created_at)` — at-rest шифрование, T1.22
- `Dispute(id, deal_id→Deal UNIQUE, opened_by, arbiter_id?, reason, status ∈ {open, claimed, resolved}, verdict?, created_at, resolved_at?)` — T1.23
- `OperatorAccessGrant(id, dispute_id→Dispute, granted_by→User, granted_at, revoked_at?)` — T3.2, UNIQUE(dispute_id, granted_by). Auto-create от opener при open_dispute; explicit grant для второй стороны; ≥1 active grant требуется для arbiter DealVault read.
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

**Фаза 3.11**
- `RuleStatusEvent(id, rule_set_id→RuleSet, from_status?, to_status, actor_id?, note, created_at)` — T3.11.02, append-only. `from_status` пуст у строки создания: статуса до неё не было. Индекс `(rule_set_id, created_at)`.
- `User.roles: list[str]` — **`ARRAY(String(32))`, пустой у обычного участника** (не `["user"]`: «участник» — это отсутствие ролей). Заменяет `User.role`, которой больше нет. Пишется только `core/roles.py` и `core/superuser.py` — T3.42, миграция `0056`.
- `RoleGrant(id, subject_id→User, role, event ∈ {offered, accepted, declined, revoked}, actor_id?, reason, created_at)` — T3.42, append-only. Состояние пары `(subject, role)` = её последняя строка. `actor_id` пуст у `accepted`/`declined` (актор — сам субъект). Индекс `(subject_id, role, created_at)`.
- `Role.COMPLIANCE_EDITOR` + права `rules:edit` / `rules:publish`; `arbiter:assign` переименовано в `role:offer` — T3.42.

**Фаза 3.5**
- `Trip.nostr_event_id?` (unique index), `Trip.nostr_published_at?` — T3.5
- `SanctionsList` уже введена в Фазе 2

**Фаза 4**
- `KycRecord(id, user_id, provider, external_id, status ∈ {pending, verified, rejected, expired}, verified_at, expires_at, level)` — T4.1
- `ComplianceAck(id, user_id, doc_version, category, acknowledged_at)` — T4.1
- `RouteNote(id, origin_iso, destination_iso, status ∈ {standard, attention, complex, restricted}, severity ∈ {info, warning, alert}, headline_i18n_key, body_i18n_key, active_from, active_until?, created_by)` — T_UX.2, informational только (не блокирует match/publish). Wildcards `*` в origin/destination поддерживаются.
- `PlatformNotice(id, key, severity, target_surface ∈ {footer, trip_card, deal_page, all}, active_from, active_until?, created_by)` — T_UX.2, глобальные плашки платформы, редактируются superuser'ом.
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
