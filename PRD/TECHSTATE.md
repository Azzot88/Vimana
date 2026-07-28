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
| Peer Identity Verification (P2P KYC) | 2 | ✅ MVP (T2.1: backend + frontend, custodial only. OCR/OFAC — stub, self-custody 422 до T2.3. pt.3 закрыт: `VerificationRequestOut` типизирован enum'ами + list-endpoint покрыт тестами) |
| Trust Graph (Web-of-Trust) | 2 | ✅ MVP (T2.4: TrustEdge + auto dealt_with/invited + BFS endpoints + denormalized counts + UI. Follow-up: Redis-кэш, UserBadge на TripCard) |
| Keypair + Nostr-совместимость (D10: A+D) | 2 | ✅ MVP (pt.1 custodial + UI; pt.2 NIP-01 event format + NIP-07 signing + Claim self-custody end-to-end) |
| Threshold 2-of-3 encryption (замена at-rest из T1.21) | 2 | ✅ MVP (T2.3: NIP-04 wrap of Shamir shares + read_packages для нормального read; `/arbiter-reveal` с audit-event; DealVault e2e-путь, Inquiry — follow-up) |
| Уровень Бизнес-Активности (УБА) | 3 | ✅ MVP (T3.1: формула F/Q/V/D/Vrf в `core.uba`, Celery beat hourly recompute, `/me/uba` + `/users/{id}/uba` endpoints, `UBASection` в профиле. D=0 до T5.x Collateral) |
| Оператор-арбитр и споры + Access Grants | 3 | ✅ MVP (T3.2: OperatorAccessGrant + auto-create от opener + explicit grant/revoke + vault-read gate на active grant. UBA-chip на TripCard. Роль/консоль/Dispute — из T1.23/T1.24. Escrow → T5.x) |
| Recipient role в DealVault | 3 | ✅ MVP (T3.3: DealParticipant модель + invite/join/revoke/list endpoints + невидимый custodial keypair per recipient + server-mediated decrypt-for-me для custodial callers. Threshold 2-of-3 не тронут — recipient орто) |
| Vimana Nostr Relay (strfry) + Federation | 3.5 | ✅ MVP (T3.5 pt.1 + pt.2: publish bridge + toggle + strfry контейнер + badge + NIP-07 self-custody publish + WoT-gate через writePolicy plugin + metrics endpoint + superuser republish. Follow-up: D-TRANSLATION мультиязычный перевод описаний — pt.3) |
| DealVault Protocol: полнота цепи (msgs/files/seal) + контент-валидация + identity-пересечение | 3.6 | ✅ MVP: T3.7 (цепь messages/files/seal) + T3.8 (контент-валидация) + T3.9 (identity-пересечение: копия в сделке + identity_ref, тройной doc_hash). Остался только T3.10 (преза + лендинг, v1 → сравнение с альтернативой) |
| DealVault: презентация + лендинг | 3.6 | 🟨 в работе (T3.10: выставлены `frontend/public/dealvault-v5-{corporate,rebel}.html` + `vimana-cta.js`. Открыты: преза, выбор версии, **расхождение по тону** — v5 заявляет tamper-proof вместо tamper-evident, см. TASKS T3.10) |
| Идентичность и вход (email-подтверждение, npub, Passkeys, step-up, recovery) | 3.7 | 🟨 в работе. **T3.11 ✅ MVP** (email-only регистрация + код подтверждения; телефон убран из auth, `password_hash` nullable, миграция `0028`). **T3.12 ✅ MVP** (служебный ключ ≠ личность; `establish` с доказательством владения, `declare-lost`, снятие `claim`/`import`/`export`, перешифровка обоих сейфов с самопроверкой, публикация под платформенным ключом с фильтром; миграции `0029`/`0030`). **T3.13 ✅ MVP** (вход и регистрация по Nostr-ключу; три purpose вместо URL-привязки NIP-98; аккаунт без пароля и без email). T3.14–T3.17 ⬜. Открыто из T3.12: NOT NULL на `nostr_pubkey` отдельной миграцией; правило «длинных хопов» ждёт структурных origin/destination; `declare-lost` для беспарольных аккаунтов ждёт step-up из T3.15. |
| Regulatory KYC/AML (только KYC-провайдер + person-level SDN) | 4 | ⬜ не начато (T4.1). Corridor-периметр не блокируем — информируем через RouteNote (T_UX.2, D-COMPLIANCE-STANCE). |
| Route notes + platform disclaimers | 3 | ✅ MVP (T_UX.2: backend + admin CRUD + PlatformNoticeBanner + UI slots + DealVault pinned system-msg на match + direct headline/body text вместо i18n_key). Multi-lang translations — pt.5 (когда появится curation workflow). |
| Multiple receiving addresses + Edit profile + avatars + landing on logo | 3 | ✅ MVP (T_UX.4: `ReceivingAddress` таблица c partial-unique index на default + CRUD + share-address address_id + `users.avatar_key` + POST/DELETE /me/avatar через тот же R2 бакет + `<AddressesSection>` inline edit + `<EditProfileModal>` + `<ShareAddressModal>` picker в чатах + two-col Bento на /profile + Navbar лого → landing). Legacy `User.receiving_*` колонки остаются fallback'ом на contract-фазу; удаление отдельной миграцией. |
| Agentic MCP server | 3 | 🟨 pt.1 skeleton (T_AGENT.1: 2 tools list_trips + get_trip_details, docker-compose profile mcp). Auth + rate-limit + search_trips + metrics — pt.2. |
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
| D-NOSTR-FEDERATION | **Стартовый whitelist** friendly relays: `wss://relay.damus.io`, `wss://nostr.wine`, `wss://relay.nostr.band`. Env `NOSTR_FRIENDLY_RELAYS=<comma-separated>`. Ревизия каждые 3–6 месяцев по популярности и uptime. Пороги для замены: >10% publish failures в течение недели, или полная недоступность >48 ч. | Три relay покрывают три разных клиентских экосистемы (damus/iOS, coracle/web, nostr.band/search-first). Достаточно redundancy без избытка network chatter. | 2026-07-18 |
| D-TRANSLATION (open) | Провайдер on-the-fly перевода Nostr-описаний для мультиязычного UI | Варианты: **Claude Haiku** (~$0.0002/call, стабильно), **DeepL Free API** (500k символов/мес, бесплатно), **локальный NLLB** (0 стоимость, но 3+ GB модель). Кэш в Redis TTL 30 дней по `(event_id, target_lang)`. Уточнить при подходе к T3.5 | TBD (Фаза 3.5) |
| D-DOCS-EXPOSURE | ✅ **Реализовано T_SEC.1.** Prod: `EXPOSE_DOCS=false` → `/docs`, `/redoc`, `/openapi.json` возвращают 404 (FastAPI фабрика конструируется с `docs_url=None` при флаге false). Nginx security headers: HSTS 1y, X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy минимальный, CSP baseline. Probe-deny: `.env`, `.git`, `.svn`, `.php/aspx/jsp/cgi`, `wp-admin/wp-login/wp-content/xmlrpc.php`, `.ht*` → 404. Rate-limit zone `auth_zone` (10r/min IP) на /auth/login+/auth/register с burst=5 nodelay. `server_tokens off`. | Swagger UI = живая карта API + модели данных = разведка для атакующего. Полное отключение проще auth-протокола за ним, dev не страдает. | 2026-07-17 → 2026-07-18 |
| D-STATIC-FRONTEND | ✅ **Реализовано T_SEC.2 (2026-07-19).** Frontend больше не запускает `npm run dev` в prod: multi-stage Dockerfile (`node:22-alpine` builds → `nginx:1.27-alpine` serves `dist/`). Внутренний nginx контейнера обрабатывает SPA fallback + immutable cache. CSP `script-src 'self'` (без `unsafe-inline`/`unsafe-eval`). Побочный эффект: React StrictMode double-effect в prod физически невозможен, backfilled invite idempotency остаётся как defense-in-depth. | Vite dev-server = HMR websocket, source код в контейнере, `eval` для module bootstrap, StrictMode double-fire ловил реальные race conditions в проде. Static bundle решает всё разом + сжимает CSP. | 2026-07-19 |
| D-BENTO-BREAKPOINT | ✅ **Реализовано T_UX.1.** Bento 2 колонки на desktop/tablet, 1 колонка на phone **даже landscape**. Хук `useBentoLayout()` в `frontend/src/hooks/` + `<BentoGrid>` контейнер в `components/`. Правила: phone = `width < 768 OR (height < 500 AND any-pointer: coarse)`, tablet = 768-1023, desktop = 1024+. 5 vitest тестов, iPhone 14 Pro Max landscape (932×430 coarse) → phone. Миграция существующих мест — follow-up. | iPhone Pro Max landscape = 932px попадает в `md:` (768+), Tailwind width-only даёт 2 колонки — противоречит UX-намерению (пользователь развернул для большего размера, не для больше колонок). | 2026-07-17 → 2026-07-18 |
| D-AGENTIC-INTERFACE | Два канала параллельно: (A) Nostr publish trip-events (kind 30402) в наш strfry — читается любым Nostr-агентом. (B) MCP-server (`mcp` SDK от Anthropic) как отдельный docker-контейнер — публикует tools `list_trips`, `get_trip_details`, `search_trips` для Claude Desktop / Claude Code / других MCP-совместимых клиентов. | Nostr = долгосрочная децентрализованная позиция (совпадает с Nostr-slope). MCP = быстрый вход для AI-агентов сегодня. REST + OpenAPI избыточно — дублирует и добавляет attack surface. Реализация — T_AGENT.1. | 2026-07-17 |
| D-COMPLIANCE-STANCE | **Платформа не блокирует направления.** Corridor-периметр как жёсткий фильтр (idea из ранних версий T4.1) удалён. Вместо: `RouteNote` показывает статус коридора (standard / attention / complex / restricted) с i18n-текстом; sender/carrier сами решают. `PlatformNotice` — глобальные плашки. Person-level sanctions (OFAC/EU SDN) остаются в T2.1 (peer verification container) и T4.1 (KYC-провайдер) — это про людей в санкционных списках, не про направления. ToS явно дисклеймит: «Vimana = инфраструктура, не курьер, не цензор; пользователь несёт риск за свой выбор». Реализация — cross-cutting `T_UX.2`. | Блокировка коридоров смещает Vimana в юр. позицию посредника-цензора → потеря децентрализованной идентичности + противоречит Nostr-slope. Информирование сохраняет свободу пользователя + разгружает платформу от роли арбитра geopolitics. Legal exposure ограничивается ясным ToS + аудит-логом RouteNote impressions. | 2026-07-18 |
| D-DVLT-PROTOCOL | **DealVault = Verifiable Vault Protocol, Фаза 3.6 (T3.7–T3.10).** (1) Цепь T3.6 расширяется на сообщения/файлы/identity-события через payload обычных `DealEvent` — preimage-формат не меняется. (2) Хешируются **хранимые байты** (`sha256(ciphertext+nonce)`) — верификация без расшифровки, E2E сохраняется; следствие: ротация `MESSAGE_ENCRYPTION_KEY` только envelope-схемой (перешифровка ключа, не данных). (3) Закрытие сделки запечатывает vault (`sealed` событие + запрет append). (4) Identity-пересечение: канонический документ в `IdentityContainer`, **полная копия в сделке** (Attachment `identity_doc`) + `identity_ref` в цепи по общему `doc_hash` — решение владельца, vault самодостаточен. (5) Публикация якорей остаётся выключенной; расширяемость — колонка `deal_chain_anchors.backend` (`nostr`\|`ipfs`\|`ots`); для proof-of-time целевой второй бэкенд — OpenTimestamps (IPFS = content-addressing, не timestamp). (6) Query API, .dvlt+Reader — отложены осознанно. | Концепция «DealVault Concept v0.1» (владелец, 2026-07-25): vault = переносимый иммутабельный криптографически проверяемый артефакт; полнота истории — обязательна, публикация — расширение. Копия документа в сделке выбрана владельцем вместо hash-only-референса ради самодостаточности vault'а. | 2026-07-25 |
| D-SEAL-SEMANTICS | **Seal замораживает контент, не audit-trail (T3.7).** `Deal.sealed_at` ставится при `confirm` (после события `sealed`); guard в `append_deal_event` (под advisory lock) отклоняет всё, кроме: (1) `dispute_opened` — спор после `closed` возможен и **распечатывает** vault (`sealed_at=NULL`); закрывающий вердикт арбитра запечатывает снова (второе `sealed`-событие); (2) `arbiter_opened` — audit-события проходят через seal, иначе пришлось бы либо терять аудит доступа арбитра к sealed vault, либо блокировать чтение. System-message в чат при чтении sealed vault не пишется (контент заморожен). Цепь фиксирует и seal, и unseal — исключения ничего не скрывают. | Проблемы обнаруживаются после подтверждения получения (продуктовая реальность); в коде нет запрета спора по closed-сделке. Мгновенный неснимаемый seal сломал бы арбитраж — evidence нельзя было бы приложить. | 2026-07-25 |
| D-EVIDENCE-DECAYS | **Все доказательства устаревают; свежее сильнее старого (2026-07-27).** Верификация вчера — сильная, месяц назад — нормальная, пять лет — под вопросом. Следствия: (1) ни одно доказательство не показывается без своей даты — голый бейдж «проверен» утверждает больше, чем факт; (2) возраст входит множителем в УБА рядом с `V_verify_factor`; (3) рёбра Trust Graph взвешиваются по свежести в BFS; (4) шкала затухания фиксируется в PRD, а не расползается по коду. Данные в основном уже есть (`VerificationBadge.verified_at`/`expires_at`, `TrustEdge.created_at`, `DealEvent.timestamp`) — не хватало не полей, а их использования. Реализация — `T_TRUST.1`. | Доверие в физической логистике опирается на недавнее поведение, а не на факт когда-то пройденной проверки. Бинарное «проверен/не проверен» позволяет годами предъявлять давно неактуальное доказательство как текущее. | 2026-07-27 |
| D-RETIRED-IS-ARCHIVE | **Завершённая личность — исторический документ, а не мёртвый аккаунт (2026-07-27).** Утрата ключа отнимает способность действовать и не трогает достоверность прошлых действий — у нас эти две вещи впервые независимы. Отсюда: аккаунт не удаляется, а меняет жанр; UI переключается в режим чтения архива, а не деградирует в урезанный профиль; поручительства завершённой личности **остаются в силе** (подпись была сделана живым ключом и проверяется до сих пор). Слово **Archive**, не Cemetery. Окно 15 дней от `key_lost_at`: **бездействие → экспонат становится видимым**, выбор «Нет» закрывает страницу навсегда. Асимметрия намеренная — ошибочное «Нет» ведёт к приватности, ошибочное бездействие к публичности, но с окном на исправление. **Ничего не удаляется ни в одном случае**: закрывается витрина (страница, `display_name`, агрегаты), остаются цепь, подписи и события сделок — они наполовину принадлежат контрагенту (ENVIRONMENT §8.2). Слово «кремация» в UI не использовать: обещает уничтожение, которого нет. **Архив вплетён в сеть, а не стоит отдельным зданием:** к завершённой личности приходят прогулкой по рёбрам `peer_verified` от живых участников; `dealt_with` и `invited` публично не обходятся (клиентская база и социальный граф). Скрытая личность остаётся в графе обезличенным узлом, и её поручительства продолжают считаться — скрыть можно себя, но не свой вклад в чужую репутацию. Экспонаты архива **несвязанные** — преемственности личностей нет по решению №4, «династии» были бы его отменой. Реализация — `T3.18`/`T3.19`. | Продукт строится на том, что информация не исчезает. Логическое завершение жизненного цикла — не смерть записи, а переход из режима «участник сети» в режим «историческая запись». Это продолжение философии DealVault, а не дополнительная функция. | 2026-07-27 |
| D-KEY-IS-IDENTITY | **Служебный ключ ≠ личность; личность создаётся при переходе и всегда новым ключом (Фаза 3.7, T3.11–T3.17).** (1) Механика T2.2 сохраняется: keypair выдаётся при регистрации, платформа хранит nsec, им шифруются контейнеры и подписываются записи — но это **служебный ключ сейфа**, а не личность. Пользователю он не показывается, наружу не публикуется. Отдельной колонки не нужно: `key_self_custody = false` означает «служебный», `true` — «личность». (2) `POST /me/keypair/claim` **удаляется**: он повышал служебный ключ до личности удалением серверной копии nsec, но ключ, приватная часть которого всю жизнь лежала у платформы, суверенным быть не может — отсутствие копии недоказуемо. Переход (`POST /me/identity/establish`) всегда даёт **новый** ключ: сгенерированный в браузере (`@noble/curves`, сервер nsec не видит) либо принесённый из NIP-07. Для сервера ветки неразличимы — он требует только доказательство владения заявленным npub. `import` и `export` тоже удаляются: первый принимал голый npub без проверок (присвоение чужой личности), второй выдавал служебный ключ, который пользователю не принадлежит. (3) Рейсы до перехода публикуются **только** под отдельным `PLATFORM_PUBLISH_NSEC` и **только отобранные фильтром «интересных»** (редкие направления, длинные хопы). Служебным ключом не публикуем: событие в сторонних relay'ях живёт вечно, а служебный npub при переходе уничтожается — остались бы события ничьей личности. (4) Смена и потеря ключа = **новая личность**: история, УБА и trust не переезжают; `key_lost_at` — терминальное состояние (read-only, публичный чип, обратного перехода нет). Recovery-код возвращает доступ, но никогда ключ. (5) Перешифровка сейфов при переходе — **envelope-схемой** (session-ключи переупаковываются NIP-04 на новый npub, байты контента не меняются) → цепь T3.6 и `verify_content` целы; `IdentityContainer` перешифровывается целиком, его `doc_hash` считается по plaintext и переживает смену шифра. (6) Сущность DID **не вводится** — `nostr_pubkey` и есть идентификатор. | Философия проекта ближе к Nostr и Bitcoin: «ключ и есть личность» (решение владельца, 2026-07-26). Вариант «ключа нет до перехода» отвергнут как дорогой: он требовал переписать шифрование `IdentityContainer`, ветку безключевого участника в `dealvault.py`, поведение threshold и весь механизм `D-RECIPIENT-ROLE` — риск на работающем коде ради семантики, которую даёт переименование. Отказ от «неизменной личности при смене ключа» принят сознательно как цена self-sovereign identity: восстановление личности силами платформы означало бы, что источник идентичности — платформа, а не пользователь. | 2026-07-26 |
| D-RECIPIENT-ROLE | Recipient — приглашённый sender'ом участник чата с собственным **невидимым custodial keypair** (генерится при регистрации через `generate_keypair` + `encrypt_nsec`, UI не показывает). Threshold 2-of-3 {sender, carrier, arbiter} **не расширяется**; расширяется только `read_packages` map — `recipient_<uuid>` NIP-04 envelope с session_key. Server-mediated decrypt endpoint (`/decrypt-for-me`) даёт plaintext recipient'у через custodial nsec — сервер видит plaintext на мс, не хранит. Sender/carrier с self-custody продолжают расшифровывать client-side через NIP-07 (для них E2E полный). | Разделять sender's nsec с recipient'ом ломает изоляцию: recipient получит доступ ко ВСЕМ прошлым чатам sender'а + impersonation в подписях + невозможность revoke. Отдельный custodial keypair — чистая изоляция per-deal, revocable через `DealParticipant.revoked_at`. Server-mediated read — честный документированный компромисс для сути роли (recipient = "читатель по приглашению", уже доверяет платформе). | 2026-07-18 |

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
| Расстояние маршрута — `route_distance_km(origin, destination)` в `core/airports.py`: IATA → координаты → haversine (дуга большого круга, погрешность ~0.5% из-за сплюснутости Земли). **`Trip.origin`/`.destination` хранят IATA-коды**, не свободный текст — `AirportSelect` вызывает `onChange(a.iata)`; схема при этом обычный `str`, поэтому прямой POST может положить что угодно → `None`, не исключение. Реальный налёт из внешних сервисов сознательно не берём: +3–7% точности ценой ключа/лимитов/точки отказа, для будущего рейса трека не существует, и это ответ на другой вопрос — мы меряем маршрут доставки, а не мили самолёта. В UI писать **«по прямой»**, никогда «пройдено километров»: расхождение с реальным путём на длинных перелётах 3–7%, но на коротких наземных плечах доходит до 60% (Тбилиси→Ереван: 175 км по прямой, ~280 по трассе) | `backend/app/core/airports.py`, `backend/tests/test_route_distance.py` |
| Вход и регистрация по Nostr-ключу (T3.13) — `/api/auth/nostr/{challenge,verify,signup}` поверх той же машинерии, что `establish`. Три purpose внутри подписанного события вместо URL-привязки NIP-98: подпись одного потока бесполезна в другом, и проверка не зависит от origin из деплой-конфига. Неизвестный ключ → 404 (не 401), аккаунт молча не создаётся. Signup отдаёт токен — пароля нет, иначе аккаунт недостижим | `backend/app/api/nostr_auth.py`, `backend/app/core/identity_proof.py`, `backend/tests/test_nostr_auth.py`, `frontend/src/components/NostrAuthButton.tsx` |
| Личность vs служебный ключ (T3.12) — `establish` с NIP-98-подобным доказательством владения (`core/identity_proof.py`, одноразовый челлендж в `core/challenge.py`), `declare-lost` + `require_live_identity`, идемпотентный бэкфилл служебных ключей в lifespan. `claim`/`import`/`export` удалены | `backend/app/api/keypair.py`, `backend/app/core/{identity,identity_proof,challenge,service_keys}.py`, миграция `0029_identity`, `backend/tests/{test_identity_establish,test_service_keys,test_identity_proof_contract}.py` |
| Перешифровка сейфов при переходе (T3.12) — контейнер: случайный ключ содержимого + NIP-04-конверт на новый npub; vault-конверты: переупаковка session-ключей. Формат конверта `{ct, sender_pubkey}` (строка = legacy, отправитель = автор сообщения) — **без этого переадресовать пакет новому владельцу невозможно**, ECDH требует приватный ключ автора. Читатели: `dealvault`, `threshold`, arbiter-reveal, `DealVaultPage` | `backend/app/core/{verification,identity,threshold}.py`, `backend/app/api/{keypair,dealvault,threshold}.py`, миграция `0030_container_key_envelope`, `frontend/src/lib/threshold.ts` |
| Публикация рейсов под платформенным ключом (T3.12) — `PLATFORM_PUBLISH_NSEC` (отдельный от `CHAIN_ANCHOR_NSEC`), авторство платформенное без подделки под перевозчика, фильтр «интересных» по редкости коридора, `trips.nostr_published_by_pubkey` для NIP-09 | `backend/app/core/{nostr_publish,publish_filter}.py`, `backend/app/tasks/{nostr_publish,nostr_whitelist}.py`, `backend/tests/test_platform_publish.py` |
| Клиентская криптография личности (T3.12) — генерация ключа и подпись челленджа в браузере (`@noble/curves`), сервер получает только npub и подпись. Каноническое событие пришпилено к одному литералу с обеих сторон, иначе расхождение выглядит как 401 «неверный ключ» | `frontend/src/lib/identity.ts`, `frontend/src/test/identity.test.ts`, `backend/tests/test_identity_proof_contract.py`, `frontend/e2e/specs/identity-establish.spec.ts` |
| Email-подтверждение по коду (T3.11) — 6 цифр, bcrypt-хеш в `users.email_verification_code_hash`, TTL 15 мин, cooldown 60 с, 5 попыток. **Исчерпание попыток обнуляет код**, а не только отклоняет догадку. Plaintext существует лишь как аргумент Celery-таска. **Ничего не гейтит** — только баннер в UI | `backend/app/core/email_verification.py`, `backend/app/api/auth.py`, `backend/app/tasks/notifications.py`, миграция `0028_email_verification`, `backend/tests/test_email_verification.py` (20 тестов) |
| Auth только по email (T3.11) — `phone` удалён из `UserCreate`/логина, остаётся полем профиля; `password_hash` nullable под T3.13/T3.14, логин явно отклоняет NULL | `backend/app/{models,schemas}/user.py`, `backend/app/api/auth.py` |
| E2E-обход подтверждения — `E2E_AUTO_VERIFY_EMAIL_DOMAINS` (список доменов через запятую). Пусто на проде; непустое значение → WARNING в lifespan. Гейта нет, поэтому влияет только на то, плодятся ли неиспользуемые коды | `backend/app/core/config.py`, `backend/app/main.py`, `backend/tests/conftest.py` |
| **Гоча тестовой схемы**: `Base.metadata.create_all` создаёт только отсутствующие таблицы и **не делает ALTER** существующих. Любая новая колонка в `users` требует своего `_ensure_*`-хелпера в conftest — зеркала миграции. Иначе сьют падает на несуществующей колонке | `backend/tests/conftest.py` (`_ensure_email_verification_columns` и соседи) |
| **Перешифровка при `establish` — inline и с самопроверкой (T3.12 pt.2b).** Контейнеры переезжают на новый ключ **в транзакции запроса**, а не Celery-таском: таск стартует только после коммита, то есть уже без служебного ключа, и его падение необратимо — перечитать данные больше нечем. Inline любое исключение откатывает всё, пользователь остаётся кастодиальным. Перед уничтожением ключа идёт **доказательство**: ECDH симметричен, поэтому платформа вскрывает только что созданный конверт ключом отправителя, дешифрует блоб до plaintext и сверяет `doc_hash`. Не сошлось → 500 и откат. Цена — латентность по числу контейнеров; при росте объёмов правильный ответ не «унести в очередь», а разнести перешифровку и смену ключа на два шага | `backend/app/api/keypair.py`, `backend/app/core/verification.py` (`rewrap_container_to_identity`, `verify_container_envelope`) |
| **КРИТИЧНО — Celery-воркер работал с пустым реестром задач.** `celery -A app.worker.celery_app` импортирует только `app/worker.py`; ни `include`, ни `autodiscover_tasks` заданы не были, `app/tasks/__init__.py` пуст. Ни одна задача не была зарегистрирована → воркер отвечал `Received unregistered task` на всё, beat исправно слал по расписанию, сообщения выбрасывались. **Никогда не выполнялись:** уведомления по сделкам, пересчёт УБА, обновление whitelist relay'я, ночная чистка e2e-аккаунтов, якоря цепи T3.6, отправка кода подтверждения. Обнаружено 2026-07-27 при разборе «письмо не пришло». Исправлено `include=_TASK_MODULES` в `app/worker.py`; `tests/test_worker.py` проверяет, что всё из `beat_schedule` и всё, что диспатчится из кода, зарегистрировано, и что ни один модуль из `app/tasks/` не забыт | `backend/app/worker.py`, `backend/tests/test_worker.py` |
| **Гоча slowapi + PEP 563**: `from __future__ import annotations` вместе с декоратором `@limiter.limit` ломает разбор тела запроса — обёртка slowapi оставляет аннотации строками, FastAPI не распознаёт Pydantic-модель и трактует параметр как query-скаляр, отдавая `422 {"loc": ["query","body"]}` на любой запрос. По отдельности безвредно: `keypair.py` с future-import без rate-limit работает, `auth.py` с rate-limit без future-import тоже. Правило: **в модуле с `@limiter.limit` future-import не ставить** (T3.13, `nostr_auth.py`) | `backend/app/api/{nostr_auth,auth,keypair}.py` |
| **Остаточный шум финализаторов Redis (осознанно подавлен).** Teardown в conftest закрывает клиента раз на тест-функцию. Там, где loop'ы рождаются и умирают **внутри** теста — hypothesis в `test_contract_fuzz` (≈15 примеров на эндпоинт) и `asyncio.run` в Celery-пути `test_deal_chain` — фикстура до них не дотягивается, и соединения финализируются после смерти своего loop'а. Подавлено `pytest.mark.filterwarnings` в этих двух модулях. Не исправлено намеренно: исправление — отказаться от кеша клиента и открывать соединение на операцию, а `is_blacklisted` вызывается на каждом авторизованном запросе в проде. Менять латентность прода ради тихого лога — плохой размен | `backend/tests/{test_contract_fuzz,test_deal_chain}.py` |
| **Гоча asyncio-Redis**: клиент `redis.asyncio` привязывается к event loop, в котором создан. Кеш на уровне модуля ломается под pytest-asyncio — он делает новый loop на каждый тест, со второго идёт `Event loop is closed`, а брошенные соединения падают в собственном `__del__` уже после смерти loop'а (`PytestUnraisableExceptionWarning`). Общий клиент вынесен в `core/redis_client.py` с кешем **по loop'у** и `aclose_current()`; conftest закрывает его в teardown. Отдельный урок: у `token_blacklist` эта же болезнь пряталась за fail-soft — под тестами отзыв токенов молча не работал, и тесты про logout проходили, не проверяя механизм | `backend/app/core/redis_client.py`, `backend/app/core/{challenge,token_blacklist}.py`, `backend/tests/conftest.py` |
| **КРИТИЧНО — `SyncSessionLocal` не изолирован тестами.** `app/core/database.py` строит его из `settings.DATABASE_URL`, то есть из **боевой** БД. Override `get_db` в conftest подменяет только async-сессию, поэтому любой Celery-таск, вызванный из теста напрямую, работал по проду. 2026-07-26 `test_cleanup_e2e_users_task_deletes_stale` вызвал `cleanup_e2e_users()` без подмены → удалено 22 реальных аккаунта с каскадом по сделкам, сообщениям и рёбрам доверия (36 → 14 юзеров). Исправлено autouse-фикстурой `sync_sessions`, которая перевешивает `SyncSessionLocal` **в каждом импортирующем модуле** (символ импортирован по значению, патч самого `core.database` не помогает). При появлении нового таск-модуля — добавлять его в кортеж фикстуры | `backend/tests/conftest.py` (`sync_sessions`), `backend/app/core/database.py`, `backend/app/tasks/*` |
| **⚠️ Гипотеза, НЕ подтверждённая**: пересборка `celery-beat` перезапускает планировщик и `cleanup_e2e_users` может отработать сразу. Появилась 2026-07-26 как объяснение падения 36 → 14 юзеров на проде — **объяснение оказалось неверным**, настоящей причиной был неизолированный `SyncSessionLocal` (строка выше). Сама механика beat'а никем не проверялась; прежде чем на неё опираться, проверить, а не цитировать | `backend/app/tasks/cleanup.py` |
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
| **Тестовые прогоны: повседневный vs полный (2026-07-25)** — повседневный: `pytest -m "not fuzz"` (~2.5 мин, без schemathesis-фаззера) для итераций во время разработки; **полный: `pytest` без фильтра — блокирующе обязателен перед закрытием любой задачи** (маркер зарегистрирован в pytest.ini). Ускорение прогона 490→312 с: (1) `BCRYPT_ROUNDS=4` — env ставится ТОЛЬКО в pytest-процессе через conftest, прод-хеширование остаётся 12 раундов, сид-юзеры перехешируются автоматически (bcrypt хранит cost в хеше); (2) `ALTER DATABASE vimana_test SET synchronous_commit = off` — per-database, основная БД не затронута; `fsync=off` сознательно НЕ используется (кластерная настройка, риск коррупции основной БД) | `backend/{pytest.ini,tests/conftest.py,app/core/security.py}` |
| **Деплой frontend после T_SEC.2 (D-STATIC-FRONTEND)** — в работающем контейнере НЕТ npm/node (multi-stage: `node:22-alpine` собирает → `nginx:1.27-alpine` раздаёт `dist/`), source volume-mount убран. `docker compose exec frontend npm run build` → «npm: executable file not found»; `restart frontend` НЕ подхватывает изменения исходников. Единственный способ выкатить фронт (включая один только `version.ts`): `docker compose -f docker-compose.dev.yml up -d --build frontend` | `frontend/Dockerfile`, `docker-compose.dev.yml` |
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
| Threshold e2e schema (T2.3) — `is_e2e BOOLEAN DEFAULT false`, `wrapped_shares JSONB`, `read_packages JSONB` на deal_vault_messages | миграция `0016_threshold_encryption` |
| Threshold NIP-04 core (T2.3) — `nip04_encrypt`/`nip04_decrypt` через raw-x ECDH (`PublicKey.multiply`) + AES-256-CBC PKCS7; `E2EPayload` валидатор blob'а | `backend/app/core/threshold.py` |
| Threshold endpoints (T2.3) — `/threshold/arbiter-info`, `/threshold/dealvault/messages/{id}/reveal-my-share`, `/threshold/disputes/{deal_id}/arbiter-reveal` + `arbiter_share_revealed` audit-event | `backend/app/api/threshold.py` |
| Threshold client crypto (T2.3) — `encryptE2E` (SSS split → NIP-04 wrap → AES-GCM), `decryptE2E` (own read_package → session_key → AES-GCM decrypt), `decryptFromShares` (dispute recovery) через `@noble/{ciphers,curves,hashes}` + `shamir-secret-sharing` + `window.nostr.nip04.*` | `frontend/src/lib/threshold.ts` |
| Threshold client API + UI (T2.3) — `api/threshold.ts`, encrypt-on-send в `api/dealvault.ts` (self-custody + NIP-07 + parties known), inline decrypt в DealVaultPage с "🔒 расшифровываю…" fallback | `frontend/src/{api/threshold,api/dealvault,pages/DealVaultPage}.tsx` |
| Nostr publish bridge core (T3.5 pt.1) — `build_event(trip, carrier, url)` kind 30402 NIP-99 + `publish_event` websockets к whitelist + own strfry, `NOSTR_PUBLISH_ENABLED` toggle | `backend/app/core/nostr_publish.py` |
| Nostr publish Celery + endpoints (T3.5 pt.1) — `publish_trip_to_nostr` task при POST /trips, `GET /trips/{id}/nostr-event` on-demand регенерация | `backend/app/tasks/nostr_publish.py`, `backend/app/api/trips.py` |
| strfry контейнер (T3.5 pt.1) — `docker-compose --profile nostr up nostr-relay`, LMDB volume, minimal config; НЕ запускается по умолчанию | `docker-compose.dev.yml`, `nostr/strfry.conf` |
| Nostr NIP-07 self-custody publish (T3.5 pt.2) — `POST /api/nostr/publish-signed` принимает event JSON, recompute event_id + verify Schnorr sig + verify pubkey совпадает с current_user.nostr_pubkey + verify carrier == trip.carrier_id | `backend/app/api/nostr.py::publish_signed_event` |
| Nostr WoT-gate (T3.5 pt.2) — strfry writePolicy plugin читает `/data/allowed_pubkeys.txt` (mtime hot-reload), Celery hourly task `refresh_allowed_pubkeys` генерирует файл из активных TrustEdge + arbiter/superuser role. Non-Vimana pubkey → reject | `nostr/write_policy.py`, `backend/app/tasks/nostr_whitelist.py` |
| Nostr metrics + republish (T3.5 pt.2) — single-row `publish_metrics` таблица (success/error counter + last_attempt_at), `bump_publish_metric` на любом publish, `GET /nostr/metrics` публичный, `POST /nostr/republish/{trip_id}` под `NOSTR_REPUBLISH` permission (superuser) | `backend/app/{core/metrics,models/metrics,api/nostr}.py`, миграция `0019_publish_metrics` |
| УБА core (T3.1) — формула F_norm × Q_norm × V_norm × D_factor × V_verify_norm × 1000, level slugs, `compute_components/compute_uba/level_of/recompute_and_persist` (sync session для Celery) | `backend/app/core/uba.py` |
| УБА Celery beat (T3.1) — `recompute_all_uba` каждый час для активных за 90 дней carrier-ов; queue=notifications | `backend/app/tasks/uba.py`, `backend/app/worker.py` |
| УБА endpoints (T3.1) — `GET /api/me/uba` + `GET /api/users/{id}/uba` → `{uba, level, components}` | `backend/app/api/uba.py` |
| УБА UI (T3.1) — `UBASection` в профиле: score, level chip (navy/cyan/amber градация), 4 component tile'а | `frontend/src/{api/uba,components/UBASection,pages/ProfilePage}.tsx` |
| Playwright smoke suite (T_TEST.3) — `frontend/e2e/` отдельный npm-пакет, `baseURL` prod, 6 spec'ов: single-context (golden/verification/recipient), multi-context pt.2 (invite-flow/auth-rehydrate/admin-guard), headed режим для Mac, trace всегда | `frontend/e2e/{package.json,playwright.config.ts,helpers.ts,specs/*}` |
| E2E user cleanup (T_TEST.3) — Celery beat `cleanup_e2e_users` раз в 24ч по convention `@e2e.vimana.local`, каскадный delete через 12 таблиц | `backend/app/tasks/cleanup.py`, beat schedule в `worker.py` |
| Admin users viewer (T_TEST.3) — `email_contains` filter, `DELETE /admin/users/{id}` async cascade, «test» chip, bulk-friendly UI | `backend/app/api/admin.py`, `frontend/src/{api/admin,pages/AdminUsersPage}.ts(x)` |
| Receiving addresses (T_UX.4 A) — `receiving_addresses` таблица + partial-unique on default per user, backfill из legacy `User.receiving_*` через 0023 (contract-фаза с удалением старых колонок — future) | миграция `0023_receiving_addresses`, `backend/app/{models/address,api/addresses,core/address}.py`, `backend/tests/test_addresses.py` |
| User avatars (T_UX.4 B) — `users.avatar_key VARCHAR(255)`, presigned R2 URL per-request, jpeg/png/webp, max 3 MB, тот же R2 бакет что для DealVault attachments | миграция `0024_user_avatar`, `backend/app/{api/avatar,core/avatar_url}.py`, `backend/tests/test_avatar.py` |
| Chat address picker (T_UX.4 C) — `share-address` в DealVault + Inquiry принимает `address_id`, backend fallback на default → legacy | `backend/app/api/{dealvault,inquiries}.py`, `frontend/src/components/ShareAddressModal.tsx` |
| Tamper-evident deal chain (T3.6) — `deal_events` расширены `seq/entry_hash/prev_hash` (NOT NULL) + `UNIQUE(deal_id, seq)`. Only `append_deal_event` создаёт entry (advisory-lock per deal + hash preimage с fixed field order, scope-binding deal_id, presence-bytes, canonical_json raises на non-serializable). Прямой `db.add(DealEvent)` падает на flush | миграция `0025_deal_event_chain`, `backend/app/{core/deal_chain,models/deal,api/{admin,deals,threshold}}.py`, `backend/tests/test_deal_chain.py` (39 тестов) |
| Chain anchors to Nostr (T3.6) — `deal_chain_anchors(deal_id, seq, entry_hash, nostr_event_id, relays JSON)`. Hourly Celery task публикует head'ы в третьесторонние relay'и signed отдельным `CHAIN_ANCHOR_NSEC`. Row только при ≥1 relay accepted → auto-retry на failed publish. `NOSTR_FRIENDLY_RELAYS` (не own strfry) — evidential weight | `backend/app/{core/chain_anchor,tasks/chain_anchor,models/deal,worker}.py` |
| Vault content chain (T3.7) — `message_added`/`file_added`/`sealed`/`identity_ref` event types; `content_hash_of(ciphertext, nonce)` = sha256 хранимых байтов (E2E верифицируется без расшифровки; ротация MESSAGE_ENCRYPTION_KEY — только envelope); сообщение/файл и его chain-событие коммитятся одной транзакцией; `verify_content()` сверяет content_hash/file_hash цепи с хранимыми строками (ловит delete/swap при интактной цепи); `GET /deals/{id}/chain` расширен sealed_at + coverage + content_mismatches. ВАЖНО: `deal.sealed_at` читать до verify-вызовов (`expire_all` → MissingGreenlet) | миграция `0026_vault_completeness`, `backend/app/{core/deal_chain,api/{dealvault,deals,admin},models/deal}.py`, `backend/tests/test_vault_completeness.py` (9 тестов) |
| Seal / unseal (T3.7, D-SEAL-SEMANTICS) — `Deal.sealed_at` при confirm; guard `_ALLOWED_WHEN_SEALED = {dispute_opened, arbiter_opened}` в `append_deal_event` под advisory lock; `open_dispute` снимает seal, `resolve_dispute(closes_deal)` ставит повторно; `SealedError` → HTTP 409 на messages/attachments/events/share-address | `backend/app/{core/deal_chain,api/{admin,deals,dealvault}}.py` |
| Identity ↔ Deal пересечение (T3.9, D-DVLT-PROTOCOL) — `submit-document` в сделке атомарно создаёт: `IdentityContainer` (шифр ключом владельца) + badge + **копию документа в сделке** (system-message + Attachment `identity_doc`, plaintext в R2, виден участникам) + 3 события цепи; `identity_ref.doc_hash` == `Attachment.file_hash` == `IdentityContainer.doc_hash` (тройное совпадение, проверяется `verify_content`). Kind `identity_doc` не загружается через generic-endpoint (415). Self-upload вне сделки — без цепи | миграция `0027_identity_doc_kind`, `backend/app/{api/verification,core/deal_chain,models/deal}.py`, `backend/tests/test_identity_ref.py` (6 тестов) |
| Контент-валидация загрузок (T3.8) — whitelist-сигнатуры (jpeg/png/webp/heic+brands/pdf), `validate_upload(data, declared_mime)` (декод изображений Pillow `verify()`+`load()`, полиглоты умирают) и `validate_document(data)` (MIME сниффится из байтов, для verification-документов). Валидация ДО записи в R2/`IdentityContainer`; отказ → 422 + warning (без байтов). 4 поверхности: DealVault attachments, avatar, verification submit-document + self-upload. Pillow==10.4.0 (weasyprint<11). Поймал битый PNG_1X1 в тестах (CRC IDAT) — фикстура теперь генерится программно | `backend/app/core/file_validation.py`, `backend/app/api/{dealvault,avatar,verification}.py`, `backend/tests/test_file_validation.py` |
| Статические лендинги DealVault (T3.10) — `frontend/public/dealvault-v5-corporate.html` + `dealvault-v5-rebel.html` отдаются как обычные файлы: Vite копирует `public/` в `dist/` (`publicDir` по умолчанию), внутренний nginx фронта резолвит их через `try_files $uri` до SPA-fallback'а. Роут в `App.tsx` и правка `nginx/default.conf` не нужны. Страницы вне i18n (только RU) и вне SPA-навигации — осознанно, решение владельца «оставить в html-виде». Ранее здесь стояли v3b/v4b (сняты 2026-07-26, исходники остаются в `marketing/`) | `frontend/public/dealvault-v5-corporate.html`, `frontend/public/dealvault-v5-rebel.html` |
| CTA на статических страницах (T3.10) — переключаются **все** элементы с `data-auth-label` разом (на v5 их три: шапка, герой, финальная кнопка — иначе залогиненный видел бы разные подписи сверху и снизу). Гость: «Получить инвайт»; финальная кнопка → `/register`, верхние скроллят к `#cta`. Живая сессия: «Зайти в аккаунт» → `/dashboard`. **Auth-куки в проекте нет** — JWT в `localStorage['token']`, уходит `Authorization: Bearer`; скрипт читает куки (`token`/`access_token`/`vimana_token`) первыми на случай будущей cookie-сессии, затем localStorage; JWT `exp` проверяется, протухший токен сессией не считается. **Файл обязан быть внешним**: прод-CSP `script-src 'self'` (T_SEC.2) без `'unsafe-inline'` молча блокирует любой инлайновый `<script>` на этих страницах | `frontend/public/vimana-cta.js` |
| УБА chip на карточке рейса (T3.2) — TripOut carrier_uba+carrier_uba_level (batch-lookup), `<UBAChip>` компонент с scoped-цветом | `backend/app/{api/trips,schemas/marketplace}.py`, `frontend/src/components/UBAChip.tsx` |
| OperatorAccessGrant (T3.2) — модель + auto-create на open_dispute + explicit grant/revoke endpoints + gate на arbiter vault read (нужен ≥1 active grant) | `backend/app/{models/deal,api/admin}.py`, миграция `0017_operator_access_grants` |
| Verification container encryption (T2.1) — AES-256-GCM key = owner's nsec[:32], custodial-only | `backend/app/core/verification.py` |
| Verification endpoints (T2.1) — create/respond/submit/escalate/self-upload/public listing/revoke | `backend/app/api/verification.py` |
| Polite-decline контракт (T2.1 pt.3) — `GET /deals/{id}/verification-requests` = единственный источник для sender-баннера; `VerificationRequestOut.status`/`.target_role` типизированы enum'ами → OpenAPI объявляет значения, TS-юнионы подкреплены контрактом | `backend/app/schemas/verification.py`, `backend/tests/test_verification.py`, `frontend/src/{api/verification.ts,pages/DealPage.tsx,components/VerificationDeclineBanner.tsx}` |
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
- `Deal(id, order_id→Order, trip_id→Trip, sender_id, carrier_id, recipient_id?, status ∈ {draft, matched, accepted, in_transit, delivered, confirmed, closed, disputed}, sealed_at?, created_at)` — `sealed_at` (T3.7): vault запечатан; NULL = открыт (снимается `dispute_opened`).
- `DealEvent(id, deal_id→Deal, event_type ∈ {…, dispute_opened, arbiter_opened, dispute_resolved, message_added, file_added, sealed, identity_ref}, payload JSON, actor_id, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, timestamp)` — **append-only**. T2.2 pt.2 добавил NIP-01 event поля (nullable); self-custody lenient — остаётся `None`. T3.7: content-события (`message_added` payload = {message_id, content_hash, msg_event_id, is_e2e}; `file_added` = {attachment_id, message_id, file_hash, kind, size_bytes, mime}).
- `DealVaultMessage(id, deal_id→Deal, sender_id?, text_ciphertext BYTEA, text_nonce BYTEA, is_system, nostr_sig?, nostr_event_id?, nostr_created_at?, nostr_pubkey?, is_e2e, wrapped_shares JSONB?, read_packages JSONB?, created_at)` — **иммутабельно**. Легаси T1.21 (`is_e2e=false`): server-encrypted at-rest, property `text` decrypt on access. T2.2 pt.2: NIP-01 event поля. **T2.3 (`is_e2e=true`)**: opaque blob — `text_ciphertext`/`text_nonce` = AES-256-GCM(session_key, plaintext) от клиента, `wrapped_shares` = 3 NIP-04 envelopes (SSS 2-of-3), `read_packages` = 2 NIP-04 envelopes с session_key для sender/carrier normal-read. Property `text` возвращает `None` для e2e — сервер не может расшифровать.
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
