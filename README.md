# Rat Rod Racing Bot — 1950s Discord Tournament Bot

A full modular `discord.py` starter bot for running 1950s rat rod racing tournaments.

## Features

- Create racing teams with driver, pit crew, car type, and 6 driver stats.
- 7 car archetypes, each with positive and negative modifiers.
- 64 custom rod parts: 8 each for engine, tyres, suspension, brakes, body, fuel, transmission, and trick slots.
- Every part has positive and negative performance trade-offs, and each slot includes one marked illegal part.
- Illegal parts add risk-versus-reward power: each illegal part adds +6% disqualification risk per race and is warned in the picker.
- Custom pit crew loadouts with 5 crew positions, 5 selectable members per position, and crew stat buffs/debuffs.
- Build stats use fair-play caps and one item per slot, so duplicate saved parts or runaway part/crew stacking cannot overpower the race engine.
- 10 tracks with sharper positive and negative modifiers, lap events, surface hazards, corner difficulty, straight speed bias, and pit-lane difficulty.
- 10-car races over 10 laps.
- Semi-real-time race streaming with commentary, overtakes, accidents, pit stops, tyre wear, damage, illegal contact warnings, disqualifications, DNFs, and finish classification.
- Single-race wizard for drivers with 5, 7, or 10 lap races and Full AI, Players Only, or Players Plus AI modes.
- Tournament system for 10-team scheduled championships with short, medium, and long formats.
- Tournament scoring gives 10 points for 1st down to 1 point for 10th.
- Tournament stat tracking for overtakes, crashes, illegal moves, last-minute wins, near misses, and pit stops.
- Tournament-only persistent damage carries a repaired, capped slice of car damage into the next race for extra stakes without runaway punishment.
- Media hooks for GIFs and audio clips you create yourself.
- SQLite persistence.
- Discord ownership controls: admins can use all commands, while regular drivers can create one linked team and manage only their own team/parts wizards.
- Deterministic race seed saved for replay/debugging.

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
```

Run:

```bash
python main.py
```

## Commands

### Teams
- `/team_wizard` — create your one linked team with a guided setup flow.
- `/team_edit_wizard` — edit your team names, car, and stats unless the team is in an open tournament.
- `/parts_wizard` — install and remove parts on your own rod with a visual garage sheet. Parts can still be changed during tournaments.
- `/pit_crew_wizard` — assign pit crew members with buffs/debuffs and a visual crew sheet.
- `/team_create` — admin-only team creation.
- `/team_list` — admin-only team list.
- `/team_sheet` — admin-only team sheet lookup.
- `/team_add_part` — admin-only direct part install.
- `/team_remove_part` — admin-only direct part removal.

### Racing
- `/race_tracks` — list tracks.
- `/race_wizard` — start a single race as a regular driver.
- `/race_quick` — admin-only race from selected team IDs.
- `/race_demo` — admin-only auto-created 10-car demo race.

### Tournaments
- `/tournament_wizard` — create a tournament with 10 teams and a short, medium, or long track schedule.
- `/tournament_create` — create a tournament.
- `/tournament_add_team` — add team to tournament.
- `/tournament_start_race` — run a race for the next 10 teams or selected teams.
- `/tournament_next_race` — run the next race from the saved track schedule.
- `/tournament_schedule` — show the saved tournament track order.
- `/tournament_standings` — show points table.
- `/tournament_stats` — show current tournament points and fun stat leaders.
- `/tournament_close` — close tournament.

### Admin
- `/ratbot_init` — initialise database.
- `/media_list` — list media keys.
- `/parts_catalogue` — list available rod parts and modifiers.

## Discord Access Rules

- Discord users with Administrator permission can use every command.
- Regular drivers can only use `/team_wizard`, `/team_edit_wizard`, `/parts_wizard`, `/pit_crew_wizard`, `/race_tracks`, and `/race_wizard`.
- Regular drivers can create one team, linked to their Discord user ID.
- Regular drivers can only edit their own linked team.
- Team profile edits are locked while that team is in an open tournament, but parts are still editable.
- Pit crew loadouts are also editable during tournaments.
- Tournaments and direct/admin race commands remain admin-only.

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

This is a strong v1 foundation. The engine is intentionally readable, tunable, and deterministic. Balance values live in `data/defaults.py`.
