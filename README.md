# Rat Rod Racing Bot — 1950s Discord Tournament Bot

A full modular `discord.py` starter bot for running 1950s rat rod racing tournaments.

## Features

- Create racing teams with driver, pit crew, car type, and 6 driver stats.
- 7 car archetypes, each with positive and negative modifiers.
- 64 custom rod parts: 8 each for engine, tyres, suspension, brakes, body, fuel, transmission, and trick slots.
- Every part has positive and negative performance trade-offs, and each slot includes one marked illegal part.
- Illegal parts add risk-versus-reward power: each illegal part adds +6% disqualification risk per race and is warned in the picker.
- Custom pit crew loadouts with 5 crew positions and 5 selectable specialists per position. Crew now affects role-specific race situations rather than permanently stacking car stats.
- Build stats use one item per slot, Mechanical Strain, and tuning-efficiency diminishing returns so a fully loaded car gains options rather than becoming an automatic super-car.
- 10 tracks with sharper positive and negative modifiers, lap events, surface hazards, corner difficulty, straight speed bias, and pit-lane difficulty.
- 10-car races over 10 laps.
- Semi-real-time race streaming with commentary, overtakes, accidents, pit stops, tyre wear, damage, illegal contact warnings, disqualifications, DNFs, and finish classification.
- Single-race wizard for drivers with 5, 7, or 10 lap races and Full AI, Players Only, or Players Plus AI modes.
- Tournament system for 10-team scheduled championships with short, medium, and long formats.
- Tournament scoring gives 10 points for 1st down through the classified finishers; DNFs and DSQs score 0.
- Tournament stat tracking for wins, podiums, race fastest laps, DNFs/DSQs, overtakes, crashes, illegal moves, last-minute wins, near misses, and pit stops.
- Tournament-only persistent damage carries a repaired, capped slice of car damage into the next championship round for extra stakes without runaway punishment. Exhibition races do not alter carryover damage.
- Media hooks for GIFs and audio clips you create yourself.
- SQLite persistence.
- Discord ownership controls: admins can use all commands, while regular drivers can create one linked team and manage only their own team/parts wizards.
- Deterministic race seed plus full build/laps/damage replay snapshot saved for new races.
- `/race_replay` is non-destructive: it does not duplicate career stats, XP, achievements, sponsors, fatigue, or track records.


## v0.4.7 championships & season structure

- `/championship` opens the public **Blacktop Championship Hub** with round progress, next venue, standings, last-three form, fastest-lap totals, title picture, top-two head-to-head, rivalry watch and calendar state.
- Saved schedules now define official championship rounds. Once a calendar exists, unscheduled `/tournament_start_race` runs are exhibitions: they are saved for history but do **not** change championship points, fastest-lap totals, carryover damage or scheduled progress.
- Legacy/manual tournaments without a saved calendar still support scoring manual races.
- Tournament standings now track **race fastest laps**, DNFs and DSQs alongside wins, podiums and form.
- Title mathematics identifies live contenders, mathematically clinched championships and next-round clinch requirements such as **P2 or better** when the points permit it.
- The tournament calendar now shows completed rounds, the next round, queued rounds and winners from completed events.
- Final Season History snapshots permanently store expanded standings, season status, championship totals and the complete season-awards board.
- Season awards include **Champion, Runner-Up, Most Wins, Most Podiums, Fastest Driver, Overtake King, Cleanest Team, Dirtiest Team, Most Reliable, Best Pit Crew, Giant Killer, and Hard Luck Award**.
- Early manual closure remains supported but is explicitly stored as a **Shortened Season**; completing the final scheduled round still auto-finalises and closes the championship.
- Championship viewing commands are public; creation, team entry, race control and closure remain admin-only.

## v0.4.6 progression, sponsors & team identity

