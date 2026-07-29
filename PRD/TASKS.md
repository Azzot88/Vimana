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
> - **T2.1** ✅ MVP (archived) — Peer Identity Verification. Child `T2.1 pt.3` ✅ MVP (decline_polite copy — см. ниже + T_UX.1 UI). Открытых child'ов нет.
> - **T2.2 pt.1** ✅ (archived) — Custodial keypair + management UI. **T2.2 pt.2** ✅ NIP-01 signing (archived).
> - **T2.3** ✅ MVP (archived) — Threshold 2-of-3 e2e для DealVault. Follow-ups в архиве (Inquiry чат, attachments chunk-encrypt, NIP-44 v2).
> - **T2.4** ✅ MVP (archived) — Trust Graph (WoT). Follow-ups: Redis-кэш BFS, UserBadge на TripCard, hourly Celery counters.
> - **T3.1** ✅ MVP (archived) — УБА (формула + Celery + endpoints + UI).
> - **T3.2** ✅ MVP (archived) — Оператор-арбитр + OperatorAccessGrant + UBA-chip. Escrow разблокировка → T5.x.
> - **T3.3** ✅ MVP (archived) — Recipient role + custodial keypair + server-mediated decrypt. Follow-up: UI kick-out, encryptE2E авто-recipients.
> - **T3.5 pt.1 + pt.2** ✅ MVP (archived) — Nostr publish bridge + strfry + NIP-42/WoT-gate + metrics + republish. Follow-up: **D-TRANSLATION** мультиязычный перевод описаний рейсов (pt.3).

### T3.6 — Tamper-evident hash chain over DealEvents + Nostr anchoring ✅ MVP

**Контекст.** До T3.6 `DealEvent` нёс `nostr_sig`/`nostr_event_id` (T2.2 pt.2) — подпись авторства одной записи. Она **не** доказывает три вещи, критичных для арбитража: (a) **completeness** — сервер мог не записать «неудобное» событие; (b) **ordering** — строки можно поменять местами; (c) **non-deletion** — удалённая строка не оставляет следа. Арбитраж опирается на DealVault как evidence layer, значит эти три бреши закрывать обязательно.

**Threat model (важно, документировано в module docstring):** цепь защищает от того, у кого есть **write** к БД (компрометированный backup, SQL-инъекция, rogue DBA, restore из подделанного дампа). Она **не** защищает от самой платформы — `seq` присваиваем мы, теоретически можем пересчитать всю цепь. Именно поэтому Vimana одновременно арбитр (`ARBITER_USER_ID` + серверный nsec) **и** записчик — а это ровно та конфигурация, где «наш log сходится, мы проверили» проигрывающая сторона обязана оспорить. Пробел закрывается **за пределами** модуля `deal_chain`: `chain_anchor` периодически публикует head'ы в **третьесторонние** relay'и подписанные отдельным platform anchor ключом.

**Модель + миграция:**

- [x] Миграция `0025_deal_event_chain`: `deal_events` расширен `seq BIGINT NOT NULL`, `entry_hash BYTEA(32) NOT NULL`, `prev_hash BYTEA(32) NULL` + `UNIQUE(deal_id, seq)`. Backfill существующих строк в порядке `(timestamp, id)` per deal. **Backfill не ретроактивно tamper-evident** — до миграции строки не хешировались; backfill нужен только чтобы NOT NULL встал и новые entries было к чему цеплять.
- [x] Новая таблица `deal_chain_anchors(id, deal_id, seq, entry_hash, nostr_event_id, nostr_pubkey, relays JSON, created_at)` + `UNIQUE(deal_id, seq)`. Одна строка на успешно опубликованный head.

**`app/core/deal_chain.py` (316 строк):**

