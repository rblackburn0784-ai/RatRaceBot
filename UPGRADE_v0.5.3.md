# Upgrade to v0.5.3 — Season Control & Administration

## Before upgrading

1. Stop the bot cleanly.
2. Keep a copy of the SQLite database, `.env`, assets and `backups/`.
3. Replace source with v0.5.3.
4. Start the bot.
5. Run `/validate_database`.
6. Run `/admin_health`.
7. Open **Season Director** from the admin menu.

## Database migration

v0.5.3 adds two idempotent tables:

- `season_race_state`
- `season_control_log`

Existing races, standings and Season History are not rewritten.

## Paused seasons

A paused championship is considered active for the single-season rule and team locking. It does not permit new races until resumed.

## Reopening a season

Reopen is a recovery action. A safety backup is created first. Existing global and per-team Season History snapshots for that tournament are removed until the season is finalised again.

## Compatibility

v0.5.3 preserves v0.5.2a Gazette alignment and all v0.5.1 recovery/UI hardening. No media or gameplay assets are replaced.
