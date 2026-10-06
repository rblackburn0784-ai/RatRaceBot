# Upgrade to v0.5 — Blacktop Racing World

## Before upgrading

1. Stop the bot cleanly.
2. Keep a copy of the existing SQLite database and `.env`.
3. Keep your local media/assets folders.
4. If upgrading from v0.4.9, retain the `backups/` directory and recovery checkpoints.

## Upgrade

1. Replace the source with v0.5.
2. Start the bot normally.
3. Database migration runs automatically and idempotently.
4. Run `/validate_database`.
5. Run `/admin_health`.
6. Open `/world` for a linked team.

## What migration adds

v0.5 adds the `team_season_history` table.

On startup, the bot reads existing frozen `season_history` records and backfills permanent per-team season records. This means championships completed before v0.5 remain part of team careers.

## Recovery compatibility

v0.4.9 race checkpoints and backup/restore features remain supported.

If a closed tournament is restored, v0.5 removes both:

- its global `season_history` snapshot
- its per-team `team_season_history` rows

Finalising it again recreates consistent history.

## Gameplay compatibility

v0.5 does not reset:

- teams
- parts
- crew
- setups
- XP / levels
- achievements
- sponsors
- rivalries
- races
- championship history
- world events

It also does not add a veteran base-stat bonus. Progression continues to unlock choices rather than guaranteed pace.
