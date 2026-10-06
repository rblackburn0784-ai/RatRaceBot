# v0.4.8 — Rivalries, Stories & Racing World

v0.4.8 turns persistent race history into a living paddock story without turning grudges into a second stat system.

## Rivalry heat

Rivalry heat now uses a public **0–100** scale and is driven by actual race interactions whenever actor/target data is available.

Typical heat signals:

- Overtake against the same rival: **+1**
- Repeated overtakes in one race: small additional escalation, capped at **+3**
- Close classified finish within five seconds: **+2**
- Illegal contact: **+4**
- Targeted minor/major contact events: **+2 / +3**
- Championship battle between close title contenders: **+2**
- Final-lap stolen win against the passed rival: **+6**
- Explicitly attributed caused DNF: **+8**

Existing rivalry history is preserved and normalised to the new 0–100 scale.

### High-heat behaviour

- **50+ heat:** live overtake/illegal-move commentary starts calling out the rivalry.
- **70+ heat:** commentary treats the feud as boiling over.
- Hot rivals racing within two positions can be preferred as the contextual rival for an incident.
- The only gameplay nudge is deliberately tiny: at 50+ heat, illegal-contact pressure receives at most **+0.8 percentage points** at 100 heat.
- Rivalry heat never grants speed, handling, reliability, points or a direct race-performance bonus.

/rivalry_story shows richer rivalry history with heat bars, overtakes, contacts, illegal incidents, championship battles, stolen wins and caused DNFs.

## Dynamic Blacktop Gazette

The post-race **BLACKTOP GAZETTE** now builds its story from the saved race and championship state.

Coverage includes:

- dynamic headline
- race winner
- current championship situation
- biggest move
- crash/scandal angle
- hottest rivalry story
- pit-lane quote
- sponsor story
- upcoming scheduled race

The existing newspaper image renderer remains in place. If the image template/Pillow path is unavailable, the Discord embed fallback still carries the same race story.

## Racing world events

After a persisted race there is a deterministic **24%** chance of one low-impact world event being created for one participating team.

Possible events:

- Garage Break-In
- Sponsor Dispute
- Local Newspaper Hype
- Crew Argument
- Surprise Inspection
- Engine Supplier Breakthrough
- Bad Weather Forecast
- Track Repairs

These are **choices, not random punishment**. They do not secretly alter driver stats, car stats, championship points or race probabilities.

Use:

- /world_events to see pending decisions for your linked team.
- /world_event_choose event_id:<id> choice:A|B to resolve one.
- Admins may inspect a specific team by ID.

## Replay integrity

New replay snapshots store the rivalry heat map that existed when the race was run. Replaying that race therefore uses the original rivalry context rather than whatever grudges happen to exist later.

Older replay snapshots remain supported and default to no rivalry gameplay nudge because they never recorded historical rivalry state.

## Persistence

v0.4.8 adds three SQLite tables on first use:

- rivalry_story_stats
- racing_world_processed
- world_events

The migration is automatic and idempotent.
