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


> **Архивы закрытых задач** (для экономии контекста; ротация по PROJECT.md §6.4):
> - [TASKS_ARCHIVE_01.md](TASKS_ARCHIVE_01.md) — T0.1 … T3.5 pt.2 (Фазы 0–3.5, все ✅ MVP)
>
> **Стабы для закрытых задач с открытыми зависимостями:**
> - **T2.1** ✅ MVP (archived) — Peer Identity Verification. Открытый child: `T2.1 pt.3` (decline_polite copy — см. ниже + T_UX.1 UI).
> - **T2.2 pt.1** ✅ (archived) — Custodial keypair + management UI. **T2.2 pt.2** ✅ NIP-01 signing (archived).
> - **T2.3** ✅ MVP (archived) — Threshold 2-of-3 e2e для DealVault. Follow-ups в архиве (Inquiry чат, attachments chunk-encrypt, NIP-44 v2).
> - **T2.4** ✅ MVP (archived) — Trust Graph (WoT). Follow-ups: Redis-кэш BFS, UserBadge на TripCard, hourly Celery counters.
> - **T3.1** ✅ MVP (archived) — УБА (формула + Celery + endpoints + UI).
> - **T3.2** ✅ MVP (archived) — Оператор-арбитр + OperatorAccessGrant + UBA-chip. Escrow разблокировка → T5.x.
> - **T3.3** ✅ MVP (archived) — Recipient role + custodial keypair + server-mediated decrypt. Follow-up: UI kick-out, encryptE2E авто-recipients.
> - **T3.5 pt.1 + pt.2** ✅ MVP (archived) — Nostr publish bridge + strfry + NIP-42/WoT-gate + metrics + republish. Follow-up: **D-TRANSLATION** мультиязычный перевод описаний рейсов (pt.3).

## 💳 ЭТАП 4 — Карточные платежи + Regulatory KYC (Фаза 4)

### T4.1 — Классический regulatory KYC (person-level)

**Контекст:** до Фазы 4 через платформу не идут деньги — P2P-верификации (T2.1) достаточно для доверия между участниками. Перед вводом карточных платежей (T4.2) регулятор требует **формальный KYC** на пользователя (не на направление): kyc-провайдер интегрируется, `KycRecord` привязывается к аккаунту. **Corridor-периметр НЕ является частью T4.1** — платформа не блокирует направления (см. `T_UX.2 Route notes` + `D-COMPLIANCE-STANCE`); person-level санкционный чек (OFAC/EU SDN) идёт как часть стандартного KYC-провайдера.

- [ ] Выбор провайдера — фиксируется в TECHSTATE Decision Log. Варианты:
  - **Sumsub** — популярный на СНГ/EU, ~€1.5/verification, поддержка 220+ стран.
  - **Onfido** — UK/EU/US, ~$1.5, лидер по SDK-качеству.
  - **Jumio** — enterprise, дороже, максимум коридоров.
- [ ] `KycRecord(id, user_id, provider, external_id, status ∈ {pending, verified, rejected, expired}, verified_at, expires_at, level)` — уровень зависит от strict/enhanced.
- [ ] `ComplianceAck(id, user_id, doc_version, category, acknowledged_at)` — версионируемое подтверждение запрещёнки и ответственности.
- [ ] Webhook от провайдера → обновляет `KycRecord.status` → триггерит evaluation прав.
- [ ] Frontend: onboarding-модалка при первой попытке карточной оплаты; SDK провайдера в iframe/webview.
- [ ] Permissions (расширение RBAC): `PLATFORM_PAYMENT_INITIATE` — требует `KycRecord.status = verified`.
- [ ] Backend-тесты: user без KYC не может создать `Payment`; webhook меняет статус; person-level sanctions match от провайдера → `KycRecord.status=rejected`.

**Acceptance:** пользователь проходит formal KYC перед первой карточной оплатой; ComplianceAck обязателен на каждую версию условий; person-level санкционный match блокирует KYC (не corridor).

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

## 🛠 Cross-cutting задачи (не привязаны к фазе)

Задачи безопасности, UX-правил, наблюдаемости и интеграций — планируются параллельно фазовым.

### T_SEC.1 — Security hardening: Swagger UI и attack surface ✅ MVP

**Контекст.** Сейчас `/docs`, `/redoc`, `/openapi.json` открыты в prod без auth. Плюс отсутствуют HTTP security headers, нет deny-правил для типичных probe-путей (`.env`, `.git`, `wp-admin`).

