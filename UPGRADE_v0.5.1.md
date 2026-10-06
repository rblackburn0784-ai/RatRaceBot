# Upgrade to v0.5.1 — World Reliability Patch

## Before upgrading

1. Stop the bot cleanly.
2. Keep a copy of the SQLite database, `.env`, media assets and `backups/`.
3. Replace the source with v0.5.1.
4. Start the bot.
5. Run `/validate_database`.
6. Run `/admin_health`.

## Multiple open seasons

v0.5.1 refuses to create a new championship while another is open.

If an older database already contains multiple open tournaments, the bot does not silently choose which one to close. `/validate_database` reports the inconsistency so an admin can decide which championship should remain active. An empty/partial duplicate with no scoring races can be cancelled safely with `/tournament_close`; it will be marked cancelled without creating Season History.

## Tournament Wizard

New wizard-created championships are all-or-nothing: tournament row, 10 teams and schedule commit together.

## Media

Local media folders are still supported and may remain outside GitHub.

If MP3 files are supplied through `data/media_registry.json` or `assets/audio/`, race presentation now attaches the matching playable audio file to Discord event messages. Missing files simply fall back to GIF/text.

## Python

v0.5.1 is release-tested on Python 3.12 and Python 3.13.
