# Upgrade to v0.4.6 — Progression, Sponsors & Team Identity

## Before upgrading

1. Stop the bot.
2. Back up the current bot folder.
3. Back up the SQLite database separately.
4. Keep your existing `.env` and media/assets folders.
5. Copy the v0.4.6 source files over the existing installation.
6. Install/update dependencies from `requirements.txt`.
7. Start the bot normally.

Do not replace a live database with a blank database from a release package.

## Automatic database migration

v0.4.6 performs additive migrations at startup:

- `teams.active_sponsor_key`
- `sponsor_offers.sponsor_key`
- new `team_identity` table for livery, emblem, garage decoration and custom intro phrase

Existing teams, race history, tournament history, XP, achievements, sponsor offers and garage presets are preserved.

## Existing progression data

Existing XP is converted directly into the v0.4.6 level structure at 100 XP per level, capped at Level 10. There is no reset.

Existing cosmetic titles remain selected. Post-race XP processing no longer replaces a title the player deliberately selected.

## Garage preset grandfathering

v0.4.6 introduces level-based preset capacity:

- Level 1–2: 3 slots
- Level 3–4: 4 slots
- Level 5+: 5 slots

If an older team already has a saved setup in a slot that would now be locked, that saved setup remains loadable. It is not deleted.

## Crew grandfathering

Level 4 introduces the specialist-crew shortlist. Any specialist already assigned before upgrading remains assigned and usable. The level gate only controls newly assigning that specialist.

## Sponsor contracts

Old sponsor offer rows remain visible. New offers include a stable sponsor key and can activate real sponsor effects. Legacy offers without a recognisable sponsor identity may need to be rejected so the team can earn a fresh offer.

Only one sponsor contract can be active at once. Use `/sponsor_offers` to accept/reject offers or end the current contract.

## Balance

Levels themselves add no car stats. Sponsor effects are deliberately situational and include drawbacks. The v0.4.3 Balance Lab remains active and v0.4.6 adds sponsor dominance checks.

## New player-facing command

`/team_identity` — choose unlocked livery, emblem, garage decoration and, from Level 3, a custom race intro phrase.
