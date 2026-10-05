# Rat Rod Racing Bot v0.4.4 — Race Presentation & Strategy

**Release:** 2026-10-05  
**Upgrade from:** v0.4.3

v0.4.4 deliberately keeps the v0.4.3 race balance model intact. It adds presentation, race-state visibility and qualitative setup guidance around the existing deterministic simulation.

## Upgrade

1. Back up your existing bot folder and SQLite database.
2. Copy the v0.4.4 files over the existing installation.
3. Keep your existing `.env`, SQLite database and large local `assets/` folders.
4. Install/update dependencies with `python -m pip install -r requirements.txt`.
5. Start the bot normally with `python main.py`.

There is no required database migration for v0.4.4.

## Race presentation changes

- Pre-race confirmation now shows track character, weather, race length, broad car strengths, Mechanical Strain, Tuning Efficiency and qualitative setup notes.
- Race phases are surfaced as **Start → Opening Laps → Mid-Race → Pit Window → Closing Laps → Final Lap**.
- Live leaderboard snapshots appear at sensible checkpoints rather than every lap.
- Leaderboards show estimated gap-to-leader plus damage, tyre wear and strain state.
- Pit stops record service quality, approximate time loss and the resulting position swing through the pit cycle.
- Major live events can include a short **Why** explanation describing the relevant driver/car/crew factors without exposing the underlying formula.
- Final classification explicitly separates official finishers, DNFs and DSQs and includes failure explanations where available.
- Fastest lap is called out on the official classification.
- New track-record notifications are posted explicitly even when the Blacktop Gazette image is rendered.

## Competitive integrity

v0.4.4 does **not** change the v0.4.3 balance probabilities. A 300-race deterministic parity sample produced the exact same results hash in v0.4.3 and v0.4.4:

`f3f4fe81e5e17bea226709002b902f65b6d4d59548a06d7c4ba7937f951fe440`

The v0.4.3 Balance Lab remains the competitive baseline and is still part of the regression suite.

## Tests

The release adds `tests/test_v044_presentation.py`, covering:

- ordered phase progression for 5/7/10-lap races,
- sparse live leaderboard checkpoints,
- deterministic leaderboard context,
- pre-race qualitative setup information,
- final fastest-lap / DNF / DSQ reporting,
- pit service context,
- unchanged deterministic results.

## Artwork

No new artwork is required. Existing GIF/media fallbacks continue to work when optional large art folders are not present.
