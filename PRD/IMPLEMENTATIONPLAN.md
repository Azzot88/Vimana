# Vimana — Sacred Logistics · IMPLEMENTATIONPLAN.md

> NAV ──────────────────────────────
> ↑ старший (читать ДО, при конфликте — он прав): USERJOURNEY.md
> ↓ младший (читать ПОСЛЕ, определяется этим файлом): TASKS.md
> Поток: PLANNING — пишется старший→младший · UPDATES — правится по минимальному подъёму
> ───────────────────────────────────

## How We Build It · CTO Execution Plan

---

## 1. Роль документа

Отвечает на вопрос: **в каком порядке мы строим Vimana, чтобы каждая фаза была готовым MVP, а архитектура выдерживала рост?** Всё в итоге питает `TASKS.md`. Фазы идут через **функциональные блоки**: от самого простого и важного к более сложному.

---

## 2. Базовые принципы

### Продуктовые
- **Trust-first.** Иммутабельность записей доставки (DealVault) — append-only, фото нельзя удалить/подменить.
- **Non-custodial-first.** Платформа никогда не держит средства пользователей — только ключ арбитра. Архитектура эскроу проектируется под это с самого начала.
- **Platform-not-carrier.** Vimana — информационный и эскроу-слой; риск перевозки несёт пользователь.

### Инженерные
- **Сначала ядро данных, потом UI.** Если БД не связывает рейсы, заявки и стороны — UI бесполезен.
- **Event Sourcing Lite.** Любое изменение статуса сделки — отдельное неизменяемое событие (`DealEvent`).
- **Design for portability.** Данные проектируются как сериализуемые, отвязываемые от платформы объекты с Фазы 1 — чтобы в Фазе 4 включить экспорт и Nostr + IPFS без переделок моделей.
- **Миграции обязательны** (Alembic). Никаких ручных правок схемы.

---

## 3. Карта доменов по фазам

| Домен | Фаза | Описание |
|---|---|---|
| **Пользователи / Auth** | 1 | Аккаунты, JWT, профиль, лёгкая верификация перевозчиков |
| **Социальный граф** | 1 | Инвайт-ссылки, связи между пользователями, видимость связей в профиле |
| **Рейсы** | 1 | Публикация рейса перевозчика (маршрут, дата, место, категории) |
| **Мэтчинг** | 1 | Сведение перевозчиков и отправителей |
| **Сделка** | 1 | Lifecycle + append-only `DealEvent` |
| **DealVault** | 1 | Иммутабельный чат + фото (R2/S3) + лог; SHA-256 → CID-совместимо с IPFS |
| **Уведомления** | 1 | Email/push, мягкие напоминания |
| **Peer Identity Verification (P2P KYC)** | 2 | Перевозчик просит документы отправителя; локальный OCR + публичные санкционные CSV; encrypted identity container (ключ владельца из T2.2) |
| **Trust Graph (Web-of-Trust)** | 2 | Транзитивный граф `peer_verified`/`dealt_with`/`invited`; круги доверия |
| **Keypair + Nostr** | 2 | secp256k1 keypair per user, подпись DealVault-событий, Nostr-совместимость |
| **Уровень Бизнес-Активности (УБА)** | 3 | Частота × количество выполненных рейсов × оценочная стоимость × размер залога |
| **Оператор-арбитр и споры** | 3 | Консоль, доступ к DealVault, вердикт (базовая механика уже закрыта в T1.23/T1.24) |
| **Vimana Nostr Relay + Federation** | 3.5 | strfry-контейнер; publish trip events (NIP-99 kind 30402) в whitelist friendly relays |
| **Regulatory KYC/AML** | 4 | Провайдер (Sumsub/Onfido/Jumio); блокирует `PLATFORM_PAYMENT_INITIATE` без verified статуса |
| **Карточные платежи** | 4 | Карта на платформе, комиссия. Без крипты. Требует Regulatory KYC |
| **Эскроу BTC + Залог** | 5 | BTC 2-of-3 (HodlHodl-схема), ключ арбитра, некастодиальный кошелёк, залог |
| **USDT-эскроу** | 5 | Аналог BTC-эскроу |
| **Премиум** | 6 | Хранение документов + учёт |
| **DealVault → IPFS** | 6 | Полный экспорт DealVault в IPFS (CID каждого сообщения и вложения) |
| **Портативность данных (Nostr + IPFS)** | 6 | Отвязка аккаунта/данных, экспорт как Nostr-события |

