# v0.5.3 — Season Control & Administration

v0.5.3 finishes the non-graphical championship administration layer before the graphical race-broadcast roadmap begins.

## Season Director

Use `/season_director` or open **Season Director** from the admin menu.

The Director shows:

- season state: Open / Paused / Closed / Cancelled
- completed rounds / total rounds
- current round and next scheduled race
- championship leader
- mathematical title picture
- teams still mathematically eligible
- recent championship form
- latest persistent race-operation state
- whether Season History is pending or complete

## Director controls

- **Start Next Race** — opens the existing race preflight/confirmation flow for the next scheduled round
- **Correct Result** — guided team / finishing position / status correction for the latest recoverable race
- **Pause Season** — stops new championship races while keeping the season active and teams locked
- **Resume Season** — returns a paused season to racing
- **Cancel Empty** — confirmed cancellation for a season with no scoring races
- **End Season** — confirmed finalisation and permanent Season History snapshot
- **Reopen Season** — confirmed recovery action with safety backup; removes the frozen history snapshot until the season is ended again
- **Championship Hub** — opens the public championship view
- **Refresh** — reloads current season state

Destructive operations use confirmation controls.

## Persistent race-operation state

Every scheduled championship round has a durable status row.

Tracked milestones:

1. Race simulated
2. Standings updated / race persisted
3. Rewards processed
4. Gazette generated
5. Season History pending / complete

Failure phases are also persisted, including save errors, reward-processing rollback and report/Gazette delivery errors.

This state is intentionally separate from the visual presentation system so the later sprite/broadcast renderer can depend on a stable race-operation timeline.

## Pause semantics

A paused season still counts as the single active championship.

While paused:

- no scheduled or exhibition tournament race can start
- teams remain locked against tournament-unsafe editing/deletion
- a second championship cannot be created
- Season Director remains available
- Resume or End Season can be used

## Result correction

Season Director uses the existing conservative v0.4.9 recovery model.

Only the latest persisted race with an automatic pre-race checkpoint can be rewritten. A correction restores the pre-race database state, reinserts the corrected result and reapplies progression once.

After a correction, the Director deliberately flags **Gazette generated = false** because the already-posted newspaper reflects the pre-correction classification.

## Competitive integrity

No race-performance formulas, part values, driver stats, sponsor bonuses, championship points table or progression rules change in v0.5.3.
