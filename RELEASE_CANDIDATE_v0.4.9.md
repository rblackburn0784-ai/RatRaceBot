# v0.4.9 — Polish, Administration & Release Candidate

v0.4.9 is the v0.5 release candidate. It deliberately adds no new gameplay systems.

## Recovery policy

Recovery is conservative by design:

- Every persisted v0.4.9 race receives an automatic SQLite checkpoint immediately before the race is saved.
- Race persistence is serialised only across checkpoint → save → post-race effects, then the lock is released before Discord presentation.
- Undo, Reprocess and Correct Result only rewrite the **latest saved race** and require its v0.4.9 checkpoint.
- Older races are refused rather than silently invalidating later progression, sponsors, rivalries or championship state.
- Every destructive recovery action creates a safety backup first.
- Backups are created with SQLite's live backup API rather than copying an open database file.
- Restore Backup validates SQLite integrity before replacing the live database.

## Recovery commands

- `/undo_last_race confirm:true` — restores the automatic pre-race checkpoint for the latest race.
- `/reprocess_race race_id:<id> confirm:true` — restores the checkpoint, reinserts the same latest race, and processes its effects exactly once.
- `/correct_result race_id:<id> team_id:<id> new_position:<n> status:<...> confirm:true` — rebuilds the latest race with corrected classification.
- `/restore_tournament tournament_id:<id> confirm:true` — reopens a closed tournament and removes its final Season History snapshot.
- `/resume_interrupted_race [race_id]` — continues saved presentation from the last successfully posted event without resimulating.
- `/repair_team_data team_id:<id> confirm:true` — repairs invalid archetype/stats/parts/crew/sponsor/setup/identity references.
- `/validate_database` — runs SQLite integrity plus Rat Rod domain checks.
- `/backup_database` — creates a consistent timestamped backup.
- `/restore_backup backup_name:<file> confirm:true` — validates and restores a backup, keeping a pre-restore safety copy.

## Diagnostics

`/admin_health` reports:

- bot state
- database integrity
- loaded slash command count
- configured/direct media availability
- current open tournament
- active race/team state
- backup count
- interrupted presentations
- release regression status
- Balance Lab release-gate status
- database issues/warnings

## Interrupted races

The simulation still completes and persists before Discord presentation. v0.4.9 now records the last successfully streamed event index. A process/network interruption can therefore resume presentation without generating a second result or duplicating rewards.

## Automated release gate

Every pull request to `main`, every push to `main`, and the v0.4.9 release branch run:

1. dependency installation
2. Python compile pass
3. full pytest regression suite
4. full deterministic Balance Lab

The Balance Lab remains a release gate rather than a gameplay feature.