---

## 4. Фаза 1 — Ядро доверия (V1)

> **Цель:** рабочий маркетплейс ручной авиадоставки + иммутабельная запись. Без денег на платформе, без эскроу.

⚠️ Нарушение порядка шагов внутри фазы ведёт к хаосу в БД и переделкам.

### 1.1 Модели данных (фундамент)
1. `User` — id, email/phone, password_hash, display_name, is_carrier, nostr_pubkey (nullable-заглушка, Фаза 2), business_activity_level (заглушка-поле), created_at.
2. `Connection` — id, user_id, connected_user_id, invite_token, created_at. Двусторонняя связь (запись для каждой стороны).
3. `InviteLink` — id, creator_id, token, expires_at, used_by (nullable). Одноразовая ссылка-приглашение.
4. `Trip` — id, carrier_id, origin, destination, depart_at, capacity, allowed_categories, status [draft, open, matched, completed, cancelled].
5. `Order` — id, sender_id, recipient_contact, origin, destination, category (enum: document, medicine, electronics, gift, other), declared_value, currency, description, deadline, status, trip_id (nullable).
6. `Deal` — id, order_id, trip_id, sender_id, carrier_id, recipient_id (nullable), status [draft, matched, accepted, in_transit, delivered, confirmed, closed, disputed], created_at.
7. `DealEvent` — id, deal_id, event_type [created, matched, accepted, handoff, in_transit, received, confirmed, closed], payload (JSON), actor_id, timestamp. **Append-only.**
8. `DealVaultMessage` — id, deal_id, sender_id, text, is_system, created_at. **Нельзя удалять/редактировать.**
9. `Attachment` — id, message_id, r2_key, file_hash (SHA-256), ipfs_cid (nullable, заполняется в Фазе 6), kind [handoff_photo, receipt_photo, doc, payment_receipt], created_at. **Иммутабельно.**

> [!IMPORTANT]
> `nostr_pubkey`, `category`, `business_activity_level`, `ipfs_cid` вводятся в Фазе 1 как nullable-заглушки — чтобы Фазы 2–6 добавляли логику без миграций моделей.

> [!NOTE]
> **IPFS-readiness:** `file_hash` (SHA-256) — это уже multihash-основа CID. Поле `ipfs_cid` в `Attachment` хранит CID после пина в Фазе 6. `DealVaultMessage` и `DealEvent` структурированы как сериализуемые Nostr-события: при добавлении подписи (Фаза 2) они становятся валидными Nostr event objects.

*Никакого UI до завершения и тестирования моделей.*

### 1.2 Аутентификация + Социальный граф
1. JWT-auth (регистрация/логин).
2. **InviteLink**: пользователь генерирует ссылку-приглашение (`/invite/{token}`); друг переходит, регистрируется (или логинится), связь создаётся автоматически.
3. **Connection**: двусторонняя связь между пользователями; видна в профиле как «Ваши контакты» — люди, с которыми уже проводились доставки или кого вы пригласили.
4. **Guest-invite**: сделка может создаваться с `recipient_contact`; по ссылке получатель регистрируется и привязывается к сделке.

### 1.3 Базовый API (маршруты и сделки)
- `POST /api/trips` — опубликовать рейс/маршрут поездки.
- `GET /api/trips` — список рейсов (с фильтрами: маршрут, дата, категория).
- `POST /api/deals/match` — сопоставить отправителя и рейс (создать сделку).
- `POST /api/deals/{id}/accept` — принять условия (→ accepted).
- `POST /api/deals/{id}/event` — зафиксировать событие (handoff/in_transit/received).
- `GET /api/deals/{id}/dealvault` — получить чат, фото и лог DealVault.
- `POST /api/deals/{id}/dealvault/messages` — сообщение/фото (загрузка в R2/S3, SHA-256, CID-заглушка).
- `POST /api/deals/{id}/confirm` — подтвердить получение (→ confirmed → closed).
- `GET /api/deals` — мои доставки.
- `POST /api/invites` — создать invite-ссылку.
- `POST /api/invites/{token}/accept` — принять приглашение (создать Connection).
- `GET /api/me/connections` — список связей в профиле.

