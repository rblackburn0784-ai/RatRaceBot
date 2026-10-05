# Rat Rod Racing Bot v0.4.7 — Championships & Season Structure

v0.4.7 turns the existing tournament engine into a proper season layer while preserving the v0.4.3 competitive model and the v0.4.2 race-integrity rules.

## Blacktop Championship Hub

Use `/championship` to open the public season overview. The hub shows:

- completed rounds / total scheduled rounds,
- the next venue,
- the full points table,
- wins, podiums and race-fastest-lap totals,
- recent form (`W`, `P2`, `DNF`, `DSQ`, etc.),
- mathematical title status,
- top-two head-to-head results,
- current rivalry heat between entered teams,
- recent/next calendar rounds.

The viewing surface is public. Tournament creation, entries, race control and closure stay admin-only.

## Official rounds vs exhibitions

A saved tournament schedule now defines the official championship.

- `/tournament_next_race` runs an official scheduled round and affects standings, carryover damage and season statistics.
- `/tournament_start_race` inside a scheduled championship is an **exhibition**. It is stored in race history, but does not alter championship points, fastest-lap totals, carryover damage or schedule progress.
- Tournaments with no saved schedule keep the legacy/manual behaviour: manually started tournament races still score.

Existing pre-v0.4.7 tournament races are grandfathered as championship races because they may already have affected standings.

## Title mathematics

The Championship Hub calculates the maximum remaining score from the current calendar. It can report:

- who is still mathematically alive,
- when the title is already clinched,
- the leader's gap,
- a guaranteed next-round clinch condition when one exists (for example, **P2 or better**).

These calculations do not change scoring. The points system remains 10 points for P1 down to 1 for P10; DNFs and DSQs score zero.

## Season statistics

`fastest_laps` is now a persistent tournament stat. Only official finishers can receive a race fastest lap. The value is shown in standings, the Championship Hub and end-of-season awards.

Recent form and head-to-head records are derived from official championship rounds only. Exhibition races are intentionally ignored.

## Season awards

When a championship closes, the following awards are permanently snapshotted:

- Champion
- Runner-Up
- Most Wins
- Most Podiums
- Fastest Driver (most race fastest laps)
- Overtake King
- Cleanest Team
- Dirtiest Team
- Most Reliable
- Best Pit Crew
- Giant Killer
- Hard Luck Award

Best Pit Crew uses actual saved pit-stop context (Fast/Solid/Botched service, position movement and time cost), not a raw permanent crew-stat bonus.

## Permanent Season History

`season_history` now stores:

- expanded final standings,
- the full awards board,
- championship race count,
- scheduled/completed round counts,
- season state (`complete`, `shortened`, or `manual`),
- aggregate overtakes, crashes, DNFs and DSQs.

The final scheduled round still closes the championship automatically. Manual close remains available; if rounds are still outstanding, the season is explicitly recorded as **Shortened** rather than pretending the calendar was completed.

## Competitive integrity

v0.4.7 does not alter RaceEngine pace, hazards, overtaking, pit probabilities, sponsor mechanics, parts, crew or driver-stat formulas. The Balance Lab remains the release gate.
