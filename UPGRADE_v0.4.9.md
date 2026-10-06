# Upgrade to v0.4.9 — v0.5 Release Candidate

## Recommended upgrade

1. Stop the bot cleanly.
2. Keep a copy of the existing SQLite database and `.env`.
3. Replace the source with v0.4.9 while preserving local media/assets.
4. Start the bot. Recovery tables are created automatically and idempotently.
5. Run `/validate_database`.
6. Run `/admin_health`.
7. Create one manual `/backup_database` before the first live tournament under v0.4.9.

## Important recovery boundary

Automatic Undo/Reprocess/Correct checkpoints only exist for races first persisted by v0.4.9 or later. Older races remain readable and replayable, but v0.4.9 will refuse destructive rewrite operations on them because there is no exact pre-race state to restore.

## New persistence

v0.4.9 adds:

- `recovery_log`
- `race_presentation_state`
- automatic checkpoint files under `backups/checkpoints/`

These are administrative/recovery records only; no race gameplay is added.

## Backup notes

Manual backups and automatic recovery checkpoints should be included in your normal server backup policy. Restore operations reject paths outside `backups/` and run SQLite integrity checks before replacement.
