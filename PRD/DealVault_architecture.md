# DealVault architecture

## Задача

Спроектировать и реализовать архитектуру DealVault как системы персональных криптографических сейфов, используя Pubky как базовый discovery/storage substrate.

Цель:
- identity принадлежит пользователю и определяется ключевой парой;
- новое устройство может восстановить данные при наличии identity key;
- данные распределяются между недоверенными Homeservers;
- DHT используется для discovery, а не для хранения содержимого сделок;
- Homeserver хранит только encrypted opaque objects;
- каждый Deal Vault имеет собственный ключ шифрования;
- при потере identity key новый ключ может быть коллективно авторизован guardians;
- recovery не восстанавливает старый private key, а переводит identity на новый key epoch.

## Базовая архитектура

Разделить систему на пять уровней:

1. Identity — криптографическая identity пользователя.
2. Discovery — поиск Homeservers через Pkarr/Mainline DHT.
3. Storage — хранение opaque encrypted objects.
4. Vault — криптографически изолированный набор данных одной сделки.
5. Recovery — threshold-авторизация нового identity key.

Ключевой принцип:

`DHT = discovery`

`Homeserver = untrusted storage`

`Identity key = authority`

`Vault key = confidentiality`

`Guardians = recovery authority`

## Pubky как основа

Использовать существующие компоненты Pubky SDK вместо повторной реализации:

- `@synonymdev/pubky` для JavaScript/WASM;
- `pubky` для Rust;
- Pubky Client;
- Pkarr/Mainline DHT discovery;
- Homeserver storage API;
- authentication/session mechanisms;
- capability-scoped access;
- event streams, если они нужны для synchronization.

Текущий Pubky `/pub` storage способен хранить произвольные byte blobs, поэтому encrypted DealVault objects можно хранить поверх существующего API. Не считать наличие полноценного `/priv`, general E2E encryption или автоматического Homeserver mirroring уже реализованной возможностью Pubky: эти функции должны быть реализованы отдельно, если они нужны DealVault.

Reference:
https://github.com/pubky/pubky-ai-kit/blob/main/pubky-dev-context.md

## Identity

Alice имеет root key `K0`.

`K0 -> PK0`

`PK0` является постоянным identity identifier.

Private key никогда не передается Homeserver или guardian.

Поддерживать key epochs:

`epoch 0 -> K0`

`epoch 1 -> K1`

`epoch 2 -> K2`

Identity не меняется при rotation; меняется только активный signing key.

Каждый transition должен иметь cryptographically verifiable authorization.

## DHT / Pkarr

DHT не хранит сделки.

Она используется для discovery:

`PK0 -> Homeserver locations`

Не публиковать в DHT:
- список сделок;
- названия сделок;
- участников;
- документы;
- суммы;
- plaintext metadata.

Любая DHT record является untrusted и принимается только после проверки подписи, epoch/sequence и срока действия.

## Homeserver

Homeserver считается недоверенным.

Он хранит:
- opaque object ID;
- encrypted ciphertext;
- size;
- MIME type;
- version;
- integrity/hash metadata;
- необходимые технические metadata.

Не использовать читаемые пути вроде:

`/alice/deals/NYC-Miami-Bob`

Использовать opaque identifiers, например:

`/pub/dealvault/objects/<opaque-id>`

Смысл объекта должен находиться внутри encrypted manifest.

## Deal Vault

Каждая сделка является отдельным cryptographic namespace.

Vault может содержать:
- encrypted manifest;
- participants;
- messages;
- documents;
- attachments;
- events;
- settlement information;
- key envelopes;
- storage placement metadata.

Для каждого Vault генерировать независимый случайный Vault Key `VK`.

Identity key не должен непосредственно шифровать документы.

Большие encrypted objects могут разбиваться на chunks.

`plaintext -> AEAD -> encrypted chunks`

Homeserver получает только ciphertext.

## Key hierarchy

Логическая модель:

`K0/K1/...`

↓

`Identity authority`

↓

`Vault Key A17 / Vault Key B42 / ...`

↓

`Object/chunk encryption`

Rotation `K0 -> K1` не должна требовать перешифровки всех существующих документов.

Существующие Vault Keys должны оставаться доступными после восстановления identity.

## Участники сделки

Для каждого Vault существует participant policy.

Например:

`A17 = Alice + Bob + Carol`

Vault Key доступен только авторизованным участникам через encrypted key envelopes:

`VK_A17`

↓

