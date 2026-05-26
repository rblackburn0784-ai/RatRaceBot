# Rat Rod Racing Bot — 1950s Discord Tournament Bot

A full modular `discord.py` starter bot for running 1950s rat rod racing tournaments.

## Features

- Create racing teams with driver, pit crew, car type, and 6 driver stats.
- 7 car archetypes, each with positive and negative modifiers.
- 64 custom rod parts: 8 each for engine, tyres, suspension, brakes, body, fuel, transmission, and trick slots.
- Every part has positive and negative performance trade-offs, and each slot includes one marked illegal part.
- Illegal parts add risk-versus-reward power: each illegal part adds +6% disqualification risk per race and is warned in the picker.
- 10 tracks with sharper positive and negative modifiers, lap events, surface hazards, corner difficulty, straight speed bias, and pit-lane difficulty.
- 10-car races over 10 laps.
- Semi-real-time race streaming with commentary, overtakes, accidents, pit stops, tyre wear, damage, illegal contact warnings, disqualifications, DNFs, and finish classification.
- Tournament system for 10-team scheduled championships with short, medium, and long formats.
- Tournament scoring gives 10 points for 1st down to 1 point for 10th.
- Tournament stat tracking for overtakes, crashes, illegal moves, last-minute wins, near misses, and pit stops.
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
- `/team_create` — admin-only team creation.
- `/team_list` — admin-only team list.
- `/team_sheet` — admin-only team sheet lookup.
- `/team_add_part` — admin-only direct part install.
- `/team_remove_part` — admin-only direct part removal.

### Racing
- `/race_tracks` — list tracks.
- `/race_quick` — run a race from selected team IDs.
- `/race_demo` — auto-create demo teams and run a 10-car race.

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
- Regular drivers can only use `/team_wizard`, `/team_edit_wizard`, and `/parts_wizard`.
- Regular drivers can create one team, linked to their Discord user ID.
- Regular drivers can only edit their own linked team.
- Team profile edits are locked while that team is in an open tournament, but parts are still editable.

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