### 1.4 Frontend (дашборд + социальный граф)
1. Дашборд (Я везу / Мне везут / Я отправляю).
2. Мастер публикации рейса и управления расписанием.
3. Экран сделки с DealVault (чат, иммутабельные фото, посадочный талон-сводка).
4. Экран статусов/событий (фиксация передачи, получения).
5. Профиль: заглушка УБА + **секция «Контакты»** (список Connections с аватарами и историей доставок).
6. Поток приглашения: экран генерации ссылки, экран принятия, подтверждение связи.
7. **i18n:** `react-i18next`; 6 языков (EN / UA / RU / PL / FR / ES); переключатель в UI; выбор сохраняется в `localStorage`. Ukraine сокращается до UA (не UK — во избежание конфликта с United Kingdom).
8. **Геодата:** бэкенд загружает OpenFlights `airports.dat` (~7 000 аэропортов) в память при старте; поиск по тексту и по координатам (Haversine, D11); фронт — компонент `AirportSelect` с autocomplete + кнопка геолокации (ближайшие аэропорты, топ-3 видимы + прокрутка).
9. **Телефон в профиль:** убрать из регистрации; добавить в ProfilePage с селектом кода страны.
10. **Мобильная версия:** mobile-first layout, Tailwind breakpoints, нижняя навигация на мобильном, тач-зоны ≥44px, проверка на 375px / 390px.

### 1.5 Уведомления
1. Celery beat — проверка дедлайнов и статусов.
2. Email о статусах и приближении прибытия.
3. **Telegram:** привязка chat_id через бот; уведомления о статусах сделки.
4. **WhatsApp:** привязка номера через провайдера (Twilio / WATI); те же события.
5. В профиле — управление каналами (вкл/выкл каждый).
6. Мягкие формулировки (см. DESIGNGUIDELINES §9).

### ✅ Phase 1 Integrity Check
- [ ] `DealVaultMessage` и `Attachment` нельзя удалить/изменить?
- [ ] `DealEvent` append-only?
- [ ] Социальный граф: InviteLink одноразовый, Connection двусторонняя?
- [ ] Стороны и роли (Отправитель/Перевозчик) явно идентифицированы?
- [ ] Фото хешируются (SHA-256), хеш хранится, `ipfs_cid` поле готово?
- [ ] `nostr_pubkey` в `User` — nullable, готово к Фазе 2?
- [ ] Нигде нет иллюзии, что платформа везёт сама или держит деньги?

---

## 5. Фаза 2 — Идентификация и ключи

> **Цель:** верифицированные силами сети участники, keypair как основа портативности. Regulatory KYC — Фаза 4. Зависимость: Фаза 1 стабильна.

### 2.1 Peer Identity Verification (P2P KYC)
1. `VerificationRequest` — id, deal_id, requested_by, status ∈ {pending, upload, later_in_person, declined, verified, escalated}.
2. `IdentityContainer` — id, owner_id, blob_encrypted BYTEA, doc_hash, doc_country, doc_type, sanctions_check_status. Ключ шифрования = owner's Nostr nsec (из T2.2). Multi-doc: один пользователь → много контейнеров.
3. `PeerVerification` — id, subject_id, verified_by_id, container_ref_id, in_deal_id, method ∈ {app_ocr, in_person_photo, in_person_visual}, created_at, revoked_at. Append-only событие сети.
4. Три варианта ответа отправителя: `later_in_person` (позже при встрече) / `declined` (метка на профиль, перевозчик вправе отменить) / `upload` (сейчас через OCR).
5. Multi-doc по принципу US DMV — если сомнения → запрос второго документа.
6. Escalation при подозрении на фальшивку → создаётся `Dispute` из T1.23 с типом `identity_fraud`.
7. Локальный OCR: PaddleOCR (fallback tesseract) — без внешних API.
8. Санкционные списки: OFAC SDN + EU consolidated — публичные CSV, обновляются ежедневно.
9. Перевозчик **не показывает свои документы** — отвечает депозитом (Фаза 5) и историей.

### 2.1a Trust Graph (Web-of-Trust)
1. `TrustEdge` — id, from_user_id, to_user_id, kind ∈ {peer_verified, dealt_with, invited}, weight, source_ref.
2. Sybil-guard: `peer_verified` edge валиден только если между парой есть `DealStatus.closed`.
3. `GET /api/me/trust-circle?depth=N` — BFS до глубины 6.
4. Публичная метрика: `verifications_issued_count`, `verifications_received_count`.