`envelope(Alice)`

`envelope(Bob)`

`envelope(Carol)`

## Identity Vault

Создать специальный encrypted Identity Vault.

Он содержит registry:
- Vault IDs;
- storage locations;
- current key epoch;
- recovery policy;
- guardian relationships;
- ссылки/объекты для Vault Keys;
- версии состояния.

Registry должен быть подписан и зашифрован.

Восстановление нового устройства при наличии `K0`:

`K0 -> PK0 -> DHT -> Homeservers -> Identity Vault -> Vault Registry -> Deal Vaults`

Проверять подписи и integrity на каждом этапе.

## Распределенное хранение

Один пользователь может использовать:
- платформенные Homeservers;
- Homeservers других пользователей;
- Homeservers guardians;
- собственные Homeservers;
- несколько независимых storage providers.

Пример:

`Vault A17 -> HS1, HS3`

`Vault B42 -> HS2, HS3`

`Vault C91 -> HS1, HS4, HS5`

Ни один отдельный Homeserver не должен быть обязательным для восстановления при наличии достаточных копий.

## Guardians

Alice заранее выбирает guardians и задает threshold policy, например `3-of-5`.

Guardian relationship создается заранее и подтверждается обеими сторонами.

Guardian не получает:
- `K0`;
- `K1`;
- Vault Keys Alice.

Guardian хранит только необходимые данные relationship и recovery policy.

## Recovery

Если `K0` потерян, старый ключ не восстанавливается.

Alice локально генерирует:

`K1 -> PK1`

Создает `RecoveryRequest`:
- identity `PK0`;
- requested public key `PK1`;
- new epoch;
- random request ID;
- expiration.

Alice подписывает request новым `K1`.

Эта подпись не доказывает, что отправитель — Alice. Она только связывает request с новым ключом.

## Коллективная авторизация K1

Guardian не подписывает утверждение «PK1 принадлежит Alice».

Он подписывает конкретный transition:

`Authorize(PK0 -> PK1, epoch=N, request_id=R, expiration=T)`

Каждый guardian независимо проверяет Alice и конкретный request.

После threshold создается `Recovery Certificate`.

Certificate означает:

`PK1 authorized as current signing key for identity PK0 at epoch N`

Любой клиент может проверить certificate без доверия к Homeserver.

## Authentication перед guardians

Если `K0` потерян, криптография сама по себе не может доказать, что человек перед guardians действительно Alice.

Social recovery поэтому является threshold trust procedure.

Authentication procedure должна быть определена заранее при создании guardian relationship.

Не считать достаточными доказательствами:
- recovery URL;
- знание PK0;
- DHT record;
- новый PK1.

Guardian должен использовать заранее определенный независимый recovery channel или credential.

Важно: guardian никогда не получает private K1.

## Защита от malicious recovery

Recovery signature должна включать:
- PK0;
- PK1;
- epoch;
- request ID;
- expiration;
- recovery policy/version.

Это обеспечивает binding конкретного request и replay protection.

Рекомендуется recovery delay:

`threshold approvals -> pending -> delay -> K1 active`

Например 24–72 часа.

Если Alice еще имеет K0, она должна иметь возможность отменить pending recovery.

Отдельно реализовать emergency flow для `K0 compromised`, потому что потеря и компрометация ключа — разные threat scenarios.

## Важное ограничение social recovery

Если K0 полностью потерян и нет другого заранее созданного credential, система не может математически доказать личность Alice.

Guardians фактически коллективно принимают решение:

`мы признаем этот recovery request продолжением identity PK0 и разрешаем PK1`

Криптография должна защищать integrity этого решения, но не может заменить процедуру authentication человека перед guardians.

## Recovery data

После успешного recovery:

`K0 lost`

↓

`3-of-5 guardian authorization`

↓

`PK0 -> PK1`

↓

`new identity epoch`

↓

`DHT discovery`

↓

`Homeservers`

↓

`encrypted Identity Vault`

↓

`Vault Registry`

↓

`encrypted Deal Vaults`

↓

`Vault Keys`

↓

`user data`

Identity recovery и data recovery являются двумя последовательными операциями.

## Threat model

Считать недоверенными:
- DHT nodes;
- Pkarr infrastructure;
- Homeservers;
- indexers;
- отдельного guardian;
- storage provider;
- network observers.

