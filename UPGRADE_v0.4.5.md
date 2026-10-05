# Rat Rod Racing Bot v0.4.5 — Garage, Parts & Crew Gameplay

**Release:** 2026-10-05

## Upgrade

1. Back up your bot folder and SQLite database.
2. Copy the v0.4.5 source over the existing installation.
3. Keep your existing `.env`, live SQLite database and local artwork/media folders.
4. Run `pip install -r requirements.txt`.
5. Start the bot normally.

The database migration is automatic. v0.4.5 adds a `team_setups` table for garage presets; existing teams, races, tournaments, parts and crew are preserved.

## Garage gameplay

- `/my_team` now opens **THE GARAGE** dashboard instead of the older summary panel.
- The garage shows every hardware slot, Mechanical Strain, Tuning Efficiency, illegal-hardware risk and broad **Fast / Technical / Wet / Rough** setup ratings.
- Players get direct buttons for **Fit Part**, **Remove Part**, **Compare Part**, **Save Setup**, **Load Setup**, **Ask Crew Chief** and **Pit Crew**.
- The Parts Wizard can replace a part in one step. You no longer need to remove the old part before fitting an alternative in the same slot.
- Part comparison shows expected setup-rating changes together with strain, tuning-efficiency and DSQ-risk changes before fitting.

## Saved setups

Each team can persist five named hardware presets:

- Street
- Dirt
- Wet
- High-Speed
- Custom

Saving a preset stores the currently fitted **parts only**. Loading a preset replaces the car's current hardware but deliberately leaves the team's pit crew unchanged. This makes track/weather setup changes quick without unexpectedly changing personnel.

If a future release removes or renames a saved part, the loader safely ignores the unknown entry rather than failing the whole preset.

## Crew gameplay

Crew remain situational specialists rather than permanent car-stat stacking:

- **Crew Chief** — strategy, coordination and control.
- **Lead Mechanic** — repairs, Mechanical Strain management and fragile-build support.
- **Tyre Changer** — tyre life, pit tyre recovery and aggressive-driver support.
- **Fuel Runner** — heat management and pit support.
- **Spotter** — traffic awareness, attack support and collision/hazard avoidance.

The crew wizard now explains these roles in player-facing language. Major race-event `Why` notes can also name the relevant assigned specialists, making crew contribution visible without changing the underlying v0.4.3 balance formula.

## Balance guarantee

v0.4.5 changes garage interaction and crew visibility. It does **not** change race probability or performance formulas. A 300-race deterministic parity check against v0.4.4 produced the same result hash:

`6c6da6824c3596192057d54aeb477b7fa18d40272c044e51abbde95ef02e6536`

The v0.4.3 Balance Lab remains the competitive-integrity gate.