- Team XP now forms a Level 1–10 progression path at 100 XP per level. **Levels unlock choices and identity, never hidden speed/handling/reliability bonuses.**
- Garage preset capacity grows from 3 slots at Levels 1–2, to 4 at Levels 3–4, to all 5 at Level 5+. Existing saved setups are grandfathered.
- `/team_identity` adds level-gated liveries, emblems, garage decoration and a custom Level 3 race intro phrase. Identity is persistent but cosmetic.
- Level 4 opens the specialist crew shortlist for new assignments; specialists already employed before the upgrade remain grandfathered.
- Sponsor offers now activate real race contracts. A team can have **one active sponsor at a time**, can reject offers, or can end its current contract from the Sponsor Paddock.
- Five sponsors have deliberately two-sided mechanics: XP-vs-focus, repair-vs-pit-variance, momentum-vs-tyre-wear, hazard-save-vs-pace/scrutiny, and opening acceleration-vs-heat/scrutiny.
- Sponsor availability expands with team level rather than giving veteran teams a permanent base-stat bonus.
- Level-ups are called out after races and Level 5+ winners can receive established-team Blacktop Gazette recognition.
- Player-selected cosmetic titles are preserved when future race XP is awarded.
- Replay snapshots preserve active sponsor and identity state, while the Balance Lab now includes sponsor-dominance guardrails.

## v0.4.5 garage, parts & crew gameplay

- `/my_team` now opens **THE GARAGE** with all eight part slots, Mechanical Strain, Tuning Efficiency, illegal-hardware risk and broad **Fast Track / Technical / Wet / Rough** setup ratings.
- Garage controls expose **Fit Part**, **Remove Part**, **Compare Part**, **Save Setup**, **Load Setup**, **Ask Crew Chief**, and **Pit Crew** directly from the team dashboard.
- Parts can be replaced in one operation. The Parts Wizard compares an alternative against the currently fitted item and shows projected setup ratings, strain, tuning efficiency and DSQ-risk changes before fitting.
- Each team can persist five hardware presets: **Street, Dirt, Wet, High-Speed, Custom**. Presets store parts only so loading a race setup never unexpectedly changes the pit crew.
- Saved presets live in SQLite and are cleaned automatically when a team is deleted. Unknown/retired part keys are ignored safely when an old preset is loaded.
- **Ask Crew Chief** gives contextual advice about build strain, tuning saturation, heat, tyre pressure, missing specialist roles, illegal hardware and where the current setup is strongest/weakest.
- Crew roles are presented in plain language: Crew Chief (strategy), Lead Mechanic (repair/strain), Tyre Changer (tyre care), Fuel Runner (heat), Spotter (traffic/hazards).
- Major race-event `Why` notes can name the relevant assigned specialists so crew contribution is visible without exposing raw formulas.
- v0.4.5 does not change the race-performance model. Deterministic race results remain parity-identical to v0.4.4 for the same seeds, and the v0.4.3 Balance Lab remains the competitive-integrity gate.

## v0.4.4 race presentation & strategy

- Pre-race confirmation shows track character, weather, race length and a qualitative setup card for each entrant.
- Setup cards show broad straight-line, cornering, reliability and pit-work ratings plus Mechanical Strain and Tuning Efficiency without exposing the simulation formula.
- Venue/weather-specialist parts are called out as useful or compromised for the selected race, along with heat, reliability, illegal-part and strain warnings.
- Live race presentation is split into **Start → Opening Laps → Mid-Race → Pit Window → Closing Laps → Final Lap** with phase-specific guidance explaining which driver/team factors matter.
- Live leaderboard snapshots appear at sparse checkpoints and show estimated gap-to-leader, damage, tyre wear and strain state for the full field.
- Major race events can include a short qualitative **Why** explanation.
- Pit stops now carry service quality, approximate time cost, damage/tyre recovery and position change through the pit cycle.
- Final classification always posts even when the Blacktop Gazette image is available, with explicit DNF/DSQ reporting and fastest-lap callout.
- New track records are posted explicitly instead of being hidden inside the newspaper render.
- v0.4.4 changes presentation only: deterministic race results remain parity-identical to the v0.4.3 balance baseline for the same seeds.

