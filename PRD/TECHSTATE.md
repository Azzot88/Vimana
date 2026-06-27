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
| Auth + Социальный граф (Invite, Connections) | 1 | ⬜ не начато |
| Маркетплейс (Рейсы, Заявки, Мэтчинг) | 1 | ⬜ не начато |
| Сделка (lifecycle + DealEvent) | 1 | ⬜ не начато |
| DealVault (чат + фото + лог, IPFS-ready) | 1 | ⬜ не начато |
| Уведомления | 1 | ⬜ не начато |
| KYC + Комплаенс | 2 | ⬜ не начато |
| Keypair + Nostr-совместимость | 2 | ⬜ не начато |
| Уровень Бизнес-Активности (УБА) | 3 | ⬜ не начато |
| Оператор-арбитр + Споры | 3 | ⬜ не начато |
| Карточные платежи | 4 | ⬜ не начато |
| Эскроу BTC + Залог | 5 | ⬜ не начато |
| USDT-эскроу | 5 | ⬜ не начато |
| Премиум | 6 | ⬜ не начато |
| DealVault → IPFS | 6 | ⬜ не начато |
| Полная Nostr + IPFS портативность | 6 | ⬜ не начато |

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
| D10 | **Nostr-совместимость: Вариант A + D.** Платформа генерирует secp256k1-keypair при регистрации и хранит зашифрованно. Пользователь «забирает» nsec в любой момент → платформа удаляет свою копию. Если обнаружен NIP-07 браузерный extension (Alby, nos2x) — Vimana использует его для подписи вместо custodial ключа | Масс-маркет онбординг без барьеров + поддержка существующей Nostr-идентичности для продвинутых пользователей | 2026-06-27 |

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
| _(добавлять по мере реализации)_ | _(пути)_ |

---

## 4. Ключевые модели данных / контракты (целевые)

**Фаза 1**
- `User(id, email/phone, password_hash, display_name, is_carrier, nostr_pubkey nullable, business_activity_level, created_at)`
- `InviteLink(id, creator_id→User, token, expires_at, used_by→User?)`
- `Connection(id, user_id→User, connected_user_id→User, created_at)` — двусторонняя запись
- `Trip(id, carrier_id→User, origin, destination, depart_at, capacity, allowed_categories, status)`
- `Order(id, sender_id→User, recipient_contact, origin, destination, category, declared_value, currency, description, deadline, status, trip_id→Trip?)`
- `Deal(id, order_id→Order, trip_id→Trip, sender_id, carrier_id, recipient_id?, status, created_at)`
- `DealEvent(id, deal_id→Deal, event_type, payload JSON, actor_id, nostr_sig nullable, timestamp)` — **append-only**
- `DealVaultMessage(id, deal_id→Deal, sender_id, text, is_system, nostr_sig nullable, created_at)` — **иммутабельно**
- `Attachment(id, message_id→DealVaultMessage, r2_key, file_hash SHA-256, ipfs_cid nullable, kind, created_at)` — **иммутабельно**

**Фаза 2**
- `KycRecord(id, user_id, provider, status, verified_at)`
- `ComplianceAck(id, user_id, version, accepted_at)`
- *(User.nostr_pubkey заполняется; DealVaultMessage.nostr_sig и DealEvent.nostr_sig заполняются)*

**Фаза 3**
- `Dispute(id, deal_id, opened_by, status, verdict)`
- `OperatorAccessGrant(id, deal_id, operator_id, granted_by, granted_at)`
- *(User.business_activity_level — заглушка Фазы 1 — заполняется реальным значением УБА; пересчёт Celery beat ежечасно)*
- **УБА-формула:** `round(F_norm × Q_norm × V_norm × D_factor × 1000)`. F = рейсы/мес (rolling 90d), Q = сделки с двумя DealVault-фото (log), V = сумма declared_value USD (log), D_factor = бонус залога [1.0–1.5]. Детали: IMPLEMENTATIONPLAN §6 §3.1.

**Фаза 4**
- `Payment(id, deal_id, method=card, amount, platform_fee, status)`

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
