# Rat Rod Racing Bot v0.4.1 — Upgrade Notes

This is a stabilisation update for the v0.4 codebase.

## Important: keep your local runtime files

The release ZIP intentionally does **not** contain your live `.env`, SQLite database, `.venv`, IDE files, Git metadata, backups, or generated smoke-test files.

To upgrade an existing install:

1. Back up your current folder and `rat_rod_racing.sqlite3`.
2. Copy the v0.4.1 files over your existing project.
3. Keep your existing `.env` and database in place.
4. Run `pip install -r requirements.txt` in your virtual environment.
5. Start the bot normally with `python main.py`.

The database migration is automatic. On first v0.4.1 startup, the `races` table gains a nullable `replay_json` column used by new exact replay snapshots.

## Git security cleanup

`.gitignore` now excludes `.env` and SQLite runtime databases, but files already tracked by Git stay tracked until removed from the index. Run this once in your existing repository:

```bash
git rm --cached .env
git rm --cached rat_rod_racing.sqlite3
git add .gitignore
git commit -m "Stop tracking local secrets and runtime database"
```

A Discord token existed in the uploaded repository history. Make sure any token that was ever committed has been revoked/regenerated in the Discord Developer Portal. Removing it from the current files does not erase old Git history.

## v0.4.1 changes

- New races save complete replay snapshots: team stats, car archetypes, fitted parts, pit crew, team order, lap count, tournament carry-over damage, and weather identity.
- `/race_replay` uses the saved snapshot when available and no longer awards XP, achievements, sponsor offers, fatigue, career stats, rivalries, or track records.
- Pre-v0.4.1 races remain replayable in legacy mode using their saved seed and current team builds.
- Closed tournaments reject new teams and race starts at both command and database layers.
- Tournament standings updates and race persistence are committed atomically.
- Team deletion now cleans related live profile/progression/achievement/sponsor/fatigue/rivalry data in one transaction.
- Historical track records are retained when a team is deleted, but their live `team_id` link is cleared.
- Illegal parts now apply the documented +6% pre-race disqualification risk per fitted illegal part only; that risk is no longer added again to every lap's illegal-move chance.
- `lap_save_*` media keys now fall back to `damage_minor.gif` when dynamic artwork or dedicated near-miss GIFs are absent.
- `.gitignore` additionally excludes `.idea/`, `backups/`, and `tmp_gif_smoke/`.

## Artwork note

This release preserves the existing media lookup/fallback behaviour. The uploaded project intentionally omitted some large art assets, particularly dynamic track/car PNGs. Missing optional art does not prevent the bot from starting; prebuilt generic/colour GIF fallbacks are used where available.