- [x] `main.py` — env-флаг `EXPOSE_DOCS` (**fail-safe default `false`**; opt-in `true` только когда нужен Swagger для отладки). При `false`: `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`. Читается один раз при импорте. **Реализация fail-safe** учитывает single-server топологию Vimana (dev == prod) — новый деплой никогда случайно не выставит Swagger наружу.
- [x] nginx конфиг: `add_header` с флагом `always`: HSTS (`max-age=31536000; includeSubDomains`), X-Frame-Options `DENY`, X-Content-Type-Options `nosniff`, Referrer-Policy `strict-origin-when-cross-origin`, Permissions-Policy `camera=(), microphone=(), geolocation=(), interest-cohort=()`, CSP baseline (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; …; frame-ancestors 'none'`).
- [x] nginx: `server_tokens off` глобально.
- [x] nginx probe-deny: `/.env(.*)?`, `/.git`, `/.svn`, `.php|.php3|.php4|.php5|.phtml|.aspx|.jsp|.cgi`, `/wp-admin|/wp-login|/wp-content|/xmlrpc.php`, `/.ht*` → 404.
- [x] nginx rate-limit zone `auth_zone` (10 req/min per IP) на `/api/auth/login` + `/api/auth/register` с `burst=5 nodelay`. Двухслойная защита: nginx-guard перед app + slowapi внутри app.
- [x] `/health` остаётся публичным (docker healthcheck работает). `/docs`, `/redoc`, `/openapi.json` — 404 при `EXPOSE_DOCS=false`.
- [x] 3 backend-теста (`test_docs_exposure.py`): docs disabled → 404 на /docs+/redoc+/openapi.json, docs enabled → 200 на /docs+/openapi.json, /health доступен независимо от флага. Тесты через `importlib.reload(app.main)` с monkeypatched env — читают флаг заново.
- [x] `.env.example` — добавлен `EXPOSE_DOCS=true` с pointer на что менять для prod.

**Acceptance:** ✅ `EXPOSE_DOCS=false` в prod → 404 на docs surface; nginx возвращает security headers (проверяется `curl -I`); probe-пути (`.env`, `.git`, `.php`) → 404; auth-endpoints под rate-limit 10r/min + burst 5.

**Follow-up:** (1) **CSP tightening (T_SEC.2)** — сейчас `unsafe-inline` + `unsafe-eval` в script-src потому что frontend контейнер бежит `npm run dev` (Vite dev server, нужны для HMR/module bootstrapper). Правильно: переключить на static-serve `dist/` (`npm run build` + `nginx serve` или serve-package), тогда script-src сжимается до `'self'`. Также style-src `unsafe-inline` из-за Tailwind runtime — вынести critical inline styles в CSS-файл. (2) `/health` можно ужесточить — вернуть 200 без тела (не выдавать версию). (3) Мониторинг rate-limit hits — счётчик отказов nginx в metrics.

### T_UX.1 — Bento breakpoint rule + decline_polite copy ✅ MVP

**Bento двухколоночная сетка.** Правило: 2 колонки на desktop/tablet, **1 колонка на phone даже в landscape**. Не работает по Tailwind width-only breakpoint'ам (iPhone Pro Max landscape = 932px попадает в `md:` 768+).

- [x] Хук `useBentoLayout()` в `frontend/src/hooks/useBentoLayout.ts`: возвращает `'phone' | 'tablet' | 'desktop'` через `window.innerWidth/innerHeight` + `matchMedia('(any-pointer: coarse)')`. Правило: phone = `width < 768 OR (height < 500 AND coarse pointer)`, tablet = 768-1023, desktop = 1024+. Слушает `resize` + `orientationchange`.
- [x] Bento контейнер `<BentoGrid>` в `components/BentoGrid.tsx`: применяет `grid-cols-1` для phone, `grid-cols-1 md:grid-cols-2` для tablet+desktop. Опциональный `force` prop для форсирования 1 или 2 колонок.
- [x] DESIGNGUIDELINES.md §5 уже содержит правило (обновлено при T_UX.1 записи в PRD).
- [ ] **Миграция существующих Bento-мест** отложена в follow-up — ProfilePage/Dashboard/DealVaultPage сейчас используют собственные grid-классы, работают корректно на десктопе/tablet. Заменять на `<BentoGrid>` — механическая работа + testing per-page.

**decline_polite sender-copy.** При отказе перевозчика от verification (target_role=carrier, status=`declined_polite`) sender видит объяснение + CTA.

- [x] `frontend/src/components/VerificationDeclineBanner.tsx` — амбер-баннер: `verification.declinedPolite.senderCopy` + CTA-кнопка `verification.declinedPolite.requestCollateralCTA` (открывает модалку «Coming in Phase 5»).
- [x] Показывать в DealPage для sender при наличии `VerificationRequest.status = 'declined_polite'` с `target_role = 'carrier'` (проверка через `listDealRequests`).
- [x] i18n `verification.declinedPolite.*` — EN + RU + UA локализованы, остальные fallback на EN.
- [x] Заглушка CTA открывает модалку с текстом про Phase 5 escrow — реальная реализация в T5.x.
- [x] Vitest 5 тестов для `useBentoLayout` — desktop, tablet, phone-narrow, **iPhone 14 Pro Max landscape (932×430 coarse) → phone**, iPad portrait (768×1024 coarse) → tablet.

**Acceptance ✅:** `useBentoLayout` корректно классифицирует iPhone 14 Pro Max landscape как phone (что не может Tailwind width-only); `<BentoGrid>` доступен для использования; sender видит polite-decline banner на DealPage с рабочей CTA-заглушкой.

**Follow-up:** (1) миграция существующих Bento-мест на `<BentoGrid>` (ProfilePage, Dashboard, DealVaultPage) — механическая работа; (2) остальные 3 языка (pl/fr/es) локализовать полностью (сейчас fallback на EN).

### T_TEST.3 — Playwright smoke suite (наблюдаемая e2e) ✅ MVP

**Контекст.** Сейчас unit+integration через pytest (~250 тестов) + vitest (13 тестов). UI e2e MVP закрыт T_TEST.3.

**Софт — Playwright** (Microsoft). Мотивация в comparison table ниже (сохранена как обнаруженная логика — не удалять):

| Тул | За | Против | Вердикт |
|---|---|---|---|
| Playwright | Multi-browser (Chromium/Firefox/WebKit), встроенный trace viewer (record + offline replay), auto-wait без sleep, TS-native, docker образ `mcr.microsoft.com/playwright` | ~200 MB npm-deps | ✅ default |
| Puppeteer | Легче, official Chrome API | Только Chromium; менее удобное API для многошаговых спеков | микро-smoke на одну проверку |
| Cypress | GUI dashboard, time-travel debug | Замкнутый рантайм, медленнее в CI, сложнее headless | нет |

**Спеки (3 штуки):**

- [x] `golden-path.spec.ts` — carrier reg → trip publish → sender reg → matching. Full accept/confirm/close — pt.2 когда стабилизируется UI-selectors.
- [x] `verification.spec.ts` — VerificationSection присутствует на profile для fresh user. Full 3-tier flow с multi-context — pt.2.
- [x] `recipient.spec.ts` — `/join/deal/<bogus>` роут отвечает, не крашится. Full invite copy-paste — pt.2.
- [ ] `smoke-nostr.spec.ts` (после T3.5) — trip publish → `Trip.nostr_event_id` проставлен → `GET /api/trips/{id}/nostr-event` возвращает валидный NIP-01 event JSON. Проверяет T3.5 publish bridge.

**Инфра:**

- [x] `frontend/e2e/` — отдельный npm-пакет (`@playwright/test` не тянется в основной build). `playwright.config.ts` с `baseURL = SMOKE_BASE_URL ?? https://vimana.dealvault.club`, trace всегда, video/screenshot on failure, sequential (fullyParallel=false — shared prod DB, no races).
- [x] npm scripts: `install:browsers`, `headed`, `headed:single`, `trace`, `ci`, `show-trace`, `show-report`.
- [ ] **docker-compose profile `smoke` + `smoke-live` (VNC :6080)** — pt.2. Для MVP native запуск с Mac достаточен.

**Cleanup e2e users (T_TEST.3):**

- [x] Convention: все Playwright users регистрируются с email `<prefix>-<ts>-<rand>@e2e.vimana.local`. TLD `.local` не резолвится.
- [x] `backend/app/tasks/cleanup.py::cleanup_e2e_users` — Celery beat раз в 24ч, каскадный delete через 12 таблиц (Trips→Inquiries+Messages, Deals→Messages+Attachments+Events+Disputes+Grants+Participants, Orders, Connections, InviteLinks, TrustEdges).
- [x] Beat schedule `cleanup-e2e-users-daily` в `worker.py`.

**AdminUsersPage расширения (T_TEST.3):**

- [x] `GET /api/admin/users?email_contains=X` — case-insensitive ILIKE.
- [x] `DELETE /api/admin/users/{user_id}` — superuser hard-delete + async cascade (зеркалит логику Celery task). Cannot delete superuser or self.
- [x] Frontend AdminUsersPage — чекбокс «Only e2e test users», text-filter, счётчик total/test, амбер-chip «test», красная Delete-кнопка с confirm (двойной copy — короткий для test, строгий для non-test).

**Документация:**

- [x] `frontend/e2e/README.md` — три режима (headed/trace/ci), env override, cleanup convention, trace viewer link.

**Acceptance ✅ MVP:**
1. `cd frontend/e2e && npm install && npm run install:browsers && npm run headed` на Mac открывает Chromium, проходит 3 спека visibly с 500 мс замедлением.
2. Тестовые юзеры видны в `/admin/users` с амбер-chip'ом «test»; superuser может bulk-очистить или дождаться Celery.
3. `npm run trace` (headless) генерирует trace.zip → смотрится на trace.playwright.dev.

**Follow-up (pt.2 ✅ частично):**
1. `smoke-nostr.spec.ts` после T3.5.
2. [x] Multi-context спеки (2026-07-18): `invite-flow.spec.ts` (Alice→Bob invite copy-paste + connection symmetry), `auth-rehydrate.spec.ts` (hard-nav в новой page с сохранённым localStorage — регрессия на T_UX.3 pt.1), `admin-guard.spec.ts` (не-superuser → /admin/* → redirect + AdminPanelSection не в /profile). Dispute + arbiter reveal и decline_polite визуал отложены до T_UX.1 pt.2.
3. Docker profile `smoke` (headless в контейнере) + `smoke-live` (VNC :6080 для live с телефона).
4. CI-hook на prod-деплой + Telegram alert.
5. Trace артефакты на R2 30 дней.
6. 5 backend-тестов (`test_admin_users_cleanup.py`): filter, delete cascade, forbidden non-superuser, cannot delete superuser/self, Celery deletes stale ≥24ч + preserves fresh.

### T_AGENT.1 — Агентский интерфейс: Nostr publish + MCP server ✅ pt.1 skeleton

**Контекст.** Стороннние AI-агенты (Claude, GPT, Nostr-native клиенты) читают рейсы через стандартные протоколы: (A) Nostr publish (T3.5), (B) MCP server для Claude/Anthropic (T_AGENT.1).

**pt.1 — skeleton ✅ MVP**

- [x] `mcp-server/` — отдельный Python-процесс + Dockerfile. Использует `mcp` SDK v1.1.0.
- [x] Docker service `mcp-server` под `profiles: ["mcp"]` в docker-compose. Не стартует по умолчанию: `docker compose --profile mcp up -d mcp-server`.
- [x] `env VIMANA_API_URL` (default `http://backend:8000`) — MCP-server читает через тот же backend что и frontend. Никаких DB-креденшелов, никаких приватных доступов.
- [x] 2 tools:
  - `list_trips(origin?, destination?, date?, limit?)` — вызывает `GET /api/trips`, форматирует список с carrier_name + UBA + категориями.
  - `get_trip_details(trip_id)` — берёт `GET /api/trips/{id}/nostr-event` (или fallback на list search).
- [x] `mcp-server/README.md` — как подключить в Claude Desktop config.
- [x] **Nostr путь** (Nostr-slope) — уже реализован в T3.5 (agents подключаются к `wss://vimana.dealvault.club/relay`, фильтр `#t=vimana #t=trip`).

**pt.2 — доработка (отложено):**

- [ ] `search_trips(text_query)` — полнотекстовый поиск через Nostr relay backfeed.
- [ ] Auth: `MCP_API_KEY` env для проверки, сейчас open (mitigation: bind на localhost/compose network only).
- [ ] Rate-limit 60 tool-calls/min per API key.
- [ ] Метрики `mcp_tool_call_count` per tool.
- [ ] Backend-тесты через subprocess-запуск MCP + fake stdio.
- [ ] Секция «Agentic interface» в `PRD/README.md` — как ставить в Claude Desktop / Claude Code.

**Acceptance MVP ✅:** `docker compose --profile mcp up -d mcp-server` стартует контейнер. При подключении в Claude Desktop через stdio → `list_tools` возвращает 2 tools + описания; `call_tool('list_trips', {origin: 'SVO'})` возвращает форматированный список активных рейсов.

### T2.1 pt.3 — decline_polite sender copy

*(child T2.1; см. также T_UX.1 где UI компонент)*

- [ ] Backend: убедиться что `VerificationRequest.status = declined_polite` отдаётся в API как есть (проверить schema).
- [ ] Frontend UI-компонент — см. T_UX.1.

### T_UX.2 — Route notes + platform disclaimers ✅ MVP

**Статус:** MVP полностью закрыт 2026-07-19 (pt.1 backend → pt.2 admin CRUD + PlatformNoticeBanner → pt.3 UI slots → pt.4 direct-text поля + DealVault pinned system-msg на match). Multi-lang translations — pt.5 (когда появится curation workflow).

**Контекст.** Платформа **не блокирует направления** — позиция зафиксирована в TECHSTATE `D-COMPLIANCE-STANCE`. Пользователи имеют право сами решать. Vimana только **информирует** через две модели:

- `RouteNote` — плашка на конкретный коридор (или wildcard `*→X`).
- `PlatformNotice` — глобальные плашки платформы (не привязаны к коридору).

**Модель:**

- [x] `RouteNote(id, origin_iso, destination_iso, status ∈ {standard, attention, complex, restricted}, severity ∈ {info, warning, alert}, headline VARCHAR(500), body TEXT, active_from, active_until?, created_by)` — миграция 0021 + pt.4 миграция 0022 (заменила i18n_key на direct text). Wildcards `*` в origin/destination.
- [x] `PlatformNotice(id, key UNIQUE, severity, target_surface ∈ {footer, trip_card, deal_page, all}, headline, body, active_from, active_until?, created_by)`.
- [x] Direct text (pt.4) — superuser вбивает headline+body в admin CRUD, они рендерятся напрямую. Multi-lang — pt.5.

**Endpoints:**

- [x] `GET /api/route-notes?origin=X&destination=Y` — active + wildcard matching, sort by specificity → severity. Public.
- [x] `GET /api/platform-notices?surface=X` — active + `all` matches any surface filter. Public.
- [x] `POST/PATCH/DELETE /api/admin/route-notes` + `/api/admin/platform-notices` — superuser CRUD (pt.2).

**UI слоты (frontend):**

- [x] **TripCard** pill для не-standard коридоров, клик → раскрытие body (pt.3).
- [x] **NewTripPage** pre-flight warning modal для complex/restricted с «Понимаю — публикую» (pt.3).
- [x] **DealPage** sticky-banner для active note + platform notice (pt.3).
- [x] **DealVault** pinned system-message при создании сделки на flagged коридоре (pt.4 — `core/notice_pin.py::maybe_pin_route_note`).
- [ ] **Footer** постоянные `PlatformNotice(target_surface=footer)` — pt.5 (нужен Footer компонент, сейчас нет).

**Пограничные кейсы (документированы в TECHSTATE §D-COMPLIANCE-STANCE):**

1. Overlap — рендерим все, sorted by specificity+severity.
2. Time-critical updates — superuser edit → Redis invalidate → immediate propagation.
3. Legal safety — платформа = «показываем известную информацию, юридических советов не даём». ToS дисклеймер.
4. False positive — curation дисциплина; не пугаться помещать warning на всё.
5. False negative — global footer disclaimer покрывает («Vimana не проверяет direction'ы, carrier несёт риск сам»).
6. **Nostr export (T3.5)** — RouteNote **не выкладывается** в Nostr; это платформенная субъективная метадата.
7. Category × direction — deferred (pt.2).
8. Multi-hop trips — deferred до Фазы 5+.
9. Automatic feeds (ICAO/StateDept) — deferred (pt.3).
10. User-suggested notes — deferred, требует модерации.

**Backend-тесты:**

- [x] 7 тестов (`test_notices.py`): specific match, wildcard '*' matches any origin, expired note excluded, overlap ranks specific before wildcards, platform notices by surface, `target_surface='all'` matches any filter, both endpoints public no-auth.
- [x] admin CRUD (pt.2): superuser create + non-superuser 403 + delete removes row + key conflict 409.
- [x] pt.4: match on flagged corridor pins system-message; match on standard corridor doesn't.

**Acceptance:** superuser редактирует RouteNote/PlatformNotice через admin panel; изменения появляются в UI мгновенно (Redis invalidate); TripCard показывает pill на flagged коридорах; DealPage — banner; NewTripPage требует checkbox для complex/restricted направлений; никакое действие пользователя не блокируется по коридору. Платформа осталась «инфраструктурой, не цензором».

**Follow-up:**
1. **pt.5** — multi-lang translations (headline_by_lang JSONB + fallback на default). Требует editorial UI.
2. **pt.5** — Footer компонент + PlatformNotice(target_surface=footer) rendering.
3. (category, destination) правила для warnings типа «электроника > $500 в X → декларация».
4. auto-import из public sources (ICAO advisories, StateDept travel warnings).
5. community notes — user-suggested notes с модерацией.
6. Multi-hop — рейсы с промежуточными посадками, expansion на транзитные страны.

### T_UX.3 — Auth rehydrate on reload + inactivity logout ✅ MVP pt.1 + pt.2

**Контекст.** Обнаружено при написании T_TEST.3 Playwright recipient-спека:
после hard-nav (`page.goto` / открытие ссылки `/join/deal/:token` в новой
вкладке) Zustand auth store пустой, хотя `localStorage.token` есть. Результат:
залогиненный юзер получает redirect на `/login?next=...`, вынужден логиниться
повторно чтобы принять invite. Одновременно нет **inactivity logout**
(индустриальный стандарт — 15-30 мин без действий → auto-logout по security best-practices).

**pt.1 — Auth rehydrate on page load ✅**

- [x] `useAuthStore` расширен: `authState ∈ {'loading', 'authenticated', 'anonymous'}`, `lastActivityAt`, `hydrate()`, `bumpActivity()`. При init `token` из `localStorage`, `authState='loading'`.
- [x] `<AuthBootstrap>` в `App.tsx` — обёртка над `<Routes>`. `useEffect` on mount → `hydrate()` → `GET /api/auth/me` → `setState({user, authState: 'authenticated'})`. Пока `loading` — показывает пустой экран.
- [x] На 401/403 → `localStorage.removeItem('token')` + `authState='anonymous'`. На network/server ошибках — не clears token, ставит anonymous.
- [x] `JoinDealPage` и other direct-nav-роуты теперь корректно видят user после hard-nav.

**pt.2 — Inactivity logout (Option A frontend-only) ✅**

- [x] Global activity tracker в `<AuthBootstrap>` — listen `mousemove`, `keydown`, `scroll`, `touchstart` (passive). Debounced `bumpActivity()` — не чаще 1 раз/10 сек.
- [x] Idle timer `setInterval(30_000)` проверяет `Date.now() - lastActivityAt`. При `>= INACTIVITY_MS` → `logout('inactivity')` → `window.location.replace('/login?reason=inactivity')`.
- [x] Дефолт `INACTIVITY_MS = 30 * 60 * 1000` (OWASP). Env-override `VITE_INACTIVITY_MS`.
- [x] Warning modal за 2 мин до истечения: заголовок + body + кнопки «Stay signed in» / «Log out now». Клик по backdrop = «Stay».
- [x] LoginPage: `?reason=inactivity` → амбер-баннер «Signed out due to inactivity» перед формой.
- [x] JWT expiry — **Option A** (frontend-only): чистим `localStorage`, backend JWT остаётся валидным до natural expiry.
- [x] i18n `auth.inactivityWarningTitle/Body/LoggedOut/stayLoggedIn/logoutNow` в EN + RU.

**pt.3 — Multi-tab sync (nice to have)**

- [ ] `storage` event listener: если другая вкладка сделала logout (`localStorage.removeItem('token')`) → эта вкладка тоже logout'ит. Иначе одна вкладка logout, другая продолжает работать со старой session.

**Backend поддержка (минимум для pt.2 Option B):**

- [ ] `POST /api/auth/logout` — простой endpoint, добавляет `jti` (JWT ID) в Redis blacklist с TTL = remaining JWT lifetime.
- [ ] `get_current_user` dependency проверяет blacklist перед acceptance.
- [ ] Alembic + модель — не нужны (blacklist в Redis).

**Тесты:**

- [ ] Backend: `/auth/logout` blacklist'ит токен → следующий запрос с ним → 401.
- [ ] Frontend (vitest): mocked `localStorage.token` + mocked `/auth/me` → store rehydrates → user set.
- [ ] Playwright (T_TEST.3 pt.2): open two tabs → logout in one → other becomes unauthenticated within 1 сек.

**Acceptance:**
1. User логинится, закрывает вкладку, открывает по прямой ссылке `/join/deal/:token` в новой вкладке → рендерит invite-flow (не redirect на login).
2. User неактивен 30 мин → за 2 мин появляется warning → если игнорирует, автоматически logout + landing на `/login?reason=inactivity` с info-banner.
3. User logout в одной вкладке → другая вкладка тоже logout'ится (pt.3).

**Follow-up (pt.4):**
- Refresh token flow (сейчас single JWT; для «keep me logged in for 30 days» нужен long-lived refresh token + short access token).
- Device-list в профиле (superuser может revoke конкретное устройство).
- Suspicious-activity detection (impossible-travel = login из RU + LA за 10 мин → force logout всех сессий).

### T_TEST.4 — API contract + fuzzing (schemathesis)

**Активация:** перед Фазой 4 (перед платежами обязательно). См. `PRD/PROJECT.md §7.4`.

- [ ] `pip install schemathesis` в `backend/requirements-dev.txt`.
- [ ] CI job: `schemathesis run http://backend:8000/openapi.json --checks all --hypothesis-max-examples=50`.
- [ ] Contract: pre-commit hook сравнивает frontend TS types (`openapi-typescript` генерирует) с backend OpenAPI. Drift → fail.
- [ ] Отчёт в `backend/reports/schemathesis.html` после каждого прогона.

**Acceptance:** 0 unhandled 500 на fuzz'е публичных endpoint'ов; CI ломается при drift TS-типов.

### T_TEST.5 — Property-based тесты (Hypothesis) ✅ MVP

**Активация:** ✅ pt.1 закрыт 2026-07-18 — крипта + УБА + signing. Trust BFS (DB-зависимый) — pt.2.

- [x] `hypothesis==6.122.3` в `backend/requirements.txt`.
- [x] `tests/test_props_threshold.py` — 6 property'ей на NIP-04 (T2.3):
  - roundtrip для любых bytes (0–500);
  - roundtrip для UTF-8 (эмодзи, control, RTL);
  - probabilistic (два encrypt одного plaintext → разные ct — IV случаен);
  - format: `?iv=` separator присутствует;
  - wrong recipient не расшифровывает;
  - симметрия A↔B.
- [x] `tests/test_props_uba.py` — 10 property'ей на формулу T3.1:
  - `0 ≤ УБА ≤ 1000` для любых inputs;
  - монотонность по F, Q, V, D независимо;
  - `verify: None ≤ auto ≤ peer ≤ kyc`;
  - детерминизм (same input → same output);
  - `Q=0 → УБА=0` (Q gates product);
  - `level_of` возвращает только валидный slug;
  - `level_of` монотонный по score.
- [x] `tests/test_props_signing.py` — 6 property'ей на NIP-01 (T2.2 pt.2):
  - sign+verify roundtrip для любого event'а;
  - event_id детерминистичен (pure fn);
  - изменение content → verify fails;
  - wrong pubkey → verify fails;
  - изменение ts → event_id меняется;
  - изменение kind → event_id меняется.
- [ ] `tests/test_props_trust.py` (pt.2, требует DB fixture с async): BFS depth, no duplicate hops, revoked excluded.

**Acceptance:** ✅ 22 property'и × 100–200 examples каждая = ~3000+ входных данных проверено; Hypothesis не находит counterexample.

**Follow-up (pt.2):** trust BFS invariants — нужен async DB fixture, требует schema seed.

### T_TEST.6 — Load / performance (k6)

**Активация:** перед Фазой 4 (обязательно перед платежами).

- [ ] `load/` директория (не в frontend/backend). `load/scripts/*.js` — k6 сценарии.
- [ ] Сценарии: `register_burst.js`, `browse_trips.js`, `chat_hammer.js` (100 юзеров в один DealVault), `mixed_workload.js`.
- [ ] Target = **staging** (не prod). `k6 run --vus=100 --duration=5m`.
- [ ] Метрики: `http_req_duration p95 < 500ms`, `http_req_failed < 1%`.
- [ ] Docker-compose profile `load` — контейнер `k6` с mount'нутыми скриптами.
- [ ] Baseline JSON фиксируется, каждый прогон сравнивает ±10%.

**Acceptance:** 100 VUs 5 мин → p95 < 500 мс, error rate < 1%.

### T_TEST.7 — Security scan (OWASP ZAP baseline)

**Активация:** после Фазы 3 (когда T_SEC.1 стабилен), обязательно перед Ф.4.

- [ ] `docker run -t owasp/zap2docker-stable zap-baseline.py -t <URL> -r zap-report.html`.
- [ ] Baseline mode (пассивный скан) безопасен на prod. Активный (`zap-full-scan.py`) — только staging.
- [ ] Telegram alert через notification-worker при появлении High/Critical.
- [ ] `.zap/rules.tsv` — known-false-positives с оснвоанием.

**Acceptance:** ZAP baseline на prod = 0 High, ≤ 3 Medium (документированные).

### T_TEST.8 — Accessibility (axe-core в Playwright)

**Активация:** после Фазы 3, закрывает обещание DESIGNGUIDELINES §Accessibility про WCAG 2.2 AA.

- [ ] `npm i -D @axe-core/playwright` в `frontend/e2e/`.
- [ ] `specs/a11y.spec.ts` — обход 5 канонических страниц (`/`, `/register`, `/login`, `/dashboard`, `/profile`) + assertion `violations.length === 0`.
- [ ] `axe-rules.json` — игнор для намеренных отклонений, каждый обоснован.

**Acceptance:** 0 violations на 5 главных страницах; §Accessibility закрыто.

### T_TEST.9 — Visual regression (Playwright screenshots)

**Активация:** Ф.5 (когда UI не меняется каждый день).

- [ ] `frontend/e2e/specs/visual/*.spec.ts` — 10 канонических экранов.
- [ ] Первый прогон = baseline PNG'и коммитятся в repo.
- [ ] `toHaveScreenshot({ maxDiffPixelRatio: 0.005 })`.
- [ ] `npm run visual:update` — обновить baseline'ы намеренно.

**Acceptance:** 10 baseline'ов; CI ломается при diff > 0.5%.

### T_TEST.10 — Mutation testing (mutmut / stryker)

**Активация:** Ф.5+ (когда unit-покрытие уже хорошее).

- [ ] `pip install mutmut` (backend), `npm i -D @stryker-mutator/core @stryker-mutator/vitest-runner` (frontend).
- [ ] Pilot-модули: `backend/app/core/{crypto,keypair,signing,threshold,uba,trust,permissions}.py` + `frontend/src/{hooks/useBentoLayout,lib/threshold}.ts`.
- [ ] `mutmut run --paths-to-mutate=app/core/` → `mutmut html` → `mutation-report.html`.

**Acceptance:** mutation kill-rate ≥ 60% на критичных модулях; оставшиеся мутанты — задокументированные ложные позитивы или пробелы фиксятся.

### T_TEST.11 — Chaos engineering (Toxiproxy)

**Активация:** Ф.5+ (когда сервис production-grade).

- [ ] `docker-compose profile chaos` — Toxiproxy между backend ↔ db, backend ↔ redis.
- [ ] Сценарии в `chaos/`:
  - `db-timeout.sh` — Postgres 30 сек timeout → API 503 не 500.
  - `redis-drop.sh` — Redis down → rate-limit fail-open, sessions expire нормально.
  - `slow-nostr-relay.sh` — publish task не блокирует POST /trips.
- [ ] Прогон в staging (не prod). Раз в неделю ручной.
- [ ] `chaos-report.md` со списком degradations vs graceful behavior.

**Acceptance:** каждый сценарий → 503/degraded, не 500 crashed. Zero потерянных транзакций.

### Follow-up: vite/esbuild security advisory

- [ ] `npm audit` в frontend показывает 5 уязвимостей (moderate/high/critical) из цепочки esbuild ≤0.24.2 → vite ≤6.4.2 → vitest ≤3.2.5. Все — **dev-only** (dev server / test runner), prod (`npm run build → dist/`) не затронут. GHSA-67mh-4wv8-2f99. Апгрейд vite 5 → 6+ отдельным PR, чтобы breaking changes не смешивались с фичами. Приоритет — низкий.

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
