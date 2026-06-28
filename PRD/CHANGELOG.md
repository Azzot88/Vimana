# Vimana — Sacred Logistics · CHANGELOG.md

> FILL ──────────────────────────────
> Назначение: короткие логи значимых изменений проекта.
> Когда обновлять: при любом значимом изменении кода, моделей, инфраструктуры или PRD.
> Что НЕ дублировать: подробную логику (TECHSTATE), стек (ENVIRONMENT), задачи (TASKS).
> Формат записи (новые сверху): `YYYY-MM-DD · <уровень> · что изменилось · затронутые файлы`
>   уровень ∈ { PRD, MODEL, INFRA, FEATURE, FIX, DECISION }
> ───────────────────────────────────

---

## Записи

- **2026-06-28 · FEATURE** · T1.6: Frontend SPA — React 18 + Vite + TypeScript + TailwindCSS; дизайн-система (navy/amber/ivory, IBM Plex Mono); 11 страниц; Zustand auth store; DealDetailOut на бэкенде · `frontend/src/`, `backend/app/api/deals.py`, `backend/app/schemas/marketplace.py`.
- **2026-06-28 · FEATURE** · T1.5: DealVault API — чат, загрузка файлов (multipart), SHA-256 хеш, presigned URL, иммутабельность на уровне API; R2 graceful degradation без R2_ENDPOINT · `backend/app/api/dealvault.py`, `backend/app/core/storage.py`.
- **2026-06-28 · FEATURE** · T1.4: Trips API (POST/GET с фильтрами), Deals API (match→accept→event→confirm→closed), DealEvent append-only · `backend/app/api/trips.py`, `backend/app/api/deals.py`.
- **2026-06-28 · FEATURE** · T1.3: JWT auth (register/login/me), InviteLink (TTL 7д, одноразовый), двусторонняя Connection, GET /api/me/connections · `backend/app/api/auth.py`, `backend/app/api/social.py`, `backend/app/core/security.py`.
- **2026-06-28 · MODEL** · T1.2: доменные модели — User, InviteLink, Connection, Trip, Order, Deal, DealEvent, DealVaultMessage, Attachment; миграция 0001_initial_models; nostr_sig/ipfs_cid/nostr_pubkey как nullable-заглушки Фазы 2/6 · `backend/app/models/`, `backend/alembic/versions/0001_initial_models.py`.
- **2026-06-28 · INFRA** · T1.1: FastAPI скелет + async SQLAlchemy + Alembic env · `backend/app/main.py`, `backend/app/core/`, `backend/alembic/`.
- **2026-06-27 · INFRA** · T0.1 выполнен: git init (ветка Azzot_main), структура `backend/` + `frontend/`, `docker-compose.dev.yml` (postgres:16 + redis:7), `.env.example`, `.gitignore` · затронуты: backend/Dockerfile, backend/requirements.txt, frontend/Dockerfile, docker-compose.dev.yml, .env.example, TECHSTATE §1.
- **2026-06-27 · PRD** · УБА-формула зафиксирована: `round(F_norm × Q_norm × V_norm × D_factor × 1000)` [0–1000]; 5 уровней (Новичок→Элита); D — бонус-множитель [1.0–1.5], не штраф; Q считает только сделки с двумя DealVault-фото · затронуты: IMPLEMENTATIONPLAN §6 §3.1, TASKS T3.1, METRICS §4, TECHSTATE §4 Фаза 3.
- **2026-06-27 · DECISION** · D10 зафиксирован: Nostr-совместимость = Вариант A (кастодиальный keypair → self-custody path) + Вариант D (NIP-07 browser extension override); детали механики в TECHSTATE §2b · затронуты: TECHSTATE, IMPLEMENTATIONPLAN §5, TASKS T2.2.
- **2026-06-27 · PRD** · Реструктуризация фаз: 4 → 6 (крипто-эскроу выведен в Фазу 5, добавлены Фазы 2/3/4 — Identity+Keys, UBA+Arbitration, Card payments); добавлен Социальный граф (Invite, Connections) в Фазу 1; BlackBox переименован в **DealVault** во всех файлах; добавлены варианты Nostr-совместимости (D10 в TECHSTATE) · затронуты: MASTERPLAN, IMPLEMENTATIONPLAN, TASKS, TECHSTATE, все PRD-файлы.
- **2026-06-27 · PRD** · Проект переименован PeerFlew → Vimana — Sacred Logistics; добавлены слоганы (Wings of Trust / Peer-to-Air / People Are the Network); заполнена Карта файлов в CLAUDE.md · затронуты: все PRD-файлы, CLAUDE.md.
- **2026-06-?? · PRD** · Инициализирована PRD-система Vimana — Sacred Logistics (PROJECT + 5 PRD-узлов + 5 артефактов) · затронуты: все файлы системы.
- **2026-06-?? · DECISION** · Зафиксированы решения D1–D5 (стек, не-кастодиальный BTC-эскроу 2-of-3, Уровень Бизнес-Активности вместо репутации, фазы-функциональные-блоки, «Чёрный ящик») · TECHSTATE.md.

*(Новые записи добавлять сверху. Дату проставлять фактическую.)*
