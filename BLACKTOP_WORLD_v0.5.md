# v0.5 — Blacktop Racing World

v0.5 is the first persistent-world release.

The design goal is that the bot feels like a Rat Rod racing game living inside Discord, while preserving the competitive-integrity rule established in v0.4.3:

> Progression gives a team more choices, not an automatic victory.

## Core loop

Create Team  
→ Build Driver + Car  
→ Hire Crew  
→ Enter Garage  
→ Prepare Track Setup  
→ Race  
→ Earn XP / Reputation / Sponsors  
→ Develop Rivalries  
→ Championship  
→ Blacktop Gazette  
→ Season Awards  
→ Permanent Team History  
→ Next Season

## World Hub

Use `/world`.

The World Hub gathers the existing systems into one screen instead of replacing them. It shows:

- team title, level and XP
- driver/car identity and reputation
- fitted-part and crew readiness
- saved track setup count
- Mechanical Strain and illegal-hardware risk
- active sponsor and waiting offers
- pending Blacktop World decisions
- hottest rivalry
- current championship position, points and next scheduled round
- permanent season totals and championship career record
- a Recommended Next action

World Hub controls open the existing Garage, Pit Crew, Race Wizard, Sponsor Paddock and Championship systems.

## Permanent team history

Every completed championship freezes one record per participating team in `team_season_history`.

The frozen record contains:

- championship/tournament ID and season name
- final position
- points
- wins
- podiums
- fastest laps
- awards won that season
- the saved season summary
- completion timestamp

These records are separate from the live mutable team profile. Changing a car, driver title, sponsor or future results does not rewrite old seasons.

Existing completed v0.4.x seasons are backfilled from `season_history` during database migration.

## Next season

Closing one championship does not reset the team.

The same persistent team can enter a later championship with:

- its accumulated XP
- unlocked setup capacity
- identity/cosmetics
- achievements
- sponsor history/current contract
- rivalry history
- career statistics
- permanent past-season record

A new season starts with fresh championship standings, so veteran career history does not become free championship points.

## Gazette archive

The World Hub Gazette view surfaces recent persisted races involving the selected team.

The post-race Blacktop Gazette remains the dramatic race report; the archive provides continuity back into earlier saved races.

## World decisions

Pending world events can be resolved directly with **Choose A** / **Choose B** buttons.

They remain story-first decisions and do not secretly alter raw car stats, driver stats or championship points.

Duplicate or stale clicks:

- do not resolve the event twice
- return an explicit ephemeral message
- do not produce a silent Discord interaction failure

## UI reliability

All interactive bot Views now use a shared error boundary.

Unexpected callback failures:

1. are logged with their traceback;
2. attempt to acknowledge the interaction;
3. tell the user the action could not be completed;
4. advise reopening `/menu` or `/world`.

Destructive confirmation views are one-shot. Existing race activity locks and database transactions remain the source of truth for concurrency.

## Competitive integrity

v0.5 does not add permanent race-performance bonuses for:

- team level
- number of seasons
- championship titles
- career awards
- reputation tags
- World Hub completion

Veterans gain broader strategic and identity options. A correctly prepared new team can still beat them.

The full deterministic Balance Lab remains a mandatory release gate.
