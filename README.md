# discord-coper

**🇬🇧 English** · [🇷🇺 Русский](README.ru.md)

A Discord bot that copies a server's **structure** — roles, categories,
channels, and per-channel permissions — and rebuilds it on another server.

It's the same idea as Discord's built-in *Server Template* feature, but it also
carries voice/stage/forum channels and works across servers you administer
(e.g. migrating a community to a new server, or spinning up a staging copy).

Available in **two interchangeable implementations** — pick whichever stack you
prefer:

| | Language | Library | Folder |
| --- | --- | --- | --- |
| 🐍 | Python 3.10+ | [discord.py](https://discordpy.readthedocs.io/) 2.x | [`python/`](python/) |
| 🟢 | Node.js 18+ | [discord.js](https://discord.js.org/) 14.x | [`node/`](node/) |

Both produce and read the **same config format**, so you can `/copy` with the
Python bot and `/paste` with the Node one, or vice versa.

## How it works

1. Invite the bot to the **source** server and run `/copy`.
   It snapshots the server and replies with a short **config ID** plus the
   config as a downloadable JSON file (your "server configuration file":
   roles with their permissions and order, channels, and who can see what).
2. Invite the bot to the **target** server and run `/paste id:<the-id>`.
   After a confirmation prompt it recreates everything.

### Commands

| Command | Who can run it | What it does |
| --- | --- | --- |
| `/copy` | Members with **Manage Server** | Snapshots the current server, returns an ID + JSON file. |
| `/paste id:<id>` | Members with **Administrator** | Adds the copied roles & channels to the current server. |
| `/paste id:<id> wipe:true` | Members with **Administrator** | Deletes existing channels/roles first, then clones (asks to confirm). |

## What is and isn't copied

**Copied:** role names, permissions, colour, hoist, mentionable, and order;
`@everyone` permissions; categories; text/voice/stage/forum channels with their
topic, NSFW flag, slowmode, bitrate and user limit; and role-based permission
overwrites on each channel.

**Not copied:** messages, members, member-specific permission overwrites,
invites, emojis, bans, or any secret. Managed roles (bot/integration/booster
roles) and roles positioned above the bot's own role are left untouched — this
is a Discord permission rule, not a limitation of the code.

## Setup

First create an application and bot at
<https://discord.com/developers/applications> → **Bot** → copy the token.
Then set up whichever implementation you want.

### 🐍 Python

```bash
cd python
cp .env.example .env          # then edit .env and paste your token
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 🟢 Node.js

```bash
cd node
cp .env.example .env          # then edit .env and paste your token
npm install
npm start
```

### Inviting the bot

Generate an invite URL under **OAuth2 → URL Generator** with the `bot` and
`applications.commands` scopes. The bot needs **Manage Roles** and **Manage
Channels** (grant **Administrator** if you want it to clone a full server
including high-permission roles). Because of Discord's role hierarchy, drag the
bot's role **above** the roles it should be able to recreate or delete.

## Config format

Configs are JSON, stored under each implementation's `configs/` folder and
keyed by an 8-character ID. Permission bitfields are stored as decimal
**strings**, not numbers — Discord's permission values exceed JavaScript's
safe-integer limit (2⁵³), so storing them as numbers would silently corrupt
them. This is also what makes the two implementations interchangeable.

```jsonc
{
  "schema_version": 2,
  "source_guild_name": "My Server",
  "everyone_permissions": "104324673",
  "roles": [
    { "name": "Admin", "permissions": "1152921504606846975",
      "color": 16711680, "hoist": true, "mentionable": false, "position": 5 }
  ],
  "categories": [
    { "name": "Staff", "position": 0,
      "overwrites": [ { "role": "@everyone", "is_default": true,
                        "allow": "0", "deny": "1024" } ],
      "channels": [
        { "name": "general", "type": "text", "position": 0,
          "topic": "hi", "nsfw": false, "slowmode_delay": 5, "overwrites": [] }
      ] }
  ],
  "uncategorized_channels": []
}
```

## Notes & limits

- The `configs/` folders are git-ignored; treat the IDs as private.
- Only act on servers you own or administer. Running `wipe:true` is
  irreversible — the bot confirms first, but there is no undo.
- Very large servers may hit Discord's API rate limits; both libraries handle
  the backoff automatically, so a big clone just takes a little longer.

## License

[MIT](LICENSE)