### 2.2 Keypair + Nostr-совместимость (D10: Вариант A + D)
1. При регистрации генерируется secp256k1-keypair. `nsec` хранится зашифрованно (AES-256-GCM; ключ шифрования в env/KMS, не в БД). `npub` → `User.nostr_pubkey`.
2. `User.key_self_custody: bool = False` — флаг наличия nsec у платформы.
3. DealVault-события подписываются server-side: `sig = schnorr_sign(event_hash, nsec)`. Сервер верифицирует подпись по `npub` перед сохранением.
4. **Self-custody path:** `POST /api/me/keypair/export` (re-auth) → `POST /api/me/keypair/claim` → платформа удаляет nsec, `key_self_custody = True`; дальнейшая подпись — client-side или NIP-07.
5. **Import:** `POST /api/me/keypair/import` принимает существующий npub; платформа не хранит чужой nsec; `key_self_custody = True` сразу.
6. **NIP-07 (Вариант D):** frontend обнаруживает `window.nostr` → запрашивает `getPublicKey()` → предлагает переключиться на extension-подпись → frontend передаёт pre-signed event, сервер верифицирует. Extension-подпись имеет приоритет над custodial.

### ✅ Phase 2 Integrity Check
- [ ] Peer verification: три варианта ответа (later/decline/upload) все работают?
- [ ] Multi-doc branch (первый паспорт + опциональный второй документ)?
- [ ] Escalation → создаёт `Dispute` типа `identity_fraud`?
- [ ] `IdentityContainer` расшифровывается только владельцем через nsec (никто третий, включая платформу)?
- [ ] `PeerVerification` без closed deal между verifier и subject → 400 (Sybil-guard)?
- [ ] Локальный OCR (PaddleOCR) работает без внешних API?
- [ ] OFAC SDN список обновляется ежедневно?
- [ ] Keypair хранится безопасно (вариант — TECHSTATE D10)?
- [ ] DealVaultMessage подписаны и проверяемы без платформы?
- [ ] **Regulatory KYC отсутствует** — переезжает в Фазу 4 (T4.1)?

---

## 6. Фаза 3 — УБА и арбитраж

> **Цель:** метрика доверия и разрешение споров. Зависимость: Фаза 2 стабильна.

### 3.1 Уровень Бизнес-Активности (УБА)

Рассчитываемая метрика доверия. Заменяет заглушку `User.business_activity_level` Фазы 1.
Recalculate: Celery beat, каждый час; кеш в `User.business_activity_level`.

**Компоненты (скользящее окно: последние 90 дней)**

| Символ | Что измеряет | Источник данных |
|---|---|---|
| F — Частота | Завершённых рейсов в месяц | `Deal.status = closed`, деление на 3 |
| Q — Качество | Подтверждённых доставок с фото | `Deal` с DealVault-фото передачи + получения |
| V — Объём | Суммарная задекларированная стоимость (USD) | `SUM(Order.declared_value)` по closed deals |
| D — Депозит | Пиковый размер активного залога | `MAX(Collateral.amount)`; 0 если не использовался |

**Формула**

```
F_norm   = min(F / 8,   1.0)                              — насыщение при 8 рейсах/мес
Q_norm   = min(log₁₀(Q + 1) / log₁₀(51),  1.0)          — насыщение при 50 сделках
V_norm   = min(log₁₀(V + 1) / log₁₀(50001), 1.0)        — насыщение при $50 000

D_factor = 1.0 + 0.5 × min(D / 5000, 1.0)               — диапазон [1.0 … 1.5]

УБА = round(F_norm × Q_norm × V_norm × D_factor × 1000)  — диапазон [0 … 1000]
```

**Уровни**

| УБА | Уровень |
|---|---|
| 0–49 | Новичок |
| 50–199 | Проверенный |
| 200–449 | Надёжный |
| 450–749 | Доверенный |
| 750–1000 | Элита |

