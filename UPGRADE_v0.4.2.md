# Rat Rod Racing Bot v0.4.2 — Upgrade Notes

**Release:** 2026-10-04  
**Theme:** Race Rules, Tournament Integrity & Reliability

This release fixes race classification/scoring and hardens tournament and post-race persistence before the next feature update.

## Upgrade

1. Stop the bot.
2. Back up your current `rat_rod_racing.sqlite3` and `.env`.
3. Copy the v0.4.2 source files over the existing project. Do **not** replace your `.env` or database with files from the ZIP.
4. Keep your existing large `assets/` folders if you maintain them locally; the release can run without optional art and falls back cleanly.
5. Install/update requirements if needed: `pip install -r requirements.txt`.
6. Start the bot normally. Database migration is automatic and idempotent.

## Database migration

On first v0.4.2 startup:

- `races.schedule_race_number` is added when missing, separating saved scheduled progress from manual tournament races.
- `race_processing` is created to make post-race progression idempotent by `race_id`.
- a unique scheduled-race index prevents the same tournament schedule slot being completed twice.
- obsolete `winner_time` / `best_time` track records are removed because they mixed race lengths and could be set by DNFs.

A v0.4.1 database can be opened directly by v0.4.2; no manual SQL is required.

## Race rules

- Classification: **finishers → DNF → DSQ**.
- DNFs and DSQs score **0 championship points**.
- Failed cars never count as a win or podium and cannot drive First Win, podium sponsor offers, winner interviews, winner newspaper headlines or timing records.
- DNFs retain small participation/action XP; DSQs receive only minimal participation/action XP.
- Timing records exclude failed cars. Each track now stores:
  - Fastest Lap
  - Fastest 5-Lap Race
  - Fastest 7-Lap Race
  - Fastest 10-Lap Race

## Tournament integrity

- A tournament can contain at most 10 teams.
- A tournament race requires exactly all 10 entered teams.
- Manual tournament races no longer consume scheduled race numbers.
- `/tournament_next_race` finds the first uncompleted scheduled slot.
- The final scheduled race atomically saves Season History and closes the tournament before final presentation.
- `/tournament_close` performs the same finalisation path and refuses to finalise a tournament that has never raced.

## Reliability

- Post-race profiles, rivalries, XP, achievements, sponsors, fatigue and track records are written in one transaction and marked processed by race ID. A retry cannot double-award them.
- Re-running database initialisation reuses the existing connection instead of leaking another SQLite connection.
- Active-race/lobby locks stop a team being placed in overlapping lobbies/races and stop concurrent races for the same tournament.
- Dynamic GIF rendering/cache maintenance runs in worker threads instead of blocking Discord's event loop.
- Generated GIF cache files are age/size pruned.
- Malformed `data/media_registry.json` falls back to defaults.
- Invalid `RACE_TICK_SECONDS` falls back/clamps safely to the 0–30 second range.
- Missing optional menu/admin artwork no longer leaves dead attachment references.

## Repository cleanup

`__pycache__/`, `*.pyc`, `.env`, SQLite databases, IDE data, backups and generated GIF smoke output remain ignored. The obsolete `cogs/teamsold.py` has been removed.

## Tests

Run the v0.4.2 regression suite with:

```bash
python -m unittest discover -s tests -v
```

The suite covers the race rules, tournament scheduling/finalisation, post-race idempotency, DB re-init, activity locks, media hardening and cache cleanup.
