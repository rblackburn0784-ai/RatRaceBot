# v0.4.6 — Progression, Sponsors & Team Identity

v0.4.6 turns the existing XP, sponsor, title and reputation foundations into a coherent long-term team progression loop without introducing permanent level-based horsepower.

## Design rule

**Levels unlock choices, identity and access — not raw speed.**

A Level 10 team does not receive a hidden speed/handling/reliability modifier. Competitive performance still comes from the v0.4.3 car/driver/part/crew trade-off model, track fit, weather and race events.

## Team levels

- 100 XP per level.
- Level 1 through Level 10.
- Existing race XP remains the progression source.
- A level-up is surfaced after race rewards are processed.

### Key unlock milestones

- **Level 1:** 3 garage setup slots; starter identity; County Line Diner sponsor interest.
- **Level 2:** more liveries/emblems; Graveyard Wrench Supply interest.
- **Level 3:** 4th/High-Speed setup slot; custom team intro; Whitewall Radio Hour interest.
- **Level 4:** specialist crew shortlist; Lucky 13 Speed Shop interest.
- **Level 5:** all 5 setup slots including Custom; Moonshine Fuel Co.; established-team Blacktop Gazette recognition.
- **Levels 6–10:** additional veteran/legend cosmetic identity options.

Existing saved setup slots and assigned specialist crew are grandfathered. The bot does not delete an existing choice just because a team is currently below its new progression requirement.

## Team identity

`/team_identity` provides level-gated cosmetic identity choices:

- Liveries
- Team emblems
- Garage decoration
- Custom race intro phrase from Level 3

Identity choices are stored independently in SQLite and are included in replay snapshots where relevant. They do not modify car performance.

## Sponsor contracts

A team may have **one active sponsor at a time**. Sponsor offers are still earned through strong race results; accepting one activates its race effect. A contract can be ended from the Sponsor Paddock before accepting another.

Every sponsor has a real benefit and a real cost:

### County Line Diner — Level 1

**Benefit:** +15% race XP from local-fan promotion.

**Trade-off:** sponsor appearances create a tiny race-focus/pace cost.

### Graveyard Wrench Supply — Level 2

**Benefit:** major pit repairs restore more damage.

**Trade-off:** heavier workshop equipment increases pit-stop timing variance.

### Whitewall Radio Hour — Level 3

**Benefit:** Showmanship has an improved chance to create race momentum.

**Trade-off:** crowd-pleasing driving increases tyre demand.

### Lucky 13 Speed Shop — Level 4

**Benefit:** extra trackside support improves marginal hazard saves.

**Trade-off:** a small outright pace cost; illegal hardware receives closer scrutiny.

### Moonshine Fuel Co. — Level 5

**Benefit:** stronger opening-phase acceleration effect during the first two laps.

**Trade-off:** greater heat pressure and closer scrutiny of illegal hardware.

Sponsors are intentionally small situational modifiers. They are not intended to replace good setup choices or create a dominant team.

## Specialist crew progression

The strongest specialist candidate in each pit-crew role becomes newly recruitable from Level 4. Existing specialist assignments are grandfathered so upgrading from an older save cannot unexpectedly remove staff.

## Garage progression

Saved setup capacity grows with the team:

- Levels 1–2: Street, Dirt, Wet
- Levels 3–4: + High-Speed
- Level 5+: + Custom

Loading an existing grandfathered setup remains allowed. Saving into a not-yet-unlocked new slot is blocked until the required level.

## Competitive-integrity guardrail

`tools/balance_lab.py` now tests every active sponsor against nine equivalent independent teams across the track set. The release guardrail rejects any sponsor whose solo win rate exceeds the sponsor-dominance ceiling.
