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
- Deterministic race seed plus full build/laps/damage replay snapshot saved for new races.
- `/race_replay` is non-destructive: it does not duplicate career stats, XP, achievements, sponsors, fatigue, or track records.

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

## Commands

### Teams
- `/menu` — open the private button menu. New players see a Start Here menu until they create a team.
- `/status` — show your current team/race dashboard.
- `/team_wizard` — create your one linked team with a guided setup flow.
- `/team_edit_wizard` — edit your team names, car, and stats unless the team is in an open tournament.
- `/parts_wizard` — install and remove parts on your own rod with a visual garage sheet. Parts can still be changed during tournaments.
- `/pit_crew_wizard` — assign pit crew members with buffs/debuffs and a visual crew sheet.
- `/my_team` — show your garage summary, risk, reputation, next setup jobs, and quick buttons for common team tools.
- `/scrutineering` — inspect your team's illegal-part, heat, reliability, and race-readiness risks.
- `/team_progress` — show cosmetic XP, title, traits, achievements, sponsors, and fatigue.
- `/team_title` — choose an unlocked cosmetic title for your team.
- `/sponsor_offers` — show recent cosmetic/story sponsor offers with accept/reject buttons.
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
- `/tournament_start_race` — run a race for the next 10 teams or selected teams.
- `/tournament_next_race` — run the next race from the saved track schedule.
- `/tournament_schedule` — show the saved tournament track order.
- `/tournament_standings` — show points table.
- `/tournament_stats` — show current tournament points and fun stat leaders.
- `/season_history` — show completed tournament champions and podiums.
- Final scheduled race — posts and pins a final podium, placements, and stat awards report.
- `/tournament_close` — close tournament.

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
- Regular drivers can only use `/menu`, `/status`, `/team_wizard`, `/team_edit_wizard`, `/parts_wizard`, `/pit_crew_wizard`, `/my_team`, `/scrutineering`, `/team_reputation`, `/team_rivalries`, `/team_progress`, `/team_title`, `/sponsor_offers`, `/track_records`, `/race_tracks`, `/track_cards`, and `/race_wizard`.
- Regular drivers can create one team, linked to their Discord user ID.
- Regular drivers can only edit their own linked team.
- Team profile edits are locked while that team is in an open tournament, but parts are still editable.
- Pit crew loadouts are also editable during tournaments.
- Tournaments and direct/admin race commands remain admin-only.
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

Current code version: **v0.4.1 Stabilisation**. The engine is intentionally readable, tunable, and deterministic. Balance values live in `data/defaults.py`. See `UPGRADE_v0.4.1.md` for upgrade/security notes.
