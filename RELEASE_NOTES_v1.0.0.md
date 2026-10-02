# discord-coper v1.0.0

Первый релиз. Discord-бот, который копирует **структуру** сервера — роли,
категории, каналы и права доступа к каждому каналу — и воссоздаёт её на другом
сервере.

По сути это та же идея, что встроенные в Discord *Шаблоны сервера*, но здесь
переносятся ещё голосовые, трибунные и форумные каналы.

## Как пользоваться

1. Добавьте бота на **исходный** сервер → `/copy`. Бот вернёт короткий
   **ID конфига** и приложит сам конфиг JSON-файлом.
2. Добавьте бота на **целевой** сервер → `/paste id:<ID>`. После подтверждения
   структура будет воссоздана.

| Команда | Кто может | Что делает |
| --- | --- | --- |
| `/copy` | **Управление сервером** | Снимает слепок сервера, возвращает ID + JSON. |
| `/paste id:<id>` | **Администратор** | Добавляет роли и каналы на текущий сервер. |
| `/paste id:<id> wipe:true` | **Администратор** | Сначала удаляет существующее, затем клонирует. |

## Две реализации

Выбирайте стек под себя — обе версии полностью равнозначны:

| | Стек | Папка | Запуск |
| --- | --- | --- | --- |
| 🐍 | Python 3.10+ / discord.py 2.x | `python/` | `pip install -r requirements.txt && python bot.py` |
| 🟢 | Node.js 18+ / discord.js 14.x | `node/` | `npm install && npm start` |

Обе читают и пишут **один формат конфига**, поэтому можно сделать `/copy`
Python-ботом, а `/paste` — Node-ботом, и наоборот.

## Безопасность

- `/copy` требует права **Управление сервером**, `/paste` — **Администратор**.
- `/paste` всегда показывает подтверждение, а разрушительный режим `wipe`
  выключен по умолчанию.
- Роли выше собственной роли бота и управляемые роли (ботов, интеграций,
  бустеров) не трогаются — это правило иерархии прав самого Discord.
- ID конфига проверяется по фиксированному алфавиту и длине до чтения файла,
  поэтому через ID нельзя добраться до произвольных файлов (path traversal).

## Формат конфига (схема v2)

Битовые маски прав хранятся как десятичные **строки**, а не числа. Значения
прав Discord превышают предел точных целых чисел в JavaScript (2⁵³): например,
`1152921504606846975` в виде JSON-числа превратился бы в
`1.152921504606847e+18` и права сломались бы молча. Строки решают это и заодно
делают обе реализации взаимозаменяемыми. Числовые маски старого формата (v1)
по-прежнему читаются.

**Копируется:** роли (права, цвет, hoist, упоминаемость, порядок), права
`@everyone`, категории, текстовые/голосовые/трибунные/форумные каналы с темой,
NSFW, медленным режимом, битрейтом и лимитом, а также права по ролям на каждом
канале.

**Не копируется:** сообщения, участники, персональные права участников,
инвайты, эмодзи, баны и любые секреты.

## Установка

Полные инструкции — в [README.md](README.md) (English) и
[README.ru.md](README.ru.md) (Русский).

Боту при добавлении нужны скоупы `bot` и `applications.commands`, а также права
**Управление ролями** и **Управление каналами**. Из-за иерархии ролей поднимите
роль бота **выше** тех ролей, которые он должен создавать или удалять.

> ⚠️ Используйте бота только на серверах, которыми владеете или управляете.
> Режим `wipe:true` необратим.

---

# discord-coper v1.0.0 (English)

First release. A Discord bot that copies a server's **structure** — roles,
categories, channels and per-channel permissions — and rebuilds it on another
server.

## Usage

1. Invite the bot to the **source** server → `/copy`. It returns a short
   **config ID** and attaches the config as a JSON file.
2. Invite the bot to the **target** server → `/paste id:<ID>`. After a
   confirmation prompt it recreates the structure.

| Command | Who | What it does |
| --- | --- | --- |
| `/copy` | **Manage Server** | Snapshots the server, returns an ID + JSON. |
| `/paste id:<id>` | **Administrator** | Adds the roles & channels to this server. |
| `/paste id:<id> wipe:true` | **Administrator** | Deletes existing items first, then clones. |

## Two implementations

| | Stack | Folder | Run |
| --- | --- | --- | --- |
| 🐍 | Python 3.10+ / discord.py 2.x | `python/` | `pip install -r requirements.txt && python bot.py` |
| 🟢 | Node.js 18+ / discord.js 14.x | `node/` | `npm install && npm start` |

Both read and write the **same config format**, so a config copied by one bot
can be pasted by the other.

## Safety

- `/copy` requires **Manage Server**; `/paste` requires **Administrator**.
- `/paste` always confirms first, and the destructive wipe is opt-in.
- Roles above the bot's own role and managed roles are never touched.
- Config IDs are validated before any file read, preventing path traversal.

## Config format (schema v2)

Permission bitfields are stored as decimal **strings**, not numbers: Discord's
permission values exceed JavaScript's safe-integer limit (2⁵³), so
`1152921504606846975` stored as a JSON number would silently become
`1.152921504606847e+18`. Strings keep both implementations exact. v1 numeric
bitfields are still accepted.

**Copied:** roles, `@everyone` permissions, categories, text/voice/stage/forum
channels with their settings, and role-based permission overwrites.

**Not copied:** messages, members, member-specific overwrites, invites, emojis,
bans, secrets.

> ⚠️ Only use this on servers you own or administer. `wipe:true` is
> irreversible.

**Full changelog:** [CHANGELOG.md](CHANGELOG.md) · **License:** MIT