- [x] `compute_entry_hash(deal_id, seq, timestamp, event_type, actor_id?, nostr_event_id?, payload, prev_hash)` — детерминистичный sha256 preimage: **fixed field order** (изменение → invalidate всех chain'ов; новая колонка + versioned migration, не edit). `deal_id` идёт первым (scope binding — entry из A нельзя переместить в B). Presence-байты `\x01`/`\x00` перед optional полями (иначе `actor_id=None` хешится как zero-UUID actor). `nostr_event_id` внутри preimage'а — связывает per-record signature с chain'ом (swap подписи → invalidate от entry дальше).
- [x] `canonical_json(payload)` — `sort_keys=True, separators=(',',':')`. **Raises `ChainError`** на non-serializable payload — никогда не подставляет `{}` вместо реального значения.
- [x] `append_deal_event(db, deal_id, event_type, actor, payload, nostr_sig?)` — единственный правильный путь создания `DealEvent`. Берёт transaction-scoped `pg_advisory_xact_lock` на deal → читает head → computes hash → INSERT. Advisory lock релизится и на commit и на rollback — нет explicit unlock который забудут.
- [x] `DealEvent` конструктор + `db.add()` напрямую → падает на flush (NOT NULL по `seq`/`entry_hash`). Это deliberate: unchained event = дыра в записях, IntegrityError громче silent gap.
- [x] `verify_chain(db, deal_id)` — recomputes все hash'и от genesis до head, ловит tamper.

**`app/core/chain_anchor.py` (208 строк):**

- [x] `anchor_pending_heads(db)` — обходит deals, у которых head опережает последний anchor. Один event per deal (не per entry — head покрывает всё под собой).
- [x] Публикует NIP-01 event (kind 30453 vimana-chain-anchor, tags `[["d", deal_id], ["seq", str], ["h", hex(entry_hash)], ["t", "vimana"], ["t", "chain-anchor"]]`, content = canonical_json({...}) с полями).
- [x] Signed через `CHAIN_ANCHOR_NSEC` env (64-hex). **Отдельный ключ** от `ARBITER_USER_ID` и от per-user keypairs — anchor это statement платформы о своих записях, mixing bluring кто про что attest'ит.
- [x] `DealChainAnchor` row записывается только если ≥1 relay accepted. Failed publish → нет строки → следующий tick retry того же head.
- [x] Evidential weight: `NOSTR_FRIENDLY_RELAYS` (третьесторонние), не `NOSTR_OWN_RELAY_URL` — своим strfry можно управлять, значит anchor только там ничего не доказывает. `DealChainAnchor.relays` = per-URL result map для аудита.

**`app/tasks/chain_anchor.py`**: Celery beat, hourly. `CHAIN_ANCHOR_NSEC` unset ИЛИ `NOSTR_PUBLISH_ENABLED=false` → no-op.

**Callsites переписаны на `append_deal_event`** (`api/{admin,deals,threshold}.py`) — раньше делали `db.add(DealEvent(...))` напрямую, теперь бы упало на NOT NULL. Тесты покрывают что во всех трёх code paths chain продолжается.

**Тесты (`test_deal_chain.py`, 39):** hash determinism, canonical JSON (sorted+stripped/None), naive timestamp treated as UTC, non-serializable payload raises (not silent `{}`), presence-byte (None vs zero-UUID vs empty string), genesis GENESIS для первой записи, first entry starts at seq=1 с prev=None, second links to first, two appends в одной транзакции chain'ятся корректно, chains independent per deal, verify empty chain OK, verify intact, edited payload detected, deleted middle entry detected, rewritten prev_hash detected, reordered entries detected, advisory lock защищает от concurrent append race, `append_deal_event` возвращает entry с corectным `seq`/`hash`, каждый admin/threshold/deals callsite chain'ится, anchor tick публикует head, anchor row только при ≥1 relay accepted, failed publish → следующий tick retry, `CHAIN_ANCHOR_NSEC` unset → no-op, `NOSTR_PUBLISH_ENABLED=false` → no-op.

**Acceptance:**
1. Любой INSERT в `deal_events` через `append_deal_event` получает `seq = max(prev_seq)+1`, `entry_hash = sha256(preimage)`, `prev_hash = head.entry_hash`.
2. `verify_chain(deal_id)` возвращает `True` для intact chain'а и `False` c detail'ом первой сломанной entry для tamper.
3. При `CHAIN_ANCHOR_NSEC` + `NOSTR_PUBLISH_ENABLED=true` hourly task публикует все head'ы, изменившиеся с прошлого anchor.
4. Прямое `db.add(DealEvent(...))` вне `append_deal_event` падает на flush — контракт вшит в схему, не в code review.
5. **39 backend-тестов зелёные.**

**Follow-up:**
1. **Публичный endpoint verification** — `GET /api/deals/{id}/chain-proof` для арбитра/проигравшей стороны: отдаёт последние N entries + anchor CID/event_id для independent verification.
2. **UI badge** на DealPage: «Chain verified · anchored at 2026-07-24 · 3 external relays». Клик → детальная страница с preimage'ами.
3. **Merkle-tree аггрегация** через N deals для дешёвого anchoring (сейчас 1 event per deal per tick — не масштабируется на >1000 active deals/hour). Anchor одного merkle-root вместо N head'ов.
4. **Chain для DealVault messages** аналогично DealEvent — сейчас vault-сообщения только signed, не chained.
5. **Rotation** для `CHAIN_ANCHOR_NSEC` — при компрометации ключа нужен overlap period с двумя ключами.

## 🔗 ЭТАП 3.6 — DealVault Protocol: полнота цепи + Identity-пересечение (Фаза 3.6)

> **Контекст этапа.** Концепция «DealVault — The Verifiable Vault Protocol» (v0.1): каждая сделка — переносимый, иммутабельный, криптографически проверяемый артефакт; Identity Vault и Deal Vault пересекаются по данным. T3.6 построил tamper-evident цепь, но только по статусным событиям. Этот этап делает цепь **полной** (сообщения, файлы, identity-события), вводит **запечатывание** при закрытии сделки и валидацию содержимого файлов. Публикация якорей остаётся выключенной (server-only, внутренняя связность) — расширение заложено схемой: Nostr (готово, T3.6), IPFS, OpenTimestamps. Решения зафиксированы в TECHSTATE `D-DVLT-PROTOCOL`. Отложено осознанно (follow-up этапа, не задачи): Query API (`TRUE/FALSE/ACCESS_DENIED` + proof), .dvlt-экспорт + Reader, включение публикации якорей, EXP-07 (участник-подписанный `prev`).

### T3.7 — Полнота цепи: сообщения, файлы, seal ✅ MVP

**Контекст.** Цепь T3.6 покрывает 11 статусных событий. `DealVaultMessage`/`Attachment` подписаны (T2.2 pt.2), но не chained: удаление сообщения из БД не ломает `verify_chain` → completeness не гарантирована именно для контента, ради которого vault существует. Сделка не запечатывается — append возможен после `closed`. Это follow-up 4 из T3.6, повышенный до задачи.

**Механика хеширования содержимого:** хешируются байты **как они хранятся** — `sha256(text_ciphertext || text_nonce)`. Для E2E-сообщений это ciphertext (сервер plaintext не видит, верификация не требует расшифровки). Следствие: ротация `MESSAGE_ENCRYPTION_KEY` с перешифровкой данных запрещена — только envelope-схема (перешифровка ключа, не данных). Формат preimage T3.6 **не меняется** — новые данные входят через `payload` обычных `DealEvent`.

- [x] Новые `DealEventType`: `message_added`, `file_added`, `sealed`, `identity_ref` (используется в T3.9). Миграция `0026` + зеркало в tests/conftest.
- [x] `message_added` — в той же транзакции, что INSERT сообщения: `append_deal_event(actor=автор, payload={message_id, content_hash: sha256(text_ciphertext+text_nonce), msg_event_id: nostr_event_id сообщения, is_e2e})`. Покрыты все точки создания сообщений: обычные, e2e, share-address, pinned route-note (match), arbiter system-message.
- [x] `file_added` — payload `{attachment_id, message_id, file_hash, kind, size_bytes, mime}`.
- [x] `sealed` — при `confirm` (→ closed): финальное событие, payload `{message_count, file_count}` + `Deal.sealed_at`.
- [x] Запрет append после seal: guard в `append_deal_event` под advisory lock → `SealedError` (API → 409). **Решено (D-SEAL-SEMANTICS):** спор после `closed` возможен — `dispute_opened` распечатывает vault (единственное content-исключение), закрывающий вердикт (`closes_deal`) запечатывает снова; `arbiter_opened` проходит через seal как audit-событие (аудит ≠ контент), system-message при чтении sealed vault арбитром не пишется.
- [x] Миграция: `deal_chain_anchors.backend VARCHAR(16) NOT NULL DEFAULT 'nostr'` (`nostr` | `ipfs` | `ots`). Код IPFS/OTS-бэкендов не писали — только схема.
- [x] **Отклонение:** вместо нового `/vault/verify` расширен уже существовавший `GET /api/deals/{id}/chain` (follow-up 1 из T3.6 оказался частично закрыт в T3.6): + `sealed_at`, coverage `{chained/total messages, chained/total files}`, `content_ok`, `content_mismatches` (новая `verify_content()` — сверка content_hash/file_hash цепи с хранимым контентом).
- [x] Старые сделки: backfill не делаем — цепь валидна, coverage честно показывает долю незачейненных сообщений.
- [x] Тесты: 9 новых (`test_vault_completeness.py`) + обновлён lifecycle-тест T3.6 (6 событий вместо 5). Грабля: `deal.sealed_at` читать ДО `verify_chain`/`verify_content` — они делают `expire_all()` → MissingGreenlet.

**Acceptance: ✅ все выполнены**
1. ✅ Отправка сообщения/загрузка файла создаёт chained-событие в той же транзакции; подмена `text_ciphertext` или файла детектируется через content_hash/file_hash.
2. ✅ Deal → `closed` порождает `sealed`; append после → 409 на всех поверхностях (messages, attachments, events, share-address).
3. ✅ `GET /deals/{id}/chain` отдаёт `ok`/`broken_at` + seal + coverage + content-проверку.
4. ✅ **657 backend-тестов зелёные** (2026-07-25).

### T3.8 — Валидация содержимого файлов (anti-dirt) ✅ MVP

**Контекст.** MIME берётся из заголовка клиента + whitelist (T1.19) — подделывается тривиально. Защиты от залива «грязи» (исполняемые, полиглоты, не-изображения под именем .jpg) нет.

- [x] **Отклонение:** вместо puremagic — рукописный whitelist сигнатур в `core/file_validation.py` (6 типов, ноль новых зависимостей, строже: контент обязан нести magic bytes заявленного типа — MZ/ELF/shebang/HTML отваливаются автоматически, не перечислением).
- [x] Изображения: Pillow `verify()` + полный decode (`load()`) — невалидный JPEG/PNG/WebP → 422. HEIC/HEIF — по сигнатуре `ftyp`+brand (Pillow без кодека, pillow-heif не тянем). Pillow закреплён `10.4.0` (weasyprint 63 требует <11).
- [x] PDF: проверка заголовка `%PDF-`.
- [x] Стриминговый SHA-256 и лимит 10 MB сохранены; валидация до записи в R2.
- [x] Отклонённые загрузки логируются warning'ом (метаданные, не содержимое).
- [x] **Бонус сверх плана:** та же валидация на avatar-upload и на verification-документы (`validate_document()` — заявленный MIME не доверяется вообще, тип сниффится из байтов; было: ноль проверок перед `IdentityContainer`). Пригодится в T3.9.
- [x] Тесты: 20+ в `test_file_validation.py` (юниты сигнатур/декода/сниффинга + API-wiring на 4 поверхности). **Валидатор на первом прогоне поймал битый PNG_1X1 в самих тестах** (рукодельный hex с неверным CRC IDAT жил с T1.19) — фикстура теперь генерируется программно, CRC корректны by construction.
- [ ] Follow-up (не блокер): ClamAV-контейнер.

**Acceptance: ✅ все выполнены** — exe/скрипт под именем `.jpg` → 422 на всех поверхностях; валидные jpeg/png/webp/heic/pdf проходят; **696 backend-тестов зелёные** (2026-07-25).

### T3.9 — Identity ↔ Deal пересечение (identity_ref + копия документа в сделке) ✅ MVP

**Контекст + решение владельца (D-DVLT-PROTOCOL).** Данные identity, внесённые в сделку, живут в обоих vault'ах: канонический документ — в `IdentityContainer` владельца (переиспользуемый, уже так с T2.1), **полная копия — в сделке** (vault самодостаточен), связь — событие `identity_ref` в цепи через общий `doc_hash`.

- [x] `AttachmentKind.identity_doc` (миграция `0027` + зеркало в conftest); копия — Attachment на system-сообщении, R2, `file_hash` = sha256 plaintext-байтов. Доступ — участники сделки; канонический контейнер — только владелец. Через generic-endpoint kind не загружается (нет в MIME-whitelist → 415).
- [x] `identity_ref`: payload `{container_id, attachment_id, badge_id, doc_hash, doc_type, doc_country}` — тройное совпадение `doc_hash` (цепь == копия == контейнер) проверяется расширенным `verify_content()` (reasons: identity copy/container hash mismatch, missing).
- [x] `submit-document` (T2.1): контейнер + бейдж + копия + system-message + 3 события цепи (`message_added`/`file_added`/`identity_ref`) — одна транзакция (`_copy_document_into_vault`). `_read_upload` теперь возвращает `(bytes, detected_mime)` из T3.8-сниффинга. Sealed deal → 409. Self-upload вне сделки — без изменений (нет событий цепи).
- [x] UI: system-message «🪪 Identity document verified and added to the vault» + label «Документ личности» для kind.
- [x] Тесты: 6 в `test_identity_ref.py` (тройной hash-match, подмена копии — двойная детекция через file_added+identity_ref, удаление контейнера, self-upload без событий, generic-upload → 415).

**Acceptance: ✅ все выполнены** — IdentityContainer + Attachment-копия + `identity_ref` в цепи, `doc_hash` совпадает во всех трёх местах, подмена детектируется `GET /deals/{id}/chain`. **702 backend-теста зелёные** (2026-07-25).

### T3.10 — DealVault: маркетинговая презентация + лендинг

**Контекст.** Сразу после закрытия T3.9 — публичная упаковка концепции «Verifiable Vault Protocol»: преза + секция лендинга на базе Concept v0.1 и реализованного (полная цепь, seal, identity-пересечение, якоря).

**Процесс (решение владельца, 2026-07-25):** это будет **версия 1**. Затем владелец подключит другие инструменты/скиллы, будет собрана альтернативная версия — и обе сравниваются перед публикацией. v1 не публикуется как финал без сравнения.

- [ ] Презентация концепции (структура: проблема доверия → Vault ≠ база данных → Identity/Deal Vault → immutability + подписи + якоря → roadmap: Query, .dvlt, IPFS/OTS).
- [x] Страница на лендинге (DESIGNGUIDELINES + Bento) — **две версии в репо для сравнения**, обе статические: `frontend/public/dealvault-v5-corporate.html` и `dealvault-v5-rebel.html` (выбор владельца 2026-07-26; v3b и v4b из `public/` сняты, исходники остаются в `marketing/`).
- [ ] Тон: «Trust is derived from cryptographic evidence» — без обещаний невыключенных фич (публикация якорей — как roadmap, не как факт). **Не выполнено на выставленных версиях** — см. «Расхождение по тону» ниже.

**Сделано 2026-07-26 (страницы):**
- Обе версии лежат в `frontend/public/` и попадают в `dist/` штатным копированием Vite (`publicDir` по умолчанию) → отдаются nginx фронта как обычные файлы по `/dealvault-v5-corporate.html` и `/dealvault-v5-rebel.html`. Ни React-роут, ни правка `nginx/default.conf` не требуются: `location /` уже делает `try_files $uri /index.html`, существующий файл выигрывает.
- Страницы остаются **статическим HTML** (решение владельца) — не переносились в `LandingPage.tsx` и не разбирались на компоненты. Следствие: они не проходят через i18n (только RU) и не участвуют в SPA-навигации.
- CTA на каждой странице продублирован трижды (шапка, герой, финальная секция) и переключается разом: гость — «Получить инвайт» (шапка и герой скроллят к `#cta`, финальная ведёт на `/register`); при живой сессии все три — «Зайти в аккаунт» → `/dashboard`. Логика в `frontend/public/vimana-cta.js`, селектор `[data-auth-label]`.
- **Отклонение от постановки:** задача ставилась как «проверить по кукам», но auth-куки в проекте нет — JWT живёт в `localStorage['token']` и уходит заголовком `Authorization: Bearer` (`api/auth.py`, `stores/auth.ts`, `api/client.ts`). Скрипт сначала читает куки (`token` / `access_token` / `vimana_token`) на случай будущей cookie-сессии, затем `localStorage`. Протухший `exp` сессией не считается.
- **Ограничение CSP:** прод-CSP из T_SEC.2 — `script-src 'self'` без `'unsafe-inline'`. Инлайновый `<script>` на этих страницах будет молча заблокирован, поэтому вся JS-логика вынесена в отдельный same-origin файл. При любой доработке страниц инлайн-скрипты не добавлять.

**Расхождение по тону (обнаружено 2026-07-26, требует решения владельца).** Выставленные v5-версии содержат формулировки сильнее, чем позволяет реализация. Текст не правился — страницы взяты как есть по решению владельца; фиксируем расхождение, чтобы оно не уехало в прод молча:
- «Ни у нас, ни у арбитра, ни у владельца платформы нет ни кнопки, ни функции, ни задней двери… чтобы изменить то, что уже произошло» и блок «Не хотим. Не будем. Не можем.» (раздел 04) — цепь **tamper-evident, не tamper-proof**. Строку в БД изменить можно; ломается сходимость цепи. Прямо противоречит threat model из docstring'а `core/deal_chain.py` (T3.6): «цепь защищает от rogue-DBA/дампа, НЕ от самой платформы».
- «Выгрузка сделки · Скоро» (раздел 08) — `.dvlt` + Reader **отложены осознанно** (D-DVLT-PROTOCOL п.6), сроков нет. «Скоро» здесь — обещание невыключенной фичи.
- «Арбитр видит переписку» (раздел 06) — доступ требует активного `OperatorAccessGrant` (T3.2), не наступает автоматически по факту приглашения.
- Формулировка про якоря/проверку без нас на страницах отсутствует — здесь расхождения нет.

Варианты: (а) поправить три места в v5 перед деплоем; (б) взять решение v4b, где выключенное вынесено в отдельные блоки `.block.road`; (в) осознанно принять риск и снять критерий тона из acceptance. До решения **пункт «Тон» остаётся открытым**.

**Осталось для закрытия T3.10:** презентация концепции; выбор между v5-corporate и v5-rebel; закрытие расхождения по тону; деплой выбранной версии.

**Acceptance:** преза согласована владельцем; лендинг-секция задеплоена; формулировки не заявляют невключённые механизмы как работающие. — *частично: страницы выставлены и отдаются, преза не сделана, критерий формулировок на v5 не выполнен.*

## 🔑 ЭТАП 3.7 — Идентичность и вход (Фаза 3.7)

> **Цель:** три способа входа поверх одной личности, где **личность и есть ключ**. Разделение уровней ответственности (решение владельца 2026-07-26):
>
> - **npub (Nostr-pubkey)** — личность. Неизменна на всём сроке жизни аккаунта. Отдельной сущности DID нет: `nostr_pubkey` и есть идентификатор, `did:`-обёртка не вводится.
> - **Passkey / Nostr-подпись / пароль** — способы **входа**. Сменяемы, множественны, к личности не приравниваются.
> - **JWT** — краткоживущая веб-сессия (уже есть, T_UX.3).
> - **YubiKey** — не отдельный механизм: WebAuthn-аутентификатор с аппаратной привязкой, используется как step-up.
>
> ```
>                   npub = личность
>                          │
>        ┌─────────────────┼─────────────────┬──────────────┐
>     iPhone            MacBook           YubiKey       nsec (NIP-07)
>     Passkey           Passkey           Passkey       подпись
>            ── способы доказать, что это ты ──
> ```
>
> Утеря устройства → отвязка его Passkey; npub и остальные способы входа не затронуты. **Утеря ключа → утеря личности** — это принято сознательно (см. решение №4).
>
> **Решения владельца (2026-07-26):**
> 1. Телефон убирается из регистрации и логина. Колонка `User.phone` остаётся nullable-полем профиля (контакт перевозчика), из auth-путей уходит.
> 2. Email **опционален**: аккаунт, созданный через Nostr-ключ или Passkey, живёт без email.
> 3. Подтверждение email **ничего не блокирует** (уточнено владельцем 2026-07-26 по итогам T3.11): это вопрос безопасности, а не прав. Неподтверждённый адрес не мешает ни войти, ни опубликовать рейс, ни начать сделку. Он ставит под вопрос сам канал — на этот адрес возвращается доступ к аккаунту и приходят уведомления по сделкам, и пока он не подтверждён, неизвестно, доходят ли письма до владельца аккаунта. Поднимает это UI (баннер + экран кода), а не API.
> 4. **Личность = ключ (self-sovereign identity).** Философия проекта ближе к Nostr и Bitcoin: «ключ и есть личность». Смена или потеря ключа означает **появление новой личности**, а не восстановление старой. Осознанный отказ от «неизменной личности при смене ключа» — концептуально чище и соответствует SSI, ценой того, что утрата ключа необратима.
> 5. **Инфраструктурный ключ ≠ личность.** Регистрация продолжает выдавать keypair, как сегодня (T2.2) — но это **служебный ключ сейфа**: им платформа шифрует и подписывает содержимое, он не показывается как «ваш Nostr-ключ» и никогда не публикуется наружу. Отдельной колонки не нужно: `key_self_custody = false` уже означает «это служебный ключ», `true` — «это личность пользователя».
> 6. **Личность создаётся при переходе — и всегда новым ключом.** `claim` в нынешнем виде убирается: он повышал служебный ключ до личности, а ключ, приватная часть которого всю жизнь лежала у платформы, суверенной личностью быть не может — доказать, что копия не осталась, невозможно. Переход (`establish identity`) даёт либо ключ, **сгенерированный в браузере пользователя** (сервер не видит nsec ни на миллисекунду), либо принесённый свой. Служебный ключ при этом уничтожается, сейфы перешифровываются на новый npub.
> 7. Восстановление по recovery-коду возвращает **доступ к аккаунту, но не ключ**. До self-custody у платформы есть всё — восстанавливается полностью. После: ключ жив (потеряно устройство) → восстанавливается всё; ключ утрачен → история и УБА **не переезжают**, чистый старт с новой личности, старый аккаунт остаётся мёртвым архивом.
> 8. Переход в self-custody **не блокируется**: экран последствий с обязательным чекбоксом, но платформа не мешает — уважение к суверенитету пользователя.
>
> **Два состояния аккаунта (следует из решений 4–7):**
>
> | | Служебный ключ (`key_self_custody = false`, дефолт) | Своя личность (`true`, после перехода / nostr-signup) |
> |---|---|---|
> | Чей ключ | платформы: nsec зашифрован и лежит у нас | пользователя: nsec у него, у нас его нет |
> | Что это для пользователя | ничего — механика шифрования сейфа, в UI как ключ не подаётся | его личность, публичный идентификатор |
> | Шифрование и подпись | служебным ключом, как сегодня | ключом пользователя |
> | Публикация рейсов | под `PLATFORM_PUBLISH_NSEC`, отобранные фильтром, имя перевозчика в содержимом | под ключом пользователя |
> | Потеря устройства | recovery-код → всё на месте | recovery-код → аккаунт и переписка, npub тот же |
> | Потеря **ключа** | невозможна — ключ не у пользователя | необратима: новая личность, старая переписка не читается никем |
>
> **Почему рейсы не публикуются служебным ключом.** Опубликованное событие остаётся в сторонних relay'ях навсегда. Если публиковать под служебным npub, который при переходе будет уничтожен, в сети останутся события от личности, более никому не принадлежащей — ровно та подмена, от которой уходит вся фаза.
>
> **Состояние прода на 2026-07-26** (проверено запросами): 36 аккаунтов, из них 24 со служебным ключом, 12 без; арбитр и superuser **без ключей** — из-за чего `threshold` 2-of-3 сейчас не собирается (`api/threshold.py:40` требует `arbiter.nostr_pubkey`). Подписанных записей 0, identity-контейнеров 0, E2E-сообщений 0, опубликованных рейсов 0. Легаси-случая «ключ уже стал личностью» **не существует** — все ключи ничем не связаны, поэтому особой ветки для старых аккаунтов не нужно, нужен бэкфилл (T3.12).

### T3.11 — Email-only регистрация + подтверждение кодом ✅ MVP

**Контекст.** Сейчас `POST /api/auth/register` принимает email **или** phone (`app/api/auth.py:26`), email никак не подтверждается, `User.password_hash` NOT NULL. Задача убирает phone из auth-путей и вводит подтверждение владения ящиком по 6-значному коду. SMTP уже настроен (`SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_PORT`, ENVIRONMENT §секреты), `core/email.send_email()` работает с T1.7.

**Схема (миграция `0028_email_verification`):**
- [x] `users.password_hash` → **nullable** (аккаунты из T3.13/T3.14 живут без пароля).
- [x] `users.email_verified_at TIMESTAMPTZ NULL`, `email_verification_code_hash VARCHAR(255) NULL`, `email_verification_expires_at TIMESTAMPTZ NULL`, `email_verification_attempts SMALLINT NOT NULL DEFAULT 0`, `email_verification_sent_at TIMESTAMPTZ NULL`.
- [x] Backfill: существующим юзерам с email → `email_verified_at = created_at`. Живых пользователей не выкидываем в «неподтверждённые». На проде отработал: 13 из 13 аккаунтов с email помечены (2026-07-26).

**Backend:**
- [x] `UserCreate`: `phone` удалён, `email` обязателен + валидатор формы адреса и нормализация в нижний регистр. `UserUpdate.phone` **остаётся** — телефон правится в профиле.
- [x] `UserLogin.login` — только email; ветка по phone удалена. Дополнительно: `password_hash IS NULL` теперь явно отклоняется — раньше `verify_password(None)` упал бы, а с T3.13/T3.14 такие аккаунты появятся.
- [x] Код: 6 цифр через `secrets.randbelow(10**6)`, хранится **хешем** (`core.security.hash_password`), TTL 15 минут, максимум 5 попыток — исчерпание **сжигает код целиком**, а не просто отклоняет попытку.
- [x] `POST /api/auth/email/request-code` → 202. Отправка — **через Celery-таск** `app.tasks.notifications.send_verification_code`: `core/email.send_email()` синхронный `smtplib` и заблокировал бы event loop. Plaintext идёт аргументом таска — в БД только хеш, больше он нигде не существует.
- [x] `POST /api/auth/email/verify` `{code}` → ставит `email_verified_at`, чистит состояние кода. Повторный вызов — идемпотентный 200.
- [x] Rate-limit **на двух уровнях**: slowapi `5/hour` на `request-code` + `limit_req zone=email_verify_zone` на `/api/auth/email/` в `nginx/default.conf`. Плюс cooldown 60 с через `email_verification_sent_at` → 429.
- [x] **Гейта нет.** Подтверждение не влияет ни на один эндпоинт: ни вход, ни `POST /trips`, ни `POST /deals/match` его не проверяют. Первая редакция задачи вводила «мягкий гейт» на создание сделок и рейсов — снято владельцем 2026-07-26 (решение №3): подтверждение адреса это безопасность, а не права. Единственная поверхность — UI.
- [x] `MeOut.email_verified: bool` — производное свойство `User.email_verified`, читается через `model_validate(from_attributes=True)`.

**Frontend:**
- [x] `RegisterPage.tsx` — телефона в форме не было уже с T1.11, поле не трогали. Изменён только переход после регистрации: на `/verify-email`, если адрес не подтверждён. `RegisterPayload.phone` удалён из типа — теперь `tsc` ловит попытку отправить телефон, а не бэкенд в рантайме.
- [x] `LoginPage.tsx` — `auth.email` вместо `auth.emailOrPhone`, `type="email"`.
- [x] `pages/VerifyEmailPage.tsx` (роут `/verify-email` внутри Layout) + `components/EmailVerifyBanner.tsx` в `Layout.tsx`. Баннер скрыт для аккаунтов **без** email: адрес не заявлен — подтверждать нечего.
- [x] i18n — **все шесть локалей** (EN/RU/UA/PL/FR/ES), не только три: экран новый, fallback на EN для продукта с шестью языками не годится. Попутно во всех поправлен `errorDuplicate`, упоминавший телефон. Ключ `auth.emailOrPhone` остался неиспользуемым — на сборку не влияет.

**E2E:**
- [x] Ничего не гейтится → T_TEST.3 не затронут вовсе. Тем не менее env `E2E_AUTO_VERIFY_EMAIL_DOMAINS` (список через запятую, по умолчанию **пусто**) помечает регистрации на этих доменах подтверждёнными сразу — чтобы тестовые прогоны не плодили коды, которые никто не читает. На dev = `e2e.vimana.local` (TLD `.local` не резолвится), на prod **не задаётся**: флаг «подтверждён» должен означать, что кто-то реально открыл ящик. Непустое значение → WARNING в лог на старте.

**Тесты:** request-code (202 · cooldown 429 · без email → 422 · уже подтверждён) · verify (успех · неверный код · истёкший · исчерпание попыток сжигает код · идемпотентность) · код хранится хешем · регистрация с `phone` → 422 · логин по телефону → 401 · **неподтверждённый юзер публикует рейс → 201 и начинает сделку → не 403** · аккаунт без email работает как обычный · auto-verify домен не шлёт код · SMTP замокан (в реальный ящик не ходим).

**Отклонения от постановки:**
- Переменная названа `E2E_AUTO_VERIFY_EMAIL_DOMAINS` (список через запятую), а не `..._DOMAIN` — тестам нужны два домена сразу.
- Гейт был реализован и **снят в тот же день** по решению владельца. Тесты переписаны в обратную сторону: проверяют, что неподтверждённый пользователь публикует рейс и начинает сделку. Сделано намеренно — фича «подтвердите почту» склонна тихо отрастать обратно в проверку прав.
- i18n сделан на шесть локалей вместо трёх (см. выше).

**Acceptance: ⚠️ выполнены частично** — регистрация только email+пароль ✅; подтверждение не влияет ни на одно право, разница только в баннере ✅. **728 backend-тестов зелёные** (полный прогон с fuzz, 2026-07-26).

**Критерий «код приходит письмом» НЕ подтверждён.** Проверка вживую 2026-07-27: регистрация на реальный Gmail с прода — экран ввода кода отрисован, код сгенерирован, Celery-таск поставлен, **письмо не пришло**. Тесты доставку не проверяют и проверять не могут: SMTP в них замокан, иначе сьют слал бы реальную почту. Нужна настройка почтового сервера. До этого фича работает наполовину — пользователь видит требование подтвердить адрес и не может его выполнить, а `notify_email` (T1.7) с той же вероятностью не доходит. **Email-подтверждение не подавать как рабочее, пока доставка не проверена вживую.**

### T3.12 — Служебный ключ vs личность: establish identity ✅ MVP

**Контекст (решения владельца №5 и №6).** Механика T2.2 остаётся целиком: keypair выдаётся при регистрации, платформа хранит nsec, им шифруются контейнеры и подписываются записи. Меняется не код шифрования, а **чем этот ключ называется**. До перехода это служебный ключ сейфа, а не личность: пользователю он не показывается, наружу не публикуется, никаких обещаний суверенности с ним не связано.

Такой подход выбран вместо «ключа нет вообще» сознательно: тот вариант требовал переписать четыре работающих механизма — шифрование `IdentityContainer`, ветку безключевого участника в `dealvault.py`, поведение threshold при участнике без ключа и весь `D-RECIPIENT-ROLE` (невидимый custodial keypair recipient'а). Здесь не меняется ни один из них.

**Почему `claim` убирается.** Сегодня `POST /api/me/keypair/claim` повышает служебный ключ до личности, просто удаляя серверную копию nsec (`app/api/keypair.py:92-115`). Но приватная часть этого ключа всю жизнь лежала у платформы — доказать, что копия не сохранилась, невозможно ни технически, ни юридически. Личность, построенная на таком ключе, «суверенна» только на честном слове платформы, то есть ровно настолько, насколько вся фаза пытается этого избежать. Поэтому переход **всегда даёт новый ключ**.

**Одна механика на оба пути.** Ключ может родиться в браузере (`@noble/curves` уже в зависимостях фронта) или прийти из NIP-07-расширения — серверу это безразлично. Ему нужно единственное: доказательство, что вызывающий контролирует заявленный npub. Иначе достаточно прислать чужой известный npub, чтобы присвоить чужую личность — сегодняшний `import` именно это и позволяет, принимая голый `npub_hex` без всяких проверок (`app/api/keypair.py:135-141`). Поэтому эндпоинт один, а «сгенерировать» и «принести своё» — различие целиком фронтовое.

**API после задачи:**
- [x] `POST /api/me/identity/challenge` → одноразовый nonce (Redis `GETDEL`, TTL 300s). `core/challenge.py` — **не** fail-soft, в отличие от `token_blacklist`: там падение Redis означало «отдать ещё живой JWT», здесь означало бы «принять доказательство, которого мы не выдавали».
- [x] `POST /api/me/identity/establish` — проверяет подпись челленджа новым ключом (`core/identity_proof.py`), ставит `nostr_pubkey`, `key_self_custody = true`, **уничтожает** `nsec_encrypted`/`nsec_nonce`. Занятый npub → 409, повторный вызов → 409.
- [x] `POST /api/me/identity/declare-lost` + `users.key_lost_at`. Терминальное состояние: `require_live_identity` в `POST /trips` и `POST /deals/match`, публичный `UserOut.key_lost`. **Отклонение:** re-auth по паролю, а не step-up — беспарольные аккаунты получают 409 «нужен T3.15». Подписью ключа тут подтвердить нельзя: отсутствие ключа и есть то, что объявляют.
- [x] **Удалены** `claim`, `import`, `export`. `import` снят сразу (принимал голый npub без доказательства — присвоение чужой личности); `export`/`claim` пережили его на один шаг, потому что семь тест-модулей брали через них известный nsec — снос в одном коммите положил бы весь крипто-сьют.
- [x] `GET /me/keypair/status` — `identity_established` + `key_lost`; старые `key_self_custody`/`has_encrypted_nsec` оставлены, чтобы не ломать читателей.

**Схема (миграции `0029_identity`, `0030_container_key_envelope`):**
- [x] `users.nostr_pubkey` → **UNIQUE**. Дублей на проде нет (проверено 2026-07-26).
- [ ] **NOT NULL — отложен намеренно.** В той же миграции он упал бы: ключей на момент `alembic upgrade` ещё нет, бэкфилл идёт позже, при старте приложения. Отдельной миграцией, когда прод покажет ноль NULL-ов (на 2026-07-27 их уже ноль).
- [x] `users.key_lost_at`, `trips.nostr_published_by_pubkey` (+ бэкфилл атрибуции уже опубликованных).
- [x] `identity_containers.key_envelope` + `key_envelope_sender_pubkey` (миграция `0030`, см. перешифровку).
- [x] **Бэкфилл служебных ключей** — `core/service_keys.py`, идемпотентно, в `lifespan` рядом с `ensure_user_zero`. Не в миграции: генерация требует `NSEC_ENCRYPTION_KEY`, а тащить рантайм-конфиг в историю схемы плохо. На проде выдано 7 + 1 ключей. **Попутно починен живой дефект:** у арбитра ключа не было вовсе, из-за чего threshold 2-of-3 не собирался.

**Публикация рейсов:**
- [x] Только под **`PLATFORM_PUBLISH_NSEC`** — отдельный ключ от `CHAIN_ANCHOR_NSEC`. Авторство события платформенное, `carrier_name` в `content`, `carrier_pubkey: null`; есть тест, что ключ перевозчика **не встречается в событии вообще**. Ключ внесён в whitelist собственного relay.
- [x] `build_event`/`build_deletion_event` (подписывали служебным ключом) **удалены**, а не оставлены рядом: событие, подписанное ключом, который потом уничтожается, живёт на чужих relay'ях приписанным ничьему pubkey.
- [x] Фильтр «интересных» — `core/publish_filter.py`, режимы `interesting`/`all`/`none`, правило «редкий коридор» считается по нашим же `trips`.
- [ ] **Правило «длинных хопов» — не реализовано, но и не заблокировано** (уточнено 2026-07-27). В первой редакции здесь стояло «`origin`/`destination` — свободный текст, нужна схема». **Это было неверно:** `AirportSelect` вызывает `onChange(a.iata)`, то есть в колонках лежат IATA-коды из справочника, а `core/airports.py` с T1.10 имеет и координаты, и haversine. Добавлен `route_distance_km(origin, destination) -> float | None`; правило остаётся дописать в `core/publish_filter.py`.
- [x] При переходе платформенные листинги ставятся в очередь на kind-5 (fire-and-forget: зависший листинг — устаревшая витрина, а не улика, и не должен ронять переход).

**Перешифровка при переходе:**
- [x] `read_packages`/`wrapped_shares` — переупаковка session-ключей на новый npub. **Байты контента не меняются** → `sha256(ciphertext||nonce)` тот же → цепь T3.6 и `verify_content` целы.
- [x] `IdentityContainer` — случайный ключ содержимого + NIP-04-конверт на новый npub (`doc_hash` по plaintext, тройное совпадение `identity_ref` переживает смену шифра).
- [x] **Смена формата конвертов (pt.2c, в постановке отсутствовала).** Пакет читался как ECDH(читатель, **автор сообщения**) — переадресовать его новому владельцу нельзя без приватного ключа автора. Решение: платформа перешифровывает от имени умирающего служебного ключа и записывает отправителя **в сам конверт** (`{ct, sender_pubkey}`, строка = legacy). Затронуты `dealvault`, `threshold`, arbiter-reveal и **клиентская расшифровка** в `DealVaultPage`.
- [x] **Отклонение: inline, а не Celery-таском.** Таск стартует только после коммита, то есть уже без служебного ключа; его падение необратимо — перечитать данные больше нечем. Inline любое исключение откатывает всё. Плюс **самопроверка перед уничтожением ключа**: ECDH симметричен, поэтому платформа вскрывает только что созданный конверт ключом отправителя, доходит до plaintext и сверяет `doc_hash`. Не сошлось → 500 и откат. При росте объёмов правильный ответ — разнести перешифровку и смену ключа на два шага (expand/migrate/contract), а не унести половину в очередь.

**Фронт и копирайт:**
- [x] `lib/identity.ts` — генерация ключа и подпись челленджа в браузере; сервер получает только npub и подпись. Каноническое событие обязано хешироваться побайтово как в `core/identity_proof.py`.
- [x] `KeypairSection` переписан под три состояния; кнопки «забрать сгенерированный» нет вовсе. Ключ показывается один раз, подтверждение заблокировано до чекбокса «сохранил и понимаю, что восстановить нельзя».
- [x] Копирайт: «ключ создаётся в вашем браузере и на наши серверы не уходит» — формулировка «отдаём ключ, который хранили» запрещена как неправда. i18n на все шесть локалей.
- [x] Термин «DID» не введён нигде: везде `npub`.

**Проверка криптографии — три уровня:**
- [x] Контракт сериализации: `frontend/src/test/identity.test.ts` (7) + `backend/tests/test_identity_proof_contract.py` (6), пришпилены к одному литералу. Разъехаться молча не могут.
- [x] Взаимная совместимость BIP-340: Playwright-спек `identity-establish.spec.ts` — `@noble/curves` подписывает в настоящем Chromium, `coincurve` принимает на сервере.
- [x] Поток в UI там же: чекбокс блокирует подтверждение, состояние переключается, аккаунт продолжает работать после перехода.

**Тесты:** `establish` без доказательства → 401 · голый npub → 422 · занятый npub → 409 · повторный → 409 · челлендж одноразовый · просроченный `created_at` → 401 · `claim`/`import`/`export` → 404 · **документ и session key вскрываются ключом, которого сервер не видел** · конверты контрагента не тронуты · несходящаяся самопроверка откатывает переход целиком · перешифровка идемпотентна · рейс до перехода публикуется платформенным ключом, ключ перевозчика в событии отсутствует · бэкфилл идемпотентен, покрывает арбитра, не трогает существующие ключи · `declare-lost` → создание рейса 403.

**Отклонения от постановки:**
- NOT NULL на `nostr_pubkey` отложен до отдельной миграции (бэкфилл в lifespan, а не в миграции — см. выше).
- Перешифровка inline, а не Celery-таском; добавлена самопроверка перед уничтожением ключа.
- Смена формата конвертов (pt.2c) в постановке отсутствовала — без неё аккаунты с e2e-перепиской не смогли бы перейти вовсе.
- Правило «длинных хопов» не реализовано: нужна схема для origin/destination.
- `declare-lost` для беспарольных аккаунтов ждёт step-up из T3.15.
- `export`/`claim` сняты на шаг позже `import` — иначе снос положил бы крипто-сьют.

**Найдено и починено попутно (не входило в задачу):** у арбитра не было keypair, threshold 2-of-3 не собирался · тесты писали и удаляли в **боевой** БД (`SyncSessionLocal` не изолирован) — за один прогон снесло 22 e2e-аккаунта · каскад `cleanup_e2e_users` отстал от схемы (`route_notes.created_by`) и никогда не удалял `Order` · `token_blacklist` под тестами молча не работал.

**Acceptance: ✅ все выполнены** — служебный ключ нигде не подаётся как личность и не публикуется наружу; переход всегда даёт новый ключ с доказательством владения; сейфы переезжают без нарушения цепи и с доказанной читаемостью; `claim`/`import`/`export` не существуют; у всех аккаунтов есть ключ и threshold собирается. **773 backend-теста, 20 vitest, 9 Playwright — зелёные** (полный прогон с fuzz, 2026-07-27).

### T3.13 — Вход и регистрация по Nostr-ключу ✅ MVP

**Контекст.** Механика доказательства владения уже была построена в T3.12 (`core/challenge.py` + `core/identity_proof.py`) и здесь переиспользована целиком — добавились только новые purpose и путь регистрации без пароля.

- [x] `POST /api/auth/nostr/challenge` `{pubkey_hex}` → nonce (Redis `GETDEL`, TTL 300s). Выдаётся **на любой pubkey без проверки**: отказ по неизвестному превратил бы эндпоинт в оракул «у каких ключей есть аккаунты», а челлендж без приватного ключа бесполезен.
- [x] `POST /api/auth/nostr/verify` — гасит челлендж, проверяет подпись, отдаёт JWT.
- [x] Неизвестный pubkey → **404 `nostr_pubkey_unknown`**, не 401: клиенту нужно отличать «не зарегистрирован, предложи регистрацию» от «подпись не сошлась». Аккаунт молча не создаётся — валидная подпись доказывает владение ключом, а не намерение зарегистрироваться.
- [x] `POST /api/auth/nostr/signup` — `password_hash=NULL`, `nsec_encrypted=NULL`, `key_self_custody=True`. **Возвращает токен**, а не только строку: пароля нет, без токена аккаунт был бы недостижим сразу после создания. Email опционален и, если задан, запускает подтверждение из T3.11.
- [x] Утраченная личность (`key_lost_at`, T3.12) войти не может → 403.
- [x] Rate-limit `10/minute` на оба эндпоинта: slowapi + зона `nostr_auth_zone` в nginx.
- [x] Frontend: `NostrAuthButton` на обеих страницах, подпись делает NIP-07-расширение. Расширения нет → объяснение, что это такое и что Vimana ключ не видит, а не пустая ошибка. i18n ×6.

**Отклонение от постановки — три purpose вместо URL-привязки.** Строгий NIP-98 биндит доказательство к абсолютному URL, что тащит origin из деплой-конфига в проверку подписи и ломается, как только dev и prod различаются. Вместо этого purpose (`establish` / `login` / `signup`) лежит **внутри подписанного события**: подпись, собранная для одного потока, бесполезна в другом. Тесты проверяют обе стороны — proof логина не создаёт аккаунт, proof establish не пускает войти.

**Тесты (15, `tests/test_nostr_auth.py`):** вход по ключу · чужая подпись → 401 · повторное использование челленджа → 401 · просроченный `created_at` → 401 · неизвестный pubkey → 404 · signup создаёт self-custody-аккаунт без пароля и email · токен из signup работает сразу · занятый ключ → 409 · signup с email заводит код подтверждения · утраченная личность → 403 · парольный вход не затронут.

**Не покрыто автотестами:** Playwright-спек на вход по ключу. Нужно настоящее NIP-07-расширение, а по T_TEST.3 это только persistent context с инъекцией — отдельная работа, не довесок.

**Acceptance: ✅ все выполнены** — владелец ключа входит без пароля и без email; перехваченный подписанный запрос повторно не проходит; аккаунт без пароля полностью работоспособен. **799 backend-тестов зелёные** (полный прогон с fuzz, 2026-07-27). Прирост против 773 — 15 новых юнит-тестов плюс ~11 schemathesis-кейсов, сгенерированных на три новых эндпоинта: контракт по ним отработал, ради чего полный прогон и был блокирующим.

### T3.14 — Passkeys (WebAuthn): несколько устройств на одну личность

- [ ] Зависимости: backend `webauthn==2.5.2` (py_webauthn), frontend `@simplewebauthn/browser@^13`.
- [ ] Env (ENVIRONMENT §секреты + `.env.example`): `WEBAUTHN_RP_ID` (prod `vimana.dealvault.club` — см. `nginx/default.conf:29`; dev `localhost`), `WEBAUTHN_RP_NAME=Vimana`, `WEBAUTHN_ORIGIN`. RP ID **обязан** совпадать с доменом — иначе браузер отклоняет ceremony молча, без внятной ошибки.
- [ ] Миграция `0030_webauthn_credentials`: `webauthn_credentials(id UUID PK, user_id FK→users ON DELETE CASCADE, credential_id BYTEA UNIQUE NOT NULL, public_key BYTEA NOT NULL, sign_count BIGINT NOT NULL DEFAULT 0, transports JSONB, aaguid VARCHAR(36), device_name VARCHAR(100), backed_up BOOL NOT NULL DEFAULT false, uv_capable BOOL, created_at, last_used_at)` + index по `user_id`.
- [ ] Ceremony-эндпоинты (challenge в Redis, TTL 300s, одноразовый):
  - `POST /api/auth/passkey/register/options` (авторизован) → `residentKey="required"`, `userVerification="preferred"`, `user.id` = байты UUID, `excludeCredentials` = уже привязанные.
  - `POST /api/auth/passkey/register/verify` → сохраняет credential; `device_name` — из ввода юзера, дефолт по User-Agent.
  - `POST /api/auth/passkey/login/options` (без авторизации) → **пустой** `allowCredentials` — usernameless-вход через discoverable credentials.
  - `POST /api/auth/passkey/login/verify` → юзер по `credential_id`, проверка подписи и `sign_count` → JWT.
  - `POST /api/auth/passkey/signup/options` + `/verify` — регистрация с нуля: `display_name` обязателен, email опционален; создаёт юзера с `password_hash=NULL` и генерирует **кастодиальный** Nostr-keypair (как в `register`) — npub становится его личностью, платформа держит nsec до `claim`.
  - `DELETE /api/auth/passkey/{id}` — отвязать устройство.
- [ ] **Sign-count:** отклонять регресс (`new <= stored`) только если `stored > 0`. Синхронизируемые passkey'и (iCloud, Google) всегда отдают 0 — жёсткая проверка выбросит нормальных пользователей.
- [ ] **Guard последнего аутентификатора:** удаление passkey → 409, если после него у юзера не остаётся ни одного способа входа (`password_hash IS NULL` **и** `key_self_custody = false` **и** это последний credential). Иначе пользователь запирает сам себя без возможности восстановления (email опционален — почтового пути назад может не быть).
- [ ] YubiKey распознаётся по `backed_up=false` + `transports ∩ {usb, nfc}` → в UI помечается как «аппаратный ключ». Отдельного кода не требует: это тот же WebAuthn-путь.
- [ ] Frontend: кнопки на LoginPage/RegisterPage; секция «Устройства входа» в `ProfilePage.tsx` (список, дата последнего входа, отвязка); `PublicKeyCredential.isConditionalMediationAvailable()` → autofill-подсказка в поле email.

**Тесты** (py_webauthn допускает фикстурные ceremony-ответы): регистрация credential · вход по нему · чужой `credential_id` → 401 · регресс sign_count → 401 · `sign_count=0` не отклоняется · повтор challenge → 401 · удаление последнего аутентификатора → 409 · удаление при наличии пароля → 204 · **два устройства на один npub дают один и тот же аккаунт**.

**Acceptance:** одна личность — несколько passkey'ев; вход с любого привязанного устройства даёт тот же аккаунт; отвязка устройства не меняет npub и не трогает остальные способы входа; последний способ входа удалить нельзя.

### T3.15 — Step-up re-auth + управление способами входа

**Контекст.** Сейчас чувствительные операции защищены паролем: `POST /api/keypair/export` принимает `password` и сверяет его через `verify_password` (`app/api/keypair.py`). С появлением аккаунтов без пароля (T3.13/T3.14) эта проверка перестаёт работать — нужен единый механизм повторной аутентификации, не зависящий от способа входа.

- [ ] `app/core/step_up.py` · `require_step_up(user, proof)` — принимает один из трёх пруфов: пароль · свежая WebAuthn-assertion с `userVerification=true` · NIP-98-подпись. Выдаёт step-up-токен в Redis, TTL 5 минут, привязанный к `user_id` **и типу операции**.
- [ ] Под step-up: экспорт nsec, claim self-custody, отвязка passkey, смена/добавление email, добавление нового способа входа.
- [ ] `POST /api/keypair/export` переводится с `password: str` на step-up-токен. Ветка «у юзера нет пароля» перестаёт быть необработанной дырой.
- [ ] `ProfilePage.tsx` — секция «Безопасность»: способы входа (email/пароль · Nostr-подпись · passkey'и), npub с копированием, добавление и удаление методов. Личность (npub) и способы входа разведены визуально — это разные вещи, пользователь не должен считать passkey «своим ключом».

**Тесты:** step-up паролем · passkey'ем · Nostr-подписью · истёкший токен → 401 · токен от другой операции → 403 · экспорт nsec без step-up → 401 · аккаунт без пароля успешно экспортирует nsec через passkey.

**Acceptance:** любая чувствительная операция требует свежего подтверждения — каким бы способом пользователь ни вошёл; аккаунт без пароля не ограничен по сравнению с парольным.

### T3.16 — Recovery-коды: запасной вход, не запасная личность

**Контекст.** Решение владельца №7 задаёт точную границу: **код возвращает доступ к аккаунту, но никогда не возвращает ключ.** Отсюда три разных исхода, и их нельзя смешивать в UI — иначе пользователь решит, что бумажка страхует его от всего:

| Что случилось | Что даёт recovery-код |
|---|---|
| Потеряно устройство, аккаунт **без ключа** (до перехода) | всё: аккаунт и переписку. Терять нечего — сейфы на ключе платформы |
| Потеряно устройство, ключ self-custody цел | аккаунт и переписку. npub тот же — ключ у пользователя, ничего не утрачено |
| **Утрачен сам ключ (self-custody)** | **ничего восстановить нельзя.** Личности больше нет: старая переписка не расшифровывается никем, история и УБА не переезжают. Путь один — `declare-lost` (T3.12) и новая личность |

- [ ] Миграция `0031_recovery_codes`: `recovery_codes(id UUID PK, user_id FK→users ON DELETE CASCADE, code_hash VARCHAR(255) NOT NULL, used_at TIMESTAMPTZ NULL, created_at)` + index по `user_id`. Хранятся **только хеши** (`core.security.hash_password`) — платформа не может ни показать коды повторно, ни воспользоваться ими сама.
- [ ] Генерация: 10 кодов по 12 символов из безопасного алфавита (без `0/O/1/l/I`), `secrets.choice`. Показываются **один раз** при создании аккаунта без email (T3.13, T3.14) — экран «сохраните, второй раз не покажем», кнопки «Скачать .txt» и «Скопировать». Расчёт на бумагу: шрифт `IBM Plex Mono` (DESIGNGUIDELINES), группировка по 4 символа, печатная раскладка.
- [ ] `POST /api/auth/recovery/consume` `{npub, code}` → одноразовый JWT с **ограниченной областью**: даёт право только привязать новый способ входа (passkey / пароль / email). Обычные операции им недоступны — украденный код не должен становиться полноценным входом. Код помечается `used_at`; повторное использование → 401.
- [ ] `POST /api/auth/recovery/regenerate` — под step-up (T3.15). Инвалидирует все прежние коды одной транзакцией.
- [ ] Rate-limit жёсткий: `5/hour` на `consume` по IP + `10/day` по npub (slowapi + nginx). Брутфорс 12-символьного кода бессмыслен, но это дешёвая защита от перебора npub'ов.
- [ ] `MeOut.recovery_codes_remaining: int` — для баннера «осталось 2 кода».
- [ ] Коды **не инвалидируются** при переходе в self-custody — вход они восстанавливают по-прежнему. Но текст рядом с ними обязан смениться: до перехода — «вернёт аккаунт и всю переписку», после — «вернёт только доступ, ключ теперь только у вас». Одинаковая формулировка в обоих состояниях = обещание, которого платформа не выполнит.
- [ ] Письмо и in-app уведомление после использования кода: «в аккаунт вошли по коду восстановления» — с указанием, сколько кодов осталось.

**Тесты:** генерация 10 уникальных кодов · валидный код → scoped-токен · scoped-токен не проходит на обычных эндпоинтах (403) · повторное использование → 401 · чужой код → 401 · `regenerate` инвалидирует прежние · rate-limit на `consume` · аккаунт с подтверждённым email кодов при регистрации не получает · кастодиальный аккаунт после `consume` читает старую переписку · self-custody после `consume` сохраняет тот же npub.

**Acceptance:** пользователь, потерявший единственное устройство, восстанавливает доступ к тому же npub по коду и привязывает новый аутентификатор; использованный код не работает повторно; платформа не хранит коды в открытом виде; UI нигде не обещает восстановление утраченного ключа.

> **Social recovery — отложено осознанно.** Восстановление через guardians из Trust Graph (T2.4) не требует от пользователя ничего хранить, но упирается в нерешённые вопросы: выбор порога, сговор guardians, пересечение с арбитражем. Отдельно: под решением №4 social recovery всё равно **не вернёт ключ** — guardians могут подтвердить личность человека, но не воссоздать его nsec. Механика shamir-долей есть (`shamir-secret-sharing` на фронте + `app/core/threshold.py`, T2.3) — при возврате к задаче переиспользуется. Отдельная задача, не child T3.16.

### T3.17 — Необратимость: экран последствий + напоминания о восстановлении

**Контекст.** Решения №4 и №8 вместе означают: платформа не мешает пользователю уйти в self-custody, но обязана убедиться, что он понимает цену. Момент риска **не наступает при регистрации** — у аккаунта до перехода нет собственного ключа и терять нечего. Значит напоминания привязываются к событиям, а не к таймеру: спам с первого дня научит игнорировать баннер ровно к тому моменту, когда он станет важен.

`PlatformNotice` для этого не подходит — он глобальный и админский, с поверхностями footer/trip_card/deal_page (`app/models/notices.py`). Персональное состояние выводится из полей `MeOut`, новой таблицы не требует.

**Три триггера, все событийные:**
- [ ] **Регистрация** — молчим. Ни баннера, ни письма. Риска нет.
- [ ] **Первая сделка или первый рейс** у аккаунта без email — мягкий закрываемый баннер «добавьте почту для восстановления доступа». Закрытие запоминается локально, повторно не всплывает.
- [ ] **Establish identity** — экран-развилка (решение №6) с обязательным чекбоксом перед обеими ветками; сам переход не блокируется (решение №8):
  - **Создать ключ** — генерация в браузере через `@noble/curves`, на сервер уходит только npub и подпись челленджа.
  - **Использовать свой** — ключ из NIP-07-расширения, тот же челлендж, та же подпись. Для сервера ветки неразличимы.
  
  **Копирайт (смысл обязателен, формулировка может шлифоваться):**
  > **Свой ключ — своя личность.**
  > Ключ создаётся прямо в вашем браузере и никогда не уходит на наши серверы. У нас его нет и не будет — ни копии, ни отпечатка. С этого момента сейфы ваших сделок шифруются им, и открыть их можете только вы.
  >
  > До сих пор сейф шифровался служебным ключом платформы. Сейчас его содержимое перешифровывается на ваш ключ, а служебный уничтожается.
  >
  > Обратного пути нет. Если ключ потерян — ни мы, ни кто-либо другой не сможем его восстановить, а вместе с ним будут потеряны переписка и вложения ваших сделок. Коды восстановления вернут вход в аккаунт, но не ключ.

  Чекбокс — не «я согласен с условиями», а «я понимаю, что платформа не сможет восстановить мой ключ». Формулировка «мы отдаём вам ключ, который хранили» **запрещена** — она была бы неправдой (T3.12).
- [ ] **Где предлагается переход** (решение владельца: не «страшный шаг», а открывающаяся возможность): пользователь хочет использовать собственный Nostr-ключ; хочет выгрузить сейф сделки (.dvlt, Фаза 6); хочет публиковать рейсы под своим именем в сети. Предложение появляется в момент такого намерения, а не висит постоянным баннером.
- [ ] Экран прогресса перешифровки сейфов (Celery-таск может идти минуты на активном аккаунте) — с явным «не закрывайте вкладку до конца» и корректным поведением, если закрыли: таск возобновляемый, статус читается при следующем входе.

**Дополнительно:**
- [ ] Баннер «осталось N кодов восстановления» при N ≤ 2, ведёт на регенерацию.
- [ ] Письмо после `claim` (если email есть) — фиксация факта и напоминание, где лежат коды.
- [ ] Чип «ключ утрачен» в профиле и на карточках для аккаунтов с `key_lost_at` (T3.12) — контрагент видит мёртвую личность до того, как предложит ей сделку.
- [ ] i18n EN/RU/UA. Тон — DESIGNGUIDELINES §9: предупреждение без запугивания, без `danger`-красного (он зарезервирован, см. Bento-скилл).

**Тесты:** экран последствий не пропускает `claim` без чекбокса (frontend, vitest) · баннер без email появляется после первой сделки и не появляется до · счётчик кодов ≤ 2 включает баннер · `key_lost` рисует чип в публичном профиле · письмо после `claim` уходит только при наличии email (SMTP замокан).

**Acceptance:** пользователь не может уйти в self-custody, не увидев полного списка последствий; аккаунт без email получает напоминание ровно тогда, когда ему есть что терять; мёртвая личность видна контрагенту.

---

### T3.18 — Публичная страница личности

**Контекст.** Публичного представления пользователя в проекте нет вообще: эндпоинта `GET /api/users/{id}` не существует, есть только частные срезы (`/users/{id}/uba`, `/users/{id}/trust-metrics`, `/users/{id}/verifications`). Контрагент не может посмотреть, с кем имеет дело, одной ссылкой — и нечем поделиться.

Нужна и сама по себе, и как фундамент под T3.19: архив завершённых личностей — это та же страница с датой конца.

- [ ] `GET /api/identities/{npub}` — по **npub**, не по внутреннему `user.id`. Личность и есть ключ (решение №4), а внутренний идентификатор — деталь реализации, которой незачем быть в публичной ссылке.
- [ ] Состав: `display_name`, аватар, дата первой активности, УБА + уровень, `highest_verification_level`, счётчики trust (`verifications_issued/received_count`, `dealt_with_count`), число закрытых сделок, `key_lost_at` (если есть). Всё это **уже публично** в `UserOut` — новизна в том, что оно собрано в одном месте и адресуемо.
- [ ] **Никогда:** email, phone, `receiving_*`, содержимое сейфов.
- [ ] **Обход графа — только по `peer_verified`** (решение владельца 2026-07-27). Три вида рёбер из T2.4 — три разных ответа:
  - `peer_verified` **публично по природе**: поручительство, которого никто не видит, не имеет веса. Без прослеживаемой цепочки бейдж превращается в утверждение платформы, а не сети. Плюс семантика верна — это публичное высказывание *о человеке*.
  - `dealt_with` — **нет**. Список клиентов перевозчика и маршрутов отправителя, коммерческая тайна. Сделка — частная транзакция двоих.
  - `invited` — **нет**. Социальный граф, кто кого привёл.
  
  Счётчики (`dealt_with_count` и прочие) остаются публичными как сейчас: число — не то же самое, что имена.
- [ ] Настройки видимости в профиле: `public_profile ∈ {full, minimal, hidden}`. `minimal` — только факт существования и уровень верификации; `hidden` — 404 для всех, кроме владельца. Дефолт `full`.
- [ ] **Видимость обязана распространяться на уже существующие метрики** — `GET /users/{id}/uba` и `GET /users/{id}/trust-metrics` отдают данные любому авторизованному и о новой настройке ничего не знают. Если их не тронуть, `hidden` будет прятать страницу, но не цифры на ней: закрылся от посторонних, а УБА и счётчики доверия по-прежнему читаются прямым запросом. Настройку применять в одном месте (общая проверка), а не копировать условие по эндпоинтам — иначе следующий публичный срез снова про неё забудет.
- [ ] Тест на каждый уровень видимости **против всех** публичных срезов сразу, а не только против страницы личности.
- [ ] **Скрытая личность в графе не исчезает, а обезличивается:** узел рисуется как «личность, скрытая владельцем», без имени и без ссылки, а её поручительство **продолжает считаться** в пользу того, за кого ручались. Скрыть можно себя, но не свой вклад в чужую репутацию — он уже не только твой.
- [ ] Фронт: `/i/{npub}`, доступна без авторизации. Чип «ключ утрачен» для завершённых. Переход к завершённой личности возможен **прогулкой по поручительствам** от живых участников — архив вплетён в сеть, а не стоит отдельным зданием.
- [ ] Каждое доказательство на странице показывается **с датой** — см. `T_TRUST.1`.

**Acceptance:** любую личность можно открыть по ссылке с её npub; приватные поля не утекают ни при каком значении видимости; `hidden` действительно скрывает.

### T3.19 — Архив завершённых личностей

**Контекст (решение владельца 2026-07-27).** Завершение личности — не смерть аккаунта, а **смена жанра**: из участника сети он становится историческим документом. Способность действовать и достоверность прошлых действий у нас впервые независимы — потеря ключа отнимает первое и не трогает второе.

> **Identity retired. Evidence lives on.**

Слово **Archive**, не Cemetery: кладбище — место утраты, архив — место сохранения, и второе есть буквально DealVault. Метафора — музей авиации: под выведенным из эксплуатации бортом пишут часы налёта, и это уважение, а не позор.

**UI завершённой личности — смена режима, а не урезанный профиль:**
- [ ] Модалка **один раз**, при первом входе после утраты: что произошло, что осталось, что теперь. Постоянная модалка на необратимое состояние — нытьё, её закрывают не читая.
- [ ] Дальше — постоянный баннер (состояние не меняется, значит видно всегда) и профиль в виде архивной карточки: период работы, публичная запись, недоступный сейф, историческая активность, дата последней подписи.
- [ ] Кнопки действий **прячутся**, а не отдают 403 по клику.
- [ ] Никакого «удалить аккаунт»: запись остаётся, потому что она наполовину чужая.

**Окно 15 дней — точная механика (решение владельца 2026-07-27):**
- [ ] Отсчёт от `key_lost_at`. **Бездействие → экспонат становится видимым** по истечении срока. Никаких подтверждений не требуется: дефолт — сохранение, как во всём продукте.
- [ ] Владелец может войти и выбрать **«Нет»** — тогда страница закрывается **навсегда**, и это решение не отменяется.
- [ ] **Асимметрия намеренная:** ошибочное «Нет» ведёт к приватности, ошибочное бездействие — к публичности, но с 15 днями на исправление. Необратима только безопасная сторона.
- [ ] **Ничего не удаляется ни в одном случае.** Закрывается витрина: страница, `display_name`, участие в агрегатах. Остаются цепь, подписи, события сделок — по ENVIRONMENT §8.2 это критические данные, и они наполовину принадлежат контрагенту. Слово «кремация» в UI **не использовать**: оно обещает уничтожение, которого не происходит.
- [ ] Скрытая личность остаётся в графе обезличенным узлом, её поручительства продолжают работать (T3.18).
- [ ] **Чтобы выбрать, надо войти.** Завершённый аккаунт войти может — для того `declare-lost` и сохраняет доступ. Но если утрачен и ключ, и доступ, человек выбора не увидит и сработает дефолт. Это честно и следует из «бездействие → видимо», но должно быть сказано вслух в модалке и в письме.
- [ ] Уведомление об окне: разовая модалка при первом входе + письмо (когда заработает доставка). Оба говорят дату, после которой выбор зафиксируется.

**Агрегаты — только настоящие числа:**
- [ ] Что есть сразу: число завершённых личностей, сделок и закрытых сделок, рёбра доверия, УБА на момент заморозки, длина цепи, первая и последняя подписи.
- [ ] Километры — через `core.airports.route_distance_km` (IATA → координаты → haversine). Килограммы — из `Trip.capacity`. Оба доступны сразу, миграций и внешних сервисов не требуют.
- [ ] **Формулировка обязана быть «по прямой».** Haversine даёт дугу большого круга; реальный трек длиннее на 3–7% из-за коридоров и ветра. И главное — мы меряем **маршрут доставки**, а не налёт самолёта: перевозчик с двумя пересадками — это по-прежнему один хоп. Писать «пройдено километров» нельзя, это другое число и другой вопрос.
- [ ] «Хвосты»: самый длинный хоп, самые редкие коридоры, самые сложные цепочки. Это и есть интересное в музее — не средние, а рекорды.
- [ ] Метрик, которых нет, не изобретать. Точность вида «99.98%» создаёт впечатление измеренного; писать только то, что посчитано.

**Тон и границы утверждений:**
- [ ] «Verified forever» **не писать.** Цепь tamper-evident, не tamper-proof. Правильная формулировка — «проверяемо независимо по состоянию на <дата последнего якоря>» и зависит от `T3.20`. Ровно на этом уже споткнулись лендинги v5 (T3.10, расхождение по тону до сих пор открыто) — повторять нельзя.
- [ ] Поручительства завершённой личности **остаются в силе**: бейдж выдан, когда ключ был жив, подпись проверяется до сих пор. Это самая сильная форма идеи — не «был да сплыл», а «перестал действовать, но его слово держит».

**Осознанное следствие решения №4:** экспонаты в архиве **несвязанные**. Ссылки «эта личность продолжает ту» не будет — преемственности мы отказали намеренно. Династии = отмена решения №4, не фича архива.

**Acceptance:** вошедший в завершённый аккаунт понимает, что произошло и что делать, без чтения документации; страница читается как исторический документ, а не как сломанный профиль; ни одно утверждение на ней не сильнее того, что механизм действительно доказывает.

### T3.20 — Включить якоря цепи

**Контекст.** `core/chain_anchor.py` написан в T3.6 и **ни разу не работал**: публикация выключена (`NOSTR_PUBLISH_ENABLED=false`), `CHAIN_ANCHOR_NSEC` не задан. А до 2026-07-27 не работал бы в любом случае — воркер шёл с пустым реестром задач.

Без якорей цепь доказывает целостность против того, у кого есть доступ к БД, но **не против самой платформы**: `seq` присваиваем мы. С якорями head, опубликованный на relay'ях, которыми мы не владеем, фиксирует всё под собой чужим временем.

- [ ] Сгенерировать `CHAIN_ANCHOR_NSEC` (отдельный от `PLATFORM_PUBLISH_NSEC` и пользовательских — T3.6 D-решение), задать `NOSTR_FRIENDLY_RELAYS`, включить публикацию.
- [ ] Проверить, что hourly-таск реально отрабатывает и `DealChainAnchor` пишется только при ≥1 принявшем relay.
- [ ] Отдавать дату и relay'и последнего якоря в API — это то, что показывает T3.19 вместо слогана.
- [ ] **Граница утверждения:** якоря фиксируют историю до последнего якоря. Написанное после — ещё нет. Везде дата, нигде «навсегда».

**Acceptance:** head'ы публикуются на сторонние relay'и; любой может проверить состояние цепи на дату независимо от нас; формулировки в продукте не сильнее этого.

### T_TRUST.1 — Свежесть доказательств (сквозная)

**Контекст (решение владельца 2026-07-27).** Все доказательства устаревают. Верификация вчера — сильная, неделю назад — сильная, месяц — нормальная, год — под вопросом, пять лет — много воды утекло. Сейчас продукт этого не отражает: бейдж либо есть, либо нет.

Это уровень корня, а не отдельного экрана: касается T2.1 (бейджи), T2.4 (Trust Graph), T3.1 (УБА) и любого места, где показывается «проверен».

- [ ] **Дата у каждого доказательства, везде.** Данные в основном есть: `VerificationBadge.verified_at` и `expires_at`, `TrustEdge.created_at`, `DealEvent.timestamp`. Не хватает не полей, а их показа.
- [ ] Никогда не показывать «проверен» без «когда». Голый бейдж без даты — утверждение сильнее фактического.
- [ ] Функция затухания в УБА: `V_verify_factor` уже есть, добавить множитель по возрасту доказательства.
- [ ] Взвешивание рёбер Trust Graph по свежести в BFS.
- [ ] Решить и записать шкалу: до какого возраста доказательство считается полным, где начинается спад, есть ли пол.
- [ ] Заголовок в Decision Log — `D-EVIDENCE-DECAYS`.

**Acceptance:** ни в одном месте продукта доказательство не показывается без своей даты; возраст влияет на УБА и на вес рёбер доверия; шкала зафиксирована в PRD, а не разбросана по коду.

### Открытые зависимости фазы

- ~~**Структурные origin/destination**~~ — **снято 2026-07-27, зависимости не было.** Я записал её по догадке, не проверив, что кладёт форма: `AirportSelect` отдаёт IATA-код, а `core/airports.py` с T1.10 держит координаты и haversine. Расстояние считается сегодня (`route_distance_km`), обе «заблокированные» фичи разблокированы. Урок общий: ограничение, попавшее в PRD без проверки кода, живёт как факт и тормозит работу.
- **Реальный налёт вместо прямой — сознательно не делаем.** Внешний сервис (FlightAware/AviationStack/OpenSky) даёт +3–7% точности ценой ключа, лимитов, денег и новой точки отказа, а для **будущего** рейса трека не существует вовсе — он появляется после вылета. Плюс отвечает не на наш вопрос: мы меряем маршрут доставки, а не мили самолёта. Проект уже отказывался от внешних API в пользу локального стека (T2.1, KYC). Если понадобится — отдельная задача с явной ценой.

---

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

**Follow-up:** (1) `/health` можно ужесточить — вернуть 200 без тела (не выдавать версию). (2) Мониторинг rate-limit hits — счётчик отказов nginx в metrics.

### T_SEC.2 — Vite dev → static production build ✅ MVP

**Контекст.** До T_SEC.2 frontend-контейнер запускал `npm run dev` (Vite dev-server с HMR) как prod: (a) `unsafe-inline` + `unsafe-eval` в script-src CSP, (b) React StrictMode двойным mount'ом дёргал useEffect (реально ловилось на invite-flow → fix через backend idempotency), (c) source-код + node_modules в prod-контейнере, (d) без бандлинга/минификации.

**Изменения:**

- [x] `frontend/Dockerfile` — multi-stage: `node:22-alpine` builder → `nginx:1.27-alpine` server. Stage 1: `npm ci` + `npm run build` → `dist/`. Stage 2: копирует `dist` в `/usr/share/nginx/html`, кладёт `nginx.conf` для SPA `try_files $uri /index.html`.
- [x] `frontend/nginx.conf` — internal nginx контейнера: `/assets/` c 1y immutable cache, SPA fallback, `/health` возвращает `ok`.
- [x] `docker-compose.dev.yml` frontend — убран volume-mount (`./frontend:/app`), healthcheck переведён на `http://localhost/health` (:80 внутри).
- [x] `nginx/default.conf` — main-nginx proxy_pass `frontend:5173` → `frontend:80`, убраны websocket-upgrade headers (Vite HMR больше нет).
- [x] **CSP tightened**: `script-src 'self'` (было `'self' 'unsafe-inline' 'unsafe-eval'`). style-src остаётся с `unsafe-inline` — Tailwind + libs всё ещё пишут inline `<style>`. Полный nonce/hash pass — future.
- [x] `AcceptInvitePage` — убран `attemptedRef` guard: StrictMode-double-effect больше не может произойти (dev-only behavior), backend + так idempotent per user.

**Acceptance:**
1. Prod-build: `docker compose up -d --build frontend` — контейнер стартует, healthcheck зелёный за <30s.
2. `curl -sI https://vimana.dealvault.club/` — CSP header **без** `unsafe-eval`, **без** `unsafe-inline` в script-src.
3. `/assets/index-<hash>.js` — cache-control `public, immutable, max-age=31536000`.
4. Прямой navigate на `/deals/xxx` в новой вкладке — nginx SPA fallback → index.html → React Router → правильная страница.
5. Bundle size: `dist/assets/*.js` < 500KB gzip'ed (Vite tree-shaking).

**Follow-up:**
1. Nonce/hash-based CSP полный strict — генерация nonce в nginx per-request + injecting в HTML (нужен custom Vite plugin).
2. Self-hosted fonts — снять `fonts.googleapis.com` / `fonts.gstatic.com` из CSP.
3. Backfill Playwright `T_TEST.3 pt.2` через prod-build — сейчас тесты гоняются против prod, вопрос: производительность и стабильность после T_SEC.2.

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

**pt.3 — Full E2E business flows (14 спеков, план 2026-07-25):**

Текущие 7 спеков — smoke (регистрация, рендер, guard'ы, multi-tab). pt.3 покрывает бизнес-флоу сквозняком через UI. Приёмы: multi-context (sender/carrier/arbiter в одном тесте), `setInputFiles` (upload из байтов), download-перехват + SHA-256 сверка, `page.request` (UI+API микс), `page.route` (сетевые сбои), `addInitScript` c фейковым `window.nostr` (self-custody без расширения — headless не грузит extensions).

**P0 — ядро сделки (реализовать первым пакетом, после T3.8):**
- [ ] 1. `deal-lifecycle.spec.ts` — carrier: рейс → sender: match → accept → handoff → received → confirm; статусы у обоих; после закрытия vault запечатан (ввод недоступен / «sealed»-ошибка). UI-покрытие T3.7.
- [ ] 2. `chat-two-users.spec.ts` — sender пишет → carrier видит; system-messages рендерятся.
- [ ] 3. `chat-file-upload.spec.ts` — PNG через `setInputFiles` → превью в чате, lightbox, файл виден второй стороне.
- [ ] 4. `dirty-file-rejected.spec.ts` — MZ-байты как `photo.jpg` → человекочитаемая ошибка, файла в чате нет. UI-покрытие T3.8.
- [ ] 5. `download-verify-hash.spec.ts` — скачать вложение → SHA-256 скачанного == `file_hash` из API == hash в `/chain`. Демо верифицируемости DealVault.

**P1 — доверие и споры:**
- [ ] 6. `verification-flow.spec.ts` — carrier запрашивает документы → sender грузит PNG-паспорт → badge в профиле.
- [ ] 7. `declined-polite.spec.ts` — перевозчик вежливо отклоняет → нейтральный баннер у отправителя, без штрафов.
- [ ] 8. `dispute-reseal.spec.ts` (3 контекста) — dispute после закрытия → чат распечатан → evidence-фото → arbiter claim + resolve(closes_deal) → снова sealed. UI-покрытие D-SEAL-SEMANTICS.
- [ ] 9. `share-address.spec.ts` — picker адреса → 📍-сообщение в чате.
- [ ] 10. `chain-verify.spec.ts` — после сделки `page.request GET /chain`: ok=true, coverage полный, sealed_at установлен. UI-badge — после follow-up 2 из T3.6.

**P2 — платформа:**
- [ ] 11. `mobile-viewport.spec.ts` — `devices['iPhone 14']`: Bento 1 колонка, BottomNav, тач-зоны.
- [ ] 12. `i18n-switch.spec.ts` — RU↔EN, сохранение выбора после reload.
- [ ] 13. `network-chaos.spec.ts` — `page.route` abort `/api/deals/*` → нет белого экрана, есть сообщение об ошибке.
- [ ] 14. `fake-nip07-e2e.spec.ts` — инъекция `window.nostr` → self-custody E2E сообщение шифруется/расшифровывается в браузере.

Ограничения (зафиксировано): email-флоу не проверяем (нет ящика); реальное NIP-07-расширение — только persistent context (обходим инъекцией); a11y/visual regression — не здесь (T_TEST.8/T_TEST.9).

**Acceptance pt.3:** P0-пакет (5 спеков) зелёный против prod ≤ 3 мин; P1/P2 — по мере, каждый спек самоочищается через `@e2e.vimana.local` convention.

### T_AGENT.1 — Агентский интерфейс: Nostr publish + MCP server ✅ pt.1 + pt.2 MVP

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

**pt.2 — auth + rate-limit + search + metrics ✅**

- [x] `MCP_API_KEY` env — если задан, каждый tool call должен содержать matching `api_key` arg → 401-эквивалент. Если пустой — dev mode, всё пропускается (backwards compat).
- [x] Rate-limit `MCP_RATE_LIMIT` (default 60) calls/минуту per key через sliding-window deque. `_anon` bucket для unauthed режима.
- [x] `search_trips(query, limit?)` — client-side substring search по origin/destination/carrier_name/categories. Полнотекстовый через Nostr subscribe backfeed — pt.3 (нужен NOSTR_PUBLISH_ENABLED + relay subscription).
- [x] `get_mcp_metrics()` tool — in-process per-tool counters + rejection reasons (auth / rate_limit). Persistence и Prometheus scrape — pt.3.
- [x] README обновлён — секции Auth, Rate limit, Metrics + pt.3 roadmap.

**pt.3 — deferred:**

- [ ] Nostr subscribe backfeed для реального full-text search.
- [ ] Метрики persistence (Postgres или Prometheus scrape endpoint).
- [ ] Per-user MCP tokens tied to Vimana accounts («my trips only»).
- [ ] SSE transport (сейчас stdio-only, ограничено локальным subprocess'ом).
- [ ] Backend-тесты через subprocess-запуск MCP + fake stdio.

**Acceptance MVP ✅:** `docker compose --profile mcp up -d mcp-server` стартует контейнер. При подключении в Claude Desktop через stdio → `list_tools` возвращает 2 tools + описания; `call_tool('list_trips', {origin: 'SVO'})` возвращает форматированный список активных рейсов.

### T2.1 pt.3 — decline_polite sender copy ✅ MVP

*(child T2.1; см. также T_UX.1 где UI компонент)*

- [x] Backend: `declined_polite` отдаётся как есть — `VerificationRequestStatus` это `str`-enum, JSON = `"declined_polite"`. `VerificationRequestOut.status` / `.target_role` типизированы enum'ами вместо голого `str`, чтобы OpenAPI объявлял допустимые значения (зеркало TS-юнионов `RequestStatus` / `TargetRole`). JSON-вывод не изменился.
- [x] `GET /deals/{id}/verification-requests` — источник баннера — покрыт 5 тестами (был без покрытия): точный предикат баннера (`status=declined_polite` + `target_role=carrier` + `resolved_at`), видимость обоими участниками, порядок newest-first, outsider → 403, несуществующая сделка → 404.
- [x] Frontend UI-компонент — сделан в T_UX.1 (`VerificationDeclineBanner.tsx`, рендер под `isSender && carrierPoliteDecline` в `DealPage.tsx`).

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

### T_UX.3 — Auth rehydrate on reload + inactivity logout ✅ MVP pt.1 + pt.2 + pt.3

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

**pt.3 — Multi-tab sync ✅**

- [x] `storage` event listener в `<AuthBootstrap>`: другая вкладка сделала `localStorage.removeItem('token')` → эта вкладка вызывает `logout('multi_tab')` → silent redirect на `/login` (без `?reason=` баннера — пользователь сам логаутнулся где-то ещё).
- [x] Симметрия для login: если в другой вкладке появился `token` (было anonymous) → синхронизируем `useAuthStore.setState({ token })` + `hydrate()` → эта вкладка становится authenticated.
- [x] `logout` reason расширен: `'inactivity' | 'manual' | 'multi_tab'`. multi_tab делает silent redirect (без URL param'ов).
- [x] Playwright regression `frontend/e2e/specs/multi-tab-logout.spec.ts` — открывает 2 page в одном browser context, register в tab A, hard-nav /profile в tab B, `evaluate(localStorage.removeItem('token'))` в tab A → tab B редиректит на /login без `reason=`.

**Backend поддержка (pt.4a — Option B) ✅**

- [x] `create_access_token` теперь кладёт `jti` (random UUID) в JWT payload.
- [x] `decode_access_token` возвращает **весь payload dict** (было: только sub).
- [x] `app/core/token_blacklist.py` — async Redis client (`redis>=5.0`), `blacklist_jti(jti, ttl)` + `is_blacklisted(jti)`. Ключ `auth:blacklist:<jti>` с TTL = remaining JWT lifetime → авто-очистка после natural expiry. Fail-soft на Redis-outage (лог + вернуть False).
- [x] `POST /api/auth/logout` — 204. Декодирует токен из Bearer, кладёт jti в blacklist. Идемпотентно: invalid/expired → тоже 204.
- [x] `get_current_user` проверяет blacklist до resolve юзера → 401 «Token revoked» на revoked jti.
- [x] Frontend `stores/auth.ts::logout` дёргает `POST /api/auth/logout` fire-and-forget перед `localStorage.removeItem`. `multi_tab` reason НЕ дёргает (оригинальная вкладка уже сделала запрос).
- [x] `backend/tests/test_logout_blacklist.py` — 5 тестов: logout → /me 401, garbage token → 204, double logout → 204/204, other user's token unaffected (jti scoping), re-login после logout → новый working token.

**Тесты:**

- [ ] Backend: `/auth/logout` blacklist'ит токен → следующий запрос с ним → 401 (backend Option B — pt.4).
- [ ] Frontend (vitest): mocked `localStorage.token` + mocked `/auth/me` → store rehydrates → user set.
- [x] Playwright (T_TEST.3 pt.2 + pt.3): `multi-tab-logout.spec.ts` — 2 page в одном context, logout в одном → второй редиректит.

**Acceptance:**
1. User логинится, закрывает вкладку, открывает по прямой ссылке `/join/deal/:token` в новой вкладке → рендерит invite-flow (не redirect на login).
2. User неактивен 30 мин → за 2 мин появляется warning → если игнорирует, автоматически logout + landing на `/login?reason=inactivity` с info-banner.
3. User logout в одной вкладке → другая вкладка тоже logout'ится (pt.3).

**Follow-up (pt.4):**
- Refresh token flow (сейчас single JWT; для «keep me logged in for 30 days» нужен long-lived refresh token + short access token).
- Device-list в профиле (superuser может revoke конкретное устройство).
- Suspicious-activity detection (impossible-travel = login из RU + LA за 10 мин → force logout всех сессий).

### T_UX.4 — Multiple addresses + Edit profile modal + avatars + landing on logo ✅ MVP

**Контекст.** Профиль-UX стал плоским: один инлайн-адрес получения, никакой Edit-кнопки, всё редактируется по месту, логотип «Vimana» вёл на dashboard, marketing-landing простаивал. Reworked за 4 инкремента.

**A — Backend addresses (2026-07-20)**

- [x] Модель `ReceivingAddress(id, user_id, label, country_iso, city, city_geoname_id, street, postal_code, note, is_default, created_at)` + partial-unique index `(user_id) WHERE is_default IS TRUE`.
- [x] Миграция `0023` — expand: создаёт таблицу, бэкфилит одну «Default»-строку каждому юзеру с заполненным legacy `receiving_country_iso`. Старые `User.receiving_*` **остаются** (contract-миграция на удаление колонок — отдельным релизом).
- [x] 5 endpoints: `GET /me/addresses`, `POST /me/addresses` (первый auto-default), `PATCH /me/addresses/{id}`, `POST /me/addresses/{id}/default` (обнуляет старый default), `DELETE /me/addresses/{id}` (при удалении default → auto-promote следующего по created_at).
- [x] `POST /deals/{id}/dealvault/messages/share-address` + `POST /inquiries/{id}/messages/share-address` теперь принимают `{"address_id": uuid?}`. Разрешение: указанный → default → legacy fallback → 422.
- [x] 10 backend-тестов (`test_addresses.py`): empty list, first auto-default, second not default, is_default clears previous, /default endpoint, update, delete promotes another, delete last, cannot touch others', country_iso normalized uppercase.

**B — Frontend profile refresh + avatars (2026-07-20)**

- [x] `<AddressesSection>` карточками с inline edit (Add/Edit/Delete/Make default).
- [x] `<AddressFormFields>` — reusable form (label + country + city autocomplete + street + postal + note).
- [x] `<EditProfileModal>` — модалка по кнопке «✎ Edit» вверху /profile: 64×64 avatar preview + Upload/Remove photo + name + phone. Адреса — отдельно в своей секции.
- [x] Two-column Bento layout на /profile: identity/UBA/Verification/Trust слева, Addresses/Contacts/Keypair/Invites/Notifications справа. Admin panel full-width под.
- [x] Аватарки: миграция `0024` (`users.avatar_key VARCHAR(255)`), `POST/DELETE /me/avatar` (multipart, jpeg/png/webp, max 3 MB, streaming SHA + size-guard). R2 бакет тот же что для DealVault attachments. `MeOut.avatar_url` = свежий presigned URL, минтится per-response через `core/avatar_url.py::me_out_with_avatar`. 5 backend-тестов (`test_avatar.py`).
- [x] ProfilePage identity-карточка показывает 48×48 avatar или fallback на инициал.

**C — Chat address picker (2026-07-20)**

- [x] `<ShareAddressModal>` (переиспользуемый) — открывается в DealVaultPage и InquiryPanel. Радио-список карточек user'ских адресов, default предвыбран. Убрана старая `confirm() + auto-default` логика — теперь всегда явный выбор.
- [x] Old handlers переписаны на модалку — сохранены только `onShare(addressId)` callback'и в parent'ах.

**D — Marketing landing on logo click (2026-07-20)**

- [x] Existing `<LandingPage>` (Bento с route example, DealVault log, boarding pass, УБА scorecard, escrow, network, corridor, Nostr, progress, missions) больше не редиректит authed-юзеров.
- [x] Navbar лого `to="/"` (было `/dashboard`) — единый home для всех.
- [x] CTA в navbar landing'а: unauthed → «Request Early Access» (waitlist модалка), authed → «Open Dashboard». i18n `landing.ctaDashboard` в EN+RU.

**Acceptance ✅ (2026-07-20 prod deploy + 7/7 Playwright smoke):**
1. Логотип «Vimana» на любой странице ведёт на `/` (landing).
2. `/profile` — 2 колонки на desktop, 1 на phone, Edit-кнопка справа от заголовка.
3. Аватар загружается через модалку, показывается в profile identity-карточке.
4. В правой колонке Addresses: Add / Edit / Delete / Make default — inline формы.
5. В чате сделки/inquiry кнопка «📍 Share address» → picker с default предвыбранным.
6. Legacy `share-address` без `address_id` продолжает работать для юзеров, ни разу не открывавших профиль после деплоя.

**Follow-up (pt.5):**
1. Celery janitor для orphaned R2 avatars после DELETE.
2. Удаление `User.receiving_*` legacy колонок отдельной миграцией (contract-фаза).
3. i18n для остальных 4 языков (pl/fr/es/ua) — сейчас EN + RU.
4. Client-side resize/crop аватарки перед загрузкой (browser Canvas API).
5. Multiple avatars / alternate identities для carrier vs sender-режимов.

### T_TEST.4 — API contract + fuzzing (schemathesis) ✅ pt.1 + pt.2 MVP

**Активация:** ✅ pt.1 закрыт 2026-07-19 (перед Фазой 4). См. `PRD/PROJECT.md §7.4`.

**pt.1 — MVP no-5xx fuzz ✅**

- [x] `schemathesis==3.39.5` в `backend/requirements.txt`.
- [x] `backend/tests/test_contract_fuzz.py` — pytest-плагин: `schemathesis.from_dict(app.openapi(), app=app, force_schema_version="30")`. FastAPI генерирует OpenAPI 3.1.0, schemathesis 3.x полноценно поддерживает только 3.0.x → патчим версию в dict + `force_schema_version="30"`. Warnings из внутренних вызовов `jsonschema.RefResolver` заглушены на уровне модуля.
- [x] `@schema.parametrize() + @settings(max_examples=15, deadline=None) → case.call()`. Один assertion: `response.status_code < 500`. Дамп body/query/headers на falure.
- [x] **Найден и починен реальный баг**: `GET /api/platform-notices?surface=X` принимал `str | None`, на `"null"` (fuzz'а) → asyncpg InvalidTextRepresentation → 500. Fix: тип `NoticeSurface | None` → FastAPI/Pydantic 422 до DB. Регрессия `test_platform_notices_invalid_surface_rejected` в `test_notices.py`.
- [x] Acceptance для pt.1: **86 test cases across ~50 endpoints × 15 examples ≈ 750 requests → 0 unhandled 5xx**. ~33 сек прогон.

**pt.2 — authed fuzz ✅**

- [x] Session-scoped `pytest_asyncio.fixture` `fuzz_user_token` — register + login regular user раз на сессию, возвращает Bearer.
- [x] Session-scoped `fuzz_superuser_token` — register + promote в superuser (raw SQL update role) + re-login.
- [x] Три parametrize'а на одной schema: `test_no_server_errors_unauthed` (pt.1) + `test_no_server_errors_authed_user` + `test_no_server_errors_authed_superuser`. `case.call(headers={Authorization: Bearer <token>})`.
- [x] `max_examples=10` для authed (vs 15 для unauthed) — балансируем время прогона (2 доп pass'а по ~30 сек каждый).
- [ ] `case.call_and_validate(checks=(status_code_conformance,))` — проверка declared status codes — deferred в pt.3 (OpenAPI auto-schema имеет gaps, много false positives).

**pt.3 — TS drift check (отложено)**

- [ ] `openapi-typescript` в `frontend/devDependencies`.
- [ ] Pre-commit hook: `npx openapi-typescript http://localhost:8000/openapi.json -o frontend/src/types/api.generated.ts` → `git diff --exit-code`. Drift → fail commit.
- [ ] Использовать generated types в `frontend/src/api/*.ts` вместо ручных interface (постепенная миграция).

**pt.4 — HTML report + CI (отложено)**

- [ ] `schemathesis run --checks all --hypothesis-max-examples=50 --html backend/reports/schemathesis.html` в отдельной CI job.
- [ ] Артефакт-загрузка отчёта.
- [ ] Bump `max_examples` до 50 в CI (сейчас 15 для скорости локально).

**Acceptance финальный:** 0 unhandled 500 на fuzz'е всех endpoint'ов (public + authed); CI ломается при drift TS-типов; HTML-отчёт после каждого прогона.

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

### T_TEST.7 — Security scan (OWASP ZAP baseline) + IDOR-матрица

**Активация:** после Фазы 3 (когда T_SEC.1 стабилен), обязательно перед Ф.4.

**pt.1 — ZAP baseline:**
- [ ] `docker run -t owasp/zap2docker-stable zap-baseline.py -t <URL> -r zap-report.html`.
- [ ] Baseline mode (пассивный скан) безопасен на prod. Активный (`zap-full-scan.py`) — только staging.
- [ ] Telegram alert через notification-worker при появлении High/Critical.
- [ ] `.zap/rules.tsv` — known-false-positives с оснвоанием.

**pt.2 — IDOR-матрица (добавлено 2026-07-29 по итогам ручного аудита).**

**Зачем отдельно.** Ручная проверка всех 36 эндпоинтов с path-параметрами (2026-07-29) классического IDOR **не нашла**: владение проверяется везде, вложенные ресурсы скоупятся (`_get_request` сверяет `req.deal_id`, `decrypt-for-me` — `msg.deal_id`), идентификаторы — UUID v4, перебирать нечего. Но это состояние ничем не удерживается: **автоматика IDOR не ловит в принципе**. Schemathesis (T_TEST.4) проверяет «нет 500-х», для него 403 и 200 одинаково валидны. ZAP baseline пассивен и авторизацию не моделирует. То есть отсутствие IDOR держится на 41 ручной проверке 403 в 18 файлах и на внимательности следующего автора.

- [ ] Два пользователя (A и B), не связанные ни сделкой, ни приглашением. Каждый создаёт полный набор объектов: адрес, рейс, заявку, сделку, сообщение в сейфе, вложение, verification-request, спор.
- [ ] Прогон таблицей: **каждый** эндпоинт с path-параметром вызывается токеном A против объекта B. Ожидание — 403 или 404, **никогда 200 и никогда 500**.
- [ ] Отдельно — вложенная подмена: свой `deal_id` + чужой `message_id`/`req_id`/`participant_id`. Это место, где обычно и течёт, и где ручная проверка легко пропускает новый эндпоинт.
- [ ] Матрица строится **из роутера**, а не из списка руками: обойти `app.routes`, отобрать пути с параметрами, упасть на любом, для которого нет записи в таблице ожиданий. Тогда новый эндпоинт без проверки прав валит тест самим фактом появления.
- [ ] Роли отдельно: обычный юзер против арбитерских путей, арбитр без заявленного спора, арбитр с отозванным `OperatorAccessGrant`.
- [ ] Presigned-ссылки: проверить, что TTL для `identity_doc` короче общего (`presign_ttl_for_kind`).

**Acceptance:** ZAP baseline на prod = 0 High, ≤ 3 Medium (документированные); IDOR-матрица покрывает **все** эндпоинты с path-параметрами и падает при появлении непокрытого.

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

### EXP-07 — Tamper-evident DealVault: хеш-цепь + внешнее закрепление 🧪 экспериментальное

**Статус:** исследование, вне roadmap. **Узкая версия уже реализована и закрыта как T3.6** (серверная цепь по `deal_events`, часовой анкер). EXP-07 — целевая модель поверх неё, кода нет.

**Разбор целиком:** [BUZZ.md](BUZZ.md) — анализ внешнего проекта buzz (Nostr-релей, Apache 2.0) + вытекшая проработка доказательности DealVault.

**Чего T3.6 не закрывает.** `DealEvent.nostr_sig` доказывает авторство одной записи, но не полноту, не порядок и не факт неудаления — это T3.6 закрыл. Осталась тонкость уровнем глубже: custodial-подпись ставится нашим сервером нашим же ключом, поэтому **против платформы** она не доказывает ничего, а серверную цепь мы сами и строим. Vimana при этом одновременно арбитр и хранитель записи. Чтобы доказательство работало против нас самих, нужны две вещи, которых в T3.6 нет: `prev` **внутри подписываемого участником события** и цепь, включающая сообщения, а не только события.

- [ ] Решить 7 открытых вопросов из BUZZ.md §7 (публиковать ли 4802, непрозрачный `anchor_id`, разрешение развилки, подпись `prev` на кнопках, частота анкера, содержимое `/chain`, единая таблица цепи).
- [ ] Единая таблица `deal_chain_entries` — одна цепь на сделку, включающая и сообщения, и события (взаимный порядок = предмет спора). Заменяет колонки в `deal_events` из T3.6; переезд потребует пересчёта цепи — см. BUZZ.md §7 п.7.
- [ ] `prev` в теге NIP-01 `["prev","<hex>"]` — читаем сервером, подписан участником, контент остаётся непрозрачным. **Это и есть главное отличие от T3.6**, где `prev` проставляет сервер.
- [ ] Непрозрачный `anchor_id` вместо открытого `deal_id` в теге анкера — в T3.6 `deal_id` публикуется открыто и выдаёт объём и активность сделок.
- [ ] `GET /deals/{id}/chain` — граница заверенности (до какого звена и чьей подписью), а не одна зелёная галочка.

**Зависимости:** поверх T3.6. Требует `NOSTR_PUBLISH_ENABLED=true` (сейчас false — см. T3.5 follow-up). Не конфликтует с T2.3 (threshold) и T3.2 (grants).

**Acceptance (когда/если активируется):** правка, удаление или перестановка любой записи ломает верификацию; участник с одним своим подписанным сообщением на руках может доказать состояние всей истории под ним без доступа к нашей БД.

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