## v0.4.3 balance rules

- All seven stock archetypes are calibrated against the complete 10-track schedule. The release Balance Lab target is **10-18% overall win rate per archetype** with equal drivers.
- Lap time uses a smooth asymptotic floor instead of a hard 48-second cap, so extra performance always helps but delivers diminishing returns at extreme pace.
- The six driver stats share a concave 24-point skill foundation, then specialise: Handling for corners, Reflexes for traffic/hazards, Nerve for consistency/clutch control, Mechanics for pit/strain management, Aggression for attacking pace with warning/tyre risk, and Showmanship for momentum with extra tyre demand.
- Pit crews are specialists rather than a second permanent-stat stack: crew chiefs influence strategy, mechanics repair/strain, tyre changers wear/pits, fuel runners heat management, and spotters traffic/hazards.
- Every legal part has at least one meaningful gain and one meaningful drawback. Several parts also have venue/weather specialisations, so Salt-Flat Skins, Dirt Track Treads, rain tyres, gearing and rough-track hardware change value by race.
- **Mechanical Strain** rises with aggressive hardware. High strain adds heat/wear/reliability/pit pressure, while driver Mechanics and lead-mechanic support can partially manage it.
- Fitting many parts also reduces **Tuning Efficiency**. Positive hardware bonuses receive diminishing returns as the car becomes more complicated; drawbacks remain fully active.
- Illegal parts remain **+6% DSQ risk each**. A single illegal item is a risky shortcut; stacking multiple illegal systems also compounds Mechanical Strain.
- Driver traits are contextual trade-offs rather than permanent raw-stat boosts.
- `python tools/balance_lab.py` runs deterministic Monte Carlo balance checks over archetypes, driver builds, legal part slots, crew roles and a fully developed stress build. `--quick` provides a shorter smoke run.

## v0.4.2 reliability rules

- Classification is always **official finishers → DNF → DSQ**. DNFs and DSQs score **0 championship points**.
- Win/podium progression, First Win, sponsor podium offers, interviews, newspaper winner headlines and timing records only use official finishers.
- Track timing records now include **Fastest Lap** plus separate **Fastest 5-Lap Race**, **Fastest 7-Lap Race**, and **Fastest 10-Lap Race** records. DNFs/DSQs are excluded.
- Tournament race starts require the full **10-team** grid. Manual races do not advance the saved schedule.
- The last scheduled race automatically finalises and closes the championship; manual close performs the same atomic Season History save.
- Post-race progression is idempotent by `race_id`, preventing duplicate XP/achievements/sponsors/records on retries.
- Process-local race/lobby locks block overlapping use of the same team or tournament.
- Dynamic GIF generation runs off the Discord event loop and generated GIF cache files are pruned automatically.
- Malformed optional media config and invalid race-tick values fall back safely instead of preventing startup.
- Regression tests for these rules live under `tests/`.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Create `.env`:

```env
DISCORD_BOT_TOKEN=your_token_here
GUILD_ID=optional_test_server_id
RACE_TICK_SECONDS=2.0
DATABASE_PATH=rat_rod_racing.sqlite3
ADMIN_ROLE_IDS=optional_role_id,optional_second_role_id
AUDIT_LOG_CHANNEL_ID=optional_admin_log_channel_id
```

Run:

```bash
python main.py
```

