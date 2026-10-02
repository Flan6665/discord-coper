# Changelog

All notable changes to this project are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-02

First release.

### Added
- `/copy` — snapshots a server's roles, categories, channels and per-channel
  permission overwrites, saves them under a short 8-character ID, and returns
  that ID plus the config as a downloadable JSON file.
- `/paste id:<id>` — rebuilds a saved structure on another server, adding to
  whatever is already there.
- `/paste id:<id> wipe:true` — deletes the existing channels and roles the bot
  can reach first, producing a clone.
- **Node.js implementation** (`node/`, discord.js 14) alongside the
  **Python implementation** (`python/`, discord.py 2). Both read and write the
  same config format, so they are interchangeable.
- Documentation in English (`README.md`) and Russian (`README.ru.md`).
- MIT license.

### Safety
- `/copy` requires the **Manage Server** permission; `/paste` requires
  **Administrator**.
- `/paste` always shows a confirmation prompt, and the destructive wipe is
  opt-in rather than the default.
- Roles above the bot's own role, and managed (bot/integration/booster) roles,
  are never touched — enforced by Discord's role hierarchy.
- Config IDs are validated against a fixed alphabet and length before any file
  is read, so an ID cannot be used for path traversal.

### Notes
- Config schema version 2: permission bitfields are stored as decimal strings
  rather than JSON numbers, because Discord permission values exceed
  JavaScript's safe-integer limit (2^53) and would otherwise be corrupted.
  Readers still accept v1 numeric bitfields.
