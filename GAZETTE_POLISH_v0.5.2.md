# v0.5.2 — Blacktop Gazette Polish

This is a presentation-only update. Race simulation, progression, championships and balance are unchanged.

## Layout rules

The Gazette now formats content before drawing it.

- Every panel has a fixed logical/rendered line budget.
- Long story fields are truncated before they reach PIL.
- Long team names are abbreviated for compact panels.
- Section header height, internal padding and body line spacing use shared constants.
- Optional/fallback copy is intentionally short.

## Race Recap

Race type, race number, track, weather and championship/exhibition context no longer consume recap rows.

Those details live in the masthead/stamp area instead.

The recap is always capped at five lines:

1. Winner
2. Biggest move
3. Hardest hit
4. Most questionable
5. Pit hero

## Race Order / Final Standings

- Exhibition, quick and demo races use **RACE ORDER**.
- Scheduled championship rounds retain **FINAL STANDINGS**.
- Only the top five classified cars are shown in the newspaper panel.
- Driver names are omitted from the compact classification panel so team/result text remains aligned.
- The template standings body is redrawn before results are added, preventing the old pre-printed 6–10 rows from showing through.

The full official classification is still posted separately in Discord after every race.

## Panel budgets

The main display caps are:

- Race Recap: 5
- Race Order / Final Standings: 5
- Race Awards: 8
- Crowd Hype: 6
- Track Records: 5
- Rivalry Watch: 4
- New Achievements: 5
- Sponsor Offers: 3
- Prediction Results: 2
- Big Move: 1

Winner quotes and compact story panels also use rendered-line caps.

## Short fallbacks

Examples:

- “No new records.”
- “No active grudge.”
- “No new badges.”
- “No sponsor movement.”
- “No correct picks.”

These are deliberately short so an empty section cannot distort the page.

## Competitive integrity

No race-performance values or probabilities are changed by v0.5.2.
