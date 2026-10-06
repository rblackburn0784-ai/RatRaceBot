# v0.5.1 — World Reliability Patch

v0.5.1 does not add gameplay. It hardens the v0.5 Blacktop Racing World for live Discord seasons.

## Single active championship

Only one tournament may be open at a time.

The rule is enforced inside the database transaction, so simultaneous admin clicks cannot create two active seasons. Existing databases that already contain multiple open tournaments are reported as a database-integrity failure by `/validate_database`.

## Atomic Tournament Wizard

The Tournament Wizard now creates the tournament, all 10 entrants and the full schedule in one transaction.

If any team disappeared, the name conflicts, the schedule is invalid, or any insert fails, the transaction rolls back and leaves no partial tournament behind.

## Command errors

Permission/check failures that already supplied a user-facing explanation are no longer followed by a second generic error message.

Unexpected command errors are still logged and acknowledged with a recovery-oriented message.

## Admin Health

`/admin_health` now verifies an explicit manifest of 59 slash commands instead of comparing the runtime command count to itself.

It also reports:

- runtime v0.5.1 versus release metadata
- configured media availability
- current season/race state
- backups and interrupted presentations
- full database table validation count
- release-test and Balance Lab status
- missing or unexpected slash-command names

## Database validation

`/validate_database` now checks all 22 persistent/recovery/world tables and validates:

- SQLite integrity
- JSON payloads
- track keys
- tournament/team/race references
- progression, sponsor, identity, fatigue and setup ownership
- permanent season history
- rivalry and world-event references
- processing and presentation records
- the single-active-season invariant

## Race audio

Configured audio is now actually surfaced during race presentation.

When a matching MP3 exists, the RaceStreamer attaches it to the same Discord event message as the GIF/text. Missing audio remains optional and never blocks a race.

Aliases cover event types that historically used a differently named media key:

- lap → lap_leader
- warning → illegal_move
- last_minute_win → finish_line

Discord attachments are playable by users; Discord does not automatically play audio attachments.

## Stale controls

Reliable Views now remember their source message after interaction and disable all controls when the View expires.

The core `/menu`, `/world`, permanent Team History and Season History screens are explicitly bound to their original Discord messages so timeout cleanup can visibly disable stale buttons.

## Permanent history pagination

Team History now pages through up to 200 stored championship seasons, four seasons per page. The prior eight-season display limit is removed from the interactive World Hub.

## Python versions

The release workflow now runs the full regression suite on both Python 3.12 and Python 3.13. The deterministic Balance Lab remains a mandatory Python 3.12 release gate.

## Competitive integrity

No race-performance values are changed by this patch.
