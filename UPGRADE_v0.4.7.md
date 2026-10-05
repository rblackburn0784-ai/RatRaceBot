# Upgrade to v0.4.7 — Championships & Season Structure

## Recommended upgrade path

1. Stop the bot cleanly.
2. Back up your SQLite database.
3. Replace the source with v0.4.7 while keeping your `.env`, live database and local media/assets.
4. Start the bot normally. Database migration is automatic and idempotent.
5. Run `/version` and confirm v0.4.7.
6. Open `/championship` for an existing/open tournament to verify the new season view.

## Database migration

v0.4.7 adds:

- `tournament_teams.fastest_laps`
- `races.championship_round`
- `season_history.awards_json`
- `season_history.summary_json`

Existing race rows are grandfathered as championship rounds because old releases may already have applied those results to standings. When the `fastest_laps` column is first added, saved tournament race results are scanned to reconstruct historical fastest-lap counts where possible.

## Behaviour change for scheduled tournaments

If a tournament has a saved calendar, unscheduled/manual tournament races are exhibitions from v0.4.7 onward. They are saved but do not change the championship table, carryover damage, fastest-lap totals or scheduled progress.

Tournaments without a saved calendar keep manual scoring behaviour.

## Closing incomplete seasons

`/tournament_close` still works before the saved calendar is complete, but the confirmation now warns the administrator and Season History records the result as a **Shortened Season**.

## Rollback note

The added columns are backward-compatible SQLite columns, but older bot builds will not understand exhibition-vs-championship markers or the new award/summary snapshots. Keep a pre-upgrade database backup if you need to revert.
