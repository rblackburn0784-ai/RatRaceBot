# Rat Rod Racing Bot — 1950s Discord Tournament Bot

A full modular `discord.py` starter bot for running 1950s rat rod racing tournaments.

## Features

- Create racing teams with driver, pit crew, car type, and 6 driver stats.
- 7 car archetypes, each with positive and negative modifiers.
- Custom rod parts with fair trade-offs: engines, tyres, suspension, brakes, body, transmission, fuel, and illicit/dirty tricks parts.
- 5 tracks with different modifiers, lap events, surface hazards, corner difficulty, straight speed bias, and pit-lane difficulty.
- 10-car races over 10 laps.
- Semi-real-time race streaming with commentary, overtakes, accidents, pit stops, tyre wear, damage, illegal contact warnings, disqualifications, DNFs, and finish classification.
- Tournament system for 20–30 teams with points table.
- Media hooks for GIFs and audio clips you create yourself.
- SQLite persistence.
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
- `/team_create` — create a team.
- `/team_list` — list teams.
- `/team_sheet` — view full team sheet.
- `/team_add_part` — add a part to a team rod.
- `/team_remove_part` — remove a part.

### Racing
- `/race_tracks` — list tracks.
- `/race_quick` — run a race from selected team IDs.
- `/race_demo` — auto-create demo teams and run a 10-car race.

### Tournaments
- `/tournament_create` — create a tournament.
- `/tournament_add_team` — add team to tournament.
- `/tournament_start_race` — run a race for the next 10 teams or selected teams.
- `/tournament_standings` — show points table.
- `/tournament_close` — close tournament.

### Admin
- `/ratbot_init` — initialise database.
- `/media_list` — list media keys.

## Media

Put your own GIFs/audio into `assets/gifs` and `assets/audio`, then edit `data/media_registry.json`.

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