Требования:
- компрометация одного Homeserver не раскрывает plaintext Vault;
- компрометация меньшего числа guardians, чем threshold, не восстанавливает identity;
- DHT poisoning не меняет identity;
- replay старого recovery request/certificate не откатывает identity;
- один Homeserver не является single point of failure.

## Metadata privacy

Шифрование содержимого недостаточно для полной приватности.

Отдельно анализировать leakage через:
- количество объектов;
- размеры объектов;
- timestamps;
- частоту операций;
- storage provider;
- network metadata;
- связь нескольких объектов с одной identity.

Первая версия должна минимизировать metadata leakage, но не обещать его полное устранение.

## Что переиспользовать из Pubky

Использовать существующие primitives SDK для:
- public keys;
- signing;
- authentication;
- Homeserver resolution;
- storage operations;
- Pkarr discovery;
- event streams.

Не дублировать функциональность SDK без необходимости.

## Что реализовать поверх Pubky

Новая часть DealVault:

1. Deal Vault data model.
2. Identity Vault registry.
3. Encrypted manifests.
4. Vault key hierarchy.
5. Chunking.
6. E2E encryption layer.
7. Participant key envelopes.
8. Storage placement.
9. Guardian relationships.
10. Recovery requests.
11. Recovery certificates.
12. Key epochs.
13. Key revocation.
14. Recovery delay.
15. Emergency compromised-key flow.
16. Distributed Vault reconstruction.
17. Metadata privacy policy.

## Криптография

Не изобретать собственные cryptographic primitives.

Перед реализацией выбрать стандартные проверенные primitives и библиотеки для:
- signing;
- key agreement;
- KDF;
- AEAD;
- hashing;
- CSPRNG;
- encrypted key envelopes;
- threshold authorization/signatures.

Выбор конкретных primitives должен быть отдельным архитектурным решением с threat model.

## Acceptance criteria

### Новый device + K0

`K0 -> PK0 -> DHT -> Homeservers -> Identity Vault -> Deal Vaults`

Все доступные пользовательские данные восстанавливаются.

### Homeserver unavailable

При наличии достаточной копии на другом Homeserver Vault остается доступным.

### K0 lost

Alice создает K1, guardians достигают threshold, создается валидный recovery certificate, после чего Alice получает доступ к существующим Vaults.

### Один guardian compromised

Один guardian не может самостоятельно восстановить identity.

### DHT poisoning

Поддельные records отклоняются по cryptographic verification.

### Homeserver compromised

Компрометированный Homeserver не получает ключей, позволяющих расшифровать Deal Vault.

### Replay

Старый request/certificate не может повторно активировать устаревший key epoch.

### Malicious recovery

При недостаточном threshold или провале authentication новый ключ не активируется.

### Recovery race

При наличии K0 Alice может отменить pending recovery.

## Порядок реализации

### Этап 1

Подключить Pubky SDK и реализовать identity + Homeserver storage.

### Этап 2

Реализовать Deal Vault как encrypted object namespace.

### Этап 3

Реализовать Vault Keys и participant key envelopes.

### Этап 4

Реализовать Identity Vault и encrypted Vault Registry.

### Этап 5

Реализовать распределение и reconstruction данных.

### Этап 6

Реализовать guardian relationships.

### Этап 7

Реализовать `3-of-5` recovery и key epochs.

### Этап 8

Добавить recovery delay, revocation и emergency compromise flow.

### Этап 9

Провести threat modeling и metadata privacy analysis.

### Этап 10

После этого рассматривать production deployment и дополнительные backup/indexing services.

## Итоговая модель

`Private Key`

↓

`Persistent Identity`

↓

`Pkarr / DHT`

↓

`Distributed Homeservers`

↓

`Opaque Encrypted Objects`

↓

`Identity Vault + Deal Vaults`

↓

`Vault-specific Keys`

↓

`Participant-specific Key Envelopes`

Recovery:

`K0 lost`

↓

`New K1`

↓

`Independent Guardian Authentication`

↓

`Threshold Authorization`

↓

`Recovery Certificate`

↓

`PK0 -> PK1`

↓

`DHT discovery`

↓

`Encrypted Vault reconstruction`

## Архитектурная формула DealVault

DealVault не должен быть приложением, которое владеет данными пользователя.

Приложение является клиентом криптографически принадлежащих пользователю Vaults.

Pubky предоставляет базовые identity/discovery/storage primitives.

DealVault добавляет поверх них:

`encrypted personal vaults + distributed storage + participant encryption + social key recovery`

Это и является основной архитектурной задачей реализации.
