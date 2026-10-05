# v0.4.5 Garage, Parts & Crew Gameplay

v0.4.5 turns team preparation into a player-facing gameplay loop while preserving the v0.4.3 competitive balance model.

## THE GARAGE

`/my_team` opens a garage dashboard showing:

- all eight fitted hardware slots;
- Tuning Efficiency;
- Mechanical Strain and its label;
- illegal-hardware DSQ risk;
- Fast Track, Technical, Wet and Rough setup ratings;
- all five specialist crew positions;
- the status of the five saved setup bays.

The dashboard exposes direct controls for **Fit Part**, **Remove Part**, **Compare Part**, **Save Setup**, **Load Setup**, **Ask Crew Chief**, **Pit Crew**, and **Refresh Garage**.

## Parts bay

The Parts Wizard now treats the selected item as an alternative to the currently fitted part in that slot. Players can compare the two before committing and can replace the current item in one action.

Comparison shows:

- broad setup-rating movement;
- Mechanical Strain before/after;
- Tuning Efficiency before/after;
- illegal DSQ risk before/after;
- the candidate part's stated performance trade-off.

The underlying part balance, tuning-efficiency model, strain model and +6% DSQ risk per illegal part are unchanged.

## Saved setups

Every team has five named hardware preset bays:

1. Street
2. Dirt
3. Wet
4. High-Speed
5. Custom

Presets save **parts only**. The standing pit crew does not change when a setup is loaded.

This is deliberate: the player can prepare several track/weather configurations while keeping the same team personnel and crew identity.

## Crew gameplay

Crew are shown by role rather than as another raw stat sheet:

- **Crew Chief** — strategy and coordination;
- **Lead Mechanic** — strain control, repairs and fragile-build support;
- **Tyre Changer** — tyre life and pit tyre recovery;
- **Fuel Runner** — heat management and pit support;
- **Spotter** — traffic awareness, attack support and hazard avoidance.

Those mechanics already existed in the v0.4.3 balance model. v0.4.5 makes them visible: pit/hazard/overtake/penalty/finish explanations can identify the relevant assigned specialists.

## Crew Chief advice

The garage can ask the pit wall for qualitative setup advice. Advice responds to the current build's:

- Mechanical Strain;
- Tuning Efficiency;
- strongest and weakest setup category;
- empty tyre/transmission slots;
- missing crew specialists;
- aggressive-driver tyre pressure;
- high heat;
- illegal-hardware risk.

No hidden race formula or exact probability calculation is exposed.

## Validation

- 46/46 automated regression tests passed in the release harness.
- All Python sources compile.
- Five active cogs import in the release harness.
- 44 slash-command names remain unique.
- 500 mixed-build stress races completed with 27,314 race events and no classification failures.
- 19,571 events in that stress run carried relevant crew-contributor context.
- Parts and pit-crew image sheets render successfully.
- The v0.4.3 quick Balance Lab remains PASS.
- A 300-race deterministic parity check against v0.4.4 produced the exact same race-result hash:

`6c6da6824c3596192057d54aeb477b7fa18d40272c044e51abbde95ef02e6536`