Development / release checks:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python tools/balance_lab.py --quick
```

## Commands

### Teams
- `/menu` — open the private button menu. New players see a Start Here menu until they create a team.
- `/status` — show your current team/race dashboard.
- `/team_wizard` — create your one linked team with a guided setup flow.
- `/team_edit_wizard` — edit your team names, car, and stats unless the team is in an open tournament.
- `/parts_wizard` — compare, fit/replace, and remove parts on your own rod with a visual garage sheet. Parts can still be changed during tournaments.
- `/pit_crew_wizard` — assign specialist crew members and see their real race roles with a visual crew sheet.
- `/my_team` — open THE GARAGE dashboard with parts, setup ratings, saved presets, Crew Chief advice and pit-crew controls.
- `/scrutineering` — inspect your team's illegal-part, heat, reliability, and race-readiness risks.
- `/team_progress` — show cosmetic XP, title, traits, achievements, sponsors, and fatigue.
- `/team_title` — choose an unlocked cosmetic title for your team.
- `/sponsor_offers` — manage recent sponsor offers, accept one active trade-off contract, reject offers, or end the current contract.
- `/hall_of_fame` — show champions, record holders, and legendary rivalries.
- `/team_create` — admin-only team creation.
- `/team_list` — admin-only team list.
- `/team_sheet` — admin-only team sheet lookup.
- `/team_reputation` — show your team's earned racing reputation.
- `/team_rivalries` — show your team's hottest rivalries.
- `/team_delete` — admin-only delete for teams that are not in an open tournament.
- `/team_add_part` — admin-only direct part install.
- `/team_remove_part` — admin-only direct part removal.

### Racing
- `/race_tracks` — list tracks.
- `/track_cards` — browse track cards with style and difficulty details.
- `/race_wizard` — start a single race as a regular driver.
- `/race_quick` — admin-only race from selected team IDs.
- `/race_demo` — admin-only auto-created 10-car demo race.
- `/race_replay` — admin-only non-destructive replay/debug helper using exact saved snapshots for v0.4.1+ races (legacy seed replay for older races).
- Single races — post a final podium, placements, and stat awards report without pinning it.
- Admin race starts now show a private preflight check and confirmation before posting publicly.
- Every race condenses the post-race recap, standings, awards, hype, predictions, rivalries, achievements, sponsors, and records into one Blacktop Gazette PNG when Pillow is installed.
- Every race posts automatic pre-race scrutineering before the race stream starts.
- Every race opens a short pre-race winner prediction window.
- Every race can award cosmetic XP, achievements, sponsor offers, fatigue flags, interviews, hype ratings, and track records.
- Player race lobbies post countdown reminders at 5 minutes and 1 minute.
- Races now roll random weather that changes car performance and race risk.
- `/track_records` — show fastest, wildest, and most chaotic marks by track.

### Tournaments
- `/tournament_wizard` — create a tournament with 10 teams and a short, medium, or long track schedule.
- `/tournament_create` — create a tournament.
- `/tournament_add_team` — add team to tournament.
- `/tournament_start_race` — run a manual race using all 10 entered teams. In a scheduled championship this is an exhibition; in a legacy/manual tournament it remains a scoring race.
- `/tournament_next_race` — run the next race from the saved track schedule.
- `/tournament_schedule` — show the championship calendar with completed/next/queued rounds and completed-round winners.
- `/tournament_standings` — show the public points table with wins, podiums, fastest laps, DNFs/DSQs and recent form.
- `/tournament_stats` — show current tournament points and fun stat leaders.
- `/championship` — public Championship Hub with calendar, title picture, form, head-to-head and rivalry watch.
- `/season_history` — show completed championship podiums plus saved season highlights.
- Final scheduled race — atomically finalises standings, saves Season History, closes the tournament, then posts/pins the final awards report.
- `/tournament_close` — manually finalise standings, save Season History, and close a tournament after at least one race.

### Admin
- `/ratbot_init` — initialise database.
- `/media_list` — list media keys.
- `/parts_catalogue` — list available rod parts and modifiers.
- `/admin_panel` — visual button panel for admin-only tools, selectors, race preflights, and guarded actions.
- `/ai_personalize_saved` — upgrade saved demo/AI teams with personalities, parts, and crew.
- `/backup_database` — create a timestamped SQLite backup in `backups/`.
- `/version` — show the current bot changelog/version note.

## Discord Access Rules

- Discord users with Administrator permission can use every command.
- Role IDs listed in `ADMIN_ROLE_IDS` can also use admin commands.
- If `AUDIT_LOG_CHANNEL_ID` is set, key admin actions are logged there.
- Regular drivers can use `/menu`, `/status`, `/team_wizard`, `/team_edit_wizard`, `/parts_wizard`, `/pit_crew_wizard`, `/my_team`, `/scrutineering`, `/team_reputation`, `/team_rivalries`, `/team_progress`, `/team_title`, `/team_identity`, `/sponsor_offers`, `/track_records`, `/race_tracks`, `/track_cards`, `/race_wizard`, `/championship`, `/tournament_standings`, `/tournament_stats`, `/tournament_schedule`, and `/season_history`.
- Regular drivers can create one team, linked to their Discord user ID.
- Regular drivers can only edit their own linked team.
- Team profile edits are locked while that team is in an open tournament, but parts are still editable.
- Pit crew loadouts are also editable during tournaments.
- Tournament **management** and direct/admin race commands remain admin-only; championship viewing commands are public.
- Team reputation and rivalries update automatically after saved races.
- AI teams have racing personalities such as Reckless, Defensive, Pit-Focused, Showboat, Reliable, and Glass Cannon.

## Single Race Wizard

- Full AI Race: your team races 9 AI teams.
- Players Only: posts a 10-minute join lobby; the race starts with joined player teams only if at least 4 teams joined.
- Players Plus AI: same 10-minute join lobby, then AI fills empty slots up to 10 racers if at least 4 player teams joined.

## Media

Put your own GIFs/audio into `assets/gifs` and `assets/audio`, then edit `data/media_registry.json`.

Put car artwork for the parts wizard into `assets/cars`. The bot looks for either the enum name or the safe display name, for example:

- `coupe_32.png`
- `1932_chopped_coupe.png`
- `roadster_29.png`
- `1929_barebones_roadster.png`

Put the pit crew wizard artwork at `assets/crew/pit_crew.png`. If that file is missing or cannot be opened, the bot falls back to the drawn crew sheet.

Put the race newspaper artwork at `assets/newspaper/newspaper_template.png`. If that file is missing or cannot be opened, the bot falls back to the generated newspaper layout.

Dynamic race event GIFs are built on the fly when Pillow is installed. Put 3 PNG backgrounds for each event in `assets/track`, using names like:

- `Start1.png`, `Start2.png`, `Start3.png`
- `Overtake1.png`, `Overtake2.png`, `Overtake3.png`
- `Minor Damage1.png`, `Major Damage1.png`, `Pitstop1.png`
- `Illegal1.png`, `Disqualified1.png`, `Destroyed1.png`
- `LapLeader1.png`, `Finish1.png`, `Podium1.png`

Put transparent car sprites in `assets/cars` as `{colour}_{model}.png`, for example `red_coupe_32.png`, `blue_gasser.png`, `silver_lakster.png`, or `green_truck_50.png`. The race engine assigns each racer a colour at the start and uses their selected car model for generated 5-second event GIFs.

Example keys used by the race engine:

- `start`
- `overtake`
- `damage_minor`
- `damage_major`
- `destroyed`
- `pit_stop`
- `illegal_move`
- `finish_line`
- `podium`

The bot will send GIFs where available. Audio support is left as a hook: the code resolves audio paths and stores them in events, so you can connect it to your existing boxing/bowling voice streamer.

## Notes

Current code version: **v0.4.7 — Championships & Season Structure**. Scheduled rounds now define the championship, public season views expose form/title/head-to-head context, and permanent Season History includes full awards and summary snapshots. v0.4.3 balance, v0.4.4 presentation, v0.4.5 garage gameplay and v0.4.6 horizontal progression remain intact. See `UPGRADE_v0.4.7.md` and `CHAMPIONSHIPS_v0.4.7.md` for details.