**Ключевые решения формулы**
- `D_factor` — множитель-бонус, не штраф. Без залога D = 0 → factor = 1.0 (нейтральный). Депозит усиливает УБА, но не уничтожает его при отсутствии.
- `Q` считает только сделки с **обоими** фото в DealVault (передача + получение). Без фото — не засчитывается.
- Логарифмическая шкала Q и V защищает от накрутки микро-сделками с низкой стоимостью.
- `F` — не просто количество рейсов, а активность текущего периода (rolling window).
- Видимость: профиль пользователя + карточка участника при мэтчинге.

### 3.2 Оператор-арбитр и споры
1. Роль `Operator`; консоль.
2. `Dispute` — id, deal_id, opened_by, status, verdict.
3. `OperatorAccessGrant` — доступ к DealVault конкретной сделки по запросу стороны.
4. Вердикт → при наличии эскроу (Фаза 5) направляет разблокировку через ключ арбитра.

### ✅ Phase 3 Integrity Check
- [ ] УБА не позволяет накрутку микро-сделками (нормализация)?
- [ ] Оператор видит DealVault только по запросу стороны и под аудит?
- [ ] Вердикт арбитра прослеживается в логе `DealEvent`?

---

## 6.5 Фаза 3.5 — Vimana Nostr Relay + Federation

> **Цель:** свой Nostr-relay в prod; каждый рейс = signed event в глобальной сети. Зависимость: Фаза 2 (keypair) + Фаза 3 (арбитраж, УБА).

### 3.5.1 Relay-runtime + event model
1. **strfry** как отдельный контейнер `nostr-relay` в docker-compose. LMDB storage, NIP-01/NIP-11/NIP-42/NIP-99.
2. Trip event model: **kind 30402** (NIP-99 Classified Listing, replaceable per `d`-tag). Tags: `d`, `l` (locations IATA), `t` (categories), `published_at`, `expires_at`, `capacity`.
3. Signed user's nsec (из T2.2) — не платформенным ключом.

### 3.5.2 Publish bridge
1. При `POST /api/trips` (после Postgres commit) — Celery task `publish_trip_to_nostr(trip_id)`.
2. Publish в свой relay + broadcast в whitelist `NOSTR_FRIENDLY_RELAYS` (env, comma-separated).
3. Идемпотентность через `Trip.nostr_event_id` (unique).
4. При cancelled — event kind 5 (deletion request).

### 3.5.3 Federation + auth
1. Стартовый whitelist: damus.io, nostr.wine, relay.nostr.band (уточнить в TECHSTATE D-NOSTR-FEDERATION).
2. NIP-42 auth: только Vimana-npub могут писать в наш relay.
3. Rate-limit 30 events/hour per pubkey; WoT-gate из T2.4.
4. **Subscribe (чтение чужих events) — отложено до Фазы 4+**.

### ✅ Phase 3.5 Integrity Check
- [ ] Event публикуется в наш relay и минимум 2 friendly relays?
- [ ] Signed user's nsec (не платформенный ключ)?
- [ ] Deletion event корректно обрабатывается при cancelled?
- [ ] Rate-limit срабатывает после 30 events/hour?
- [ ] Наш relay виден в damus/amethyst/coracle по тегу `#t: vimana`?

---

## 7. Фаза 4 — Карточные платежи + Regulatory KYC

> **Цель:** монетизация без крипты. Появление реальных денег → появление regulator'а. Зависимость: Фаза 3.5 стабильна.

### 4.1 Классический regulatory KYC / AML
1. Выбор провайдера — TECHSTATE Decision Log D-KYC (варианты: Sumsub / Onfido / Jumio).
2. `KycRecord` — id, user_id, provider, external_id, status ∈ {pending, verified, rejected, expired}, verified_at, expires_at, level.
3. `ComplianceAck` — id, user_id, doc_version, category, acknowledged_at.
4. `CorridorRestriction(origin_country, destination_country, requires_kyc_level, blocked)` — санкционный периметр коридоров.
5. Webhook провайдера → обновляет `KycRecord.status` → триггерит evaluation прав.
6. Permission `PLATFORM_PAYMENT_INITIATE` требует `KycRecord.status = verified`.

### 4.2 Платежи на платформе
1. `Payment` — id, deal_id, method [card], amount, platform_fee, status.
2. Интеграция карточного процессинга. Комиссия платформы с каждой транзакции.
3. Все платёжные события пишутся в `DealEvent`.
4. **Зависит от T4.1** — пользователь без verified KYC → 403.

