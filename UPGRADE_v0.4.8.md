# Upgrade to v0.4.8 — Rivalries, Stories & Racing World

## Recommended upgrade path

1. Stop the bot cleanly.
2. Back up your SQLite database.
3. Replace the source with v0.4.8 while keeping your .env, live database and local media/assets.
4. Start the bot normally.
5. Run a persisted race or open /world_events once to initialise the v0.4.8 racing-world tables.
6. Use /rivalry_story on a team with race history to verify rivalry data.

## Database changes

v0.4.8 keeps the existing team_rivalries table and adds:

- rivalry_story_stats
- racing_world_processed
- world_events

Existing rivalry heat is preserved and clamped into the new 0–100 display/processing scale. The new tables are created automatically and idempotently.

## Rivalry behaviour change

Older releases inferred rivalries mainly from adjacent classified cars. v0.4.8 instead consumes race-event actor/target information so an overtake or illegal move is attributed to the teams that actually interacted.

The old adjacency-based post-race writer is disabled in the normal reward path to prevent double-counting.

High heat changes commentary and can add only a tiny situational illegal-contact pressure, capped at **+0.8 percentage points** at maximum heat. It does not add raw performance.

## Blacktop Gazette

The existing Gazette renderer is retained, but its headline and story sections now use live race/championship/rivalry/sponsor context. No new image assets are required.

## World events

World events are deliberately low impact. They create a decision and persistent story outcome but do not alter car/driver performance or championship scoring.

## Replay compatibility

New snapshots include the pre-race rivalry heat map. Old v0.4.x snapshots continue to load; because they did not record rivalry state, replays from those snapshots use an empty rivalry map.

## Rollback note

The added tables are non-destructive, but an older bot build will ignore v0.4.8 rivalry-story counters and world-event decisions. Keep a pre-upgrade database backup if you may revert.