### ✅ Phase 4 Integrity Check
- [ ] User без `KycRecord.status = verified` → 403 на `POST /payments`?
- [ ] Санкционный периметр блокирует запрещённые пары стран на этапе match?
- [ ] `ComplianceAck` версионируется и хранится по каждой версии условий?
- [ ] Все карточные транзакции пишут событие в `DealEvent`?
- [ ] Комиссия рассчитывается корректно?
- [ ] Платформа не хранит карточные данные напрямую (передача сразу процессору)?

---

## 8. Фаза 5 — Крипто-эскроу

> **Цель:** доверие к деньгам для дорогих грузов. Зависимость: Фаза 4 стабильна.

### 5.1 Эскроу BTC + Залог (HodlHodl-схема)
1. `Escrow` — id, deal_id, chain [BTC], type [multisig_2of3], lock_address, amount, arbiter_pubkey_ref, status [created, funded, released, refunded, disputed].
2. `Collateral` — залог перевозчика: сумма, статус.
3. Схема **2-of-3 multisig**: ключи — плательщик, перевозчик, **платформа (арбитр)**; релиз — 2 подписи; платформа подписывает **только при споре**. **Средства не кастодируются платформой.**
4. Некастодиальный кошелёк на платформе для возвратов.
5. **Фи за безопасную сделку (эскроу)** — основной поток монетизации.
6. **Graceful degradation:** при недоступности крипто-слоя сделки Фаз 1–4 продолжают работать.

### 5.2 USDT-эскроу
- Аналог BTC-эскроу для USDT (контрактная 2-of-3 / арбитр-подпись на поддерживающей сети). Та же не-кастодиальная модель.

### ✅ Phase 5 Integrity Check
- [ ] Платформа держит **только ключ арбитра**, никогда — средства?
- [ ] Релиз требует 2 из 3 подписей; платформа подписывает только в споре?
- [ ] Regulatory KYC (Фаза 4) — обязателен до операций с эскроу?
- [ ] USDT-эскроу сохраняет не-кастодиальную модель?

---

## 9. Фаза 6 — Премиум + IPFS-портативность

> **Цель:** доп. ценность и полная децентрализация данных. Зависимость: Фаза 5 стабильна.

### 6.1 Премиум
- `PremiumSubscription`; хранилище документов + учёт (история, экспорт отчётов).

### 6.2 DealVault → IPFS
- Для каждого `Attachment`: SHA-256 → multihash → CID; файл пинится в IPFS (или Filecoin/Pinata); `Attachment.ipfs_cid` заполняется.
- Для каждого `DealVaultMessage`: сериализуется как Nostr event JSON (signed keypair из Фазы 2), пинится в IPFS; CID сохраняется.
- Полный DealVault сделки экспортируется как self-contained IPFS DAG: CID корня = верификационный хеш всей записи.

### 6.3 Полная Nostr + IPFS портативность
- Экспорт отвязываемого пакета аккаунта: профиль, все DealVault как Nostr-события, IPFS CID вложений.
- Аккаунт совместим с Nostr-клиентами: npub идентифицирует пользователя, прошлые записи верифицируемы.
- Решение по операторской/админ-панели — зафиксировать в Decision Log TECHSTATE.

### ✅ Phase 6 Integrity Check
- [ ] CID каждого вложения совпадает с SHA-256 при верификации?
- [ ] DealVault-экспорт самодостаточен без платформы?
- [ ] Nostr-совместимость: npub → все signed events проверяемы?
- [ ] Премиум не даёт нечестного преимущества в УБА?

---

## 10. Что сознательно откладываем (за пределами 6 фаз)
- Эквайринг банковских API сверх базового процессинга.
- Интеграция с таможенными/судебными системами.
- Многосторонние сделки (только 1-на-1 + получатель).
- Нативное мобильное приложение (начинаем с web).

---

## 11. CTO Integrity Check (сквозной)
Перед переходом к каждой следующей фазе:
1. **Записи нельзя подделать?** (DealVault append-only, фото хешированы, подписи валидны?)
2. **Не держим средства?** (Только ключ арбитра; релиз 2-of-3? — актуально с Фазы 5.)
3. **Готовность к следующей фазе?** (Модели расширяемы, nullable-поля заполнены, API версионирован?)

«Нет» — чиним архитектуру до перехода.
