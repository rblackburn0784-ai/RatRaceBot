# Upgrade to v0.4.3 — Balance & Competitive Integrity

**Release:** 2026-10-04  
**From:** v0.4.2 — Race Rules, Tournament Integrity & Reliability

v0.4.3 is a gameplay-balance release. It does **not** require a database reset and it does not invalidate existing teams, tournaments, progression, race history or v0.4.1+ replay snapshots.

## Main balance changes

- Rebalanced all seven stock car archetypes around the complete 10-track championship schedule.
- Replaced the old hard lap-time floor with smooth diminishing returns.
- Rebuilt driver-stat influence so all six 24-point stats have useful race roles and min-max allocations cannot create a super-driver.
- Removed permanent pit-crew stat stacking. Crew members now provide role-specific race effects.
- Added Mechanical Strain for high-performance hardware.
- Added Tuning Efficiency diminishing returns when many parts are fitted.
- Rebalanced legal parts so each has a meaningful gain and drawback.
- Added track/weather specialisation for selected tyres, suspension, gearing, cooling and rough-track hardware.
- Kept illegal parts at **+6% DSQ risk per fitted illegal part**, while multiple illegal systems also compound strain.
- Reworked driver traits as contextual trade-offs rather than raw always-on car-stat bonuses.
- Added `tools/balance_lab.py` and `tests/test_v043_balance.py`.

## Explicit competitive targets

The release Balance Lab targets:

- stock archetypes: **10–18% overall win rate each** with equal drivers across the full schedule;
- representative legal 24-point driver profiles: no more than **10 percentage points** between strongest and weakest test profiles;
- fully developed stress build: **no more than 35% wins** against nine stock equivalents;
- legal part slot leader: **below 30%** in the mixed-track slot comparison;
- crew-role leader: **below 25%** in the mixed-track role comparison.

These are regression guardrails rather than a promise that every individual race is equal. Track, weather, build, driver style, hazards and randomness are deliberately allowed to change which compromise is best.

## Important gameplay behaviour

### Mechanical Strain

Each fitted part contributes strain according to its performance demand and support trade-offs. High strain increases race wear, heat/reliability pressure and pit difficulty. Driver Mechanics and lead-mechanic support can reduce the effective strain during a race.

### Tuning Efficiency

Hardware drawbacks remain fully active, but positive part bonuses receive diminishing returns as more systems and strain are added. One or two carefully selected parts retain most of their benefit. An eight-slot performance stack no longer receives eight full-strength piles of bonuses.

### Pit crew roles

Crew no longer appears in `BuildService.effective_car_stats()` as permanent car stats. Instead:

- Crew Chief → strategy and race calls
- Lead Mechanic → repair, strain and heat support
- Tyre Changer → tyre care and pit work
- Fuel Runner → heat/fuelling management and pit support
- Spotter → traffic, hazards and attacking support

The crew wizard and crew sheet display these specialist effects.

### Driver stats

All six stats still use the 1–8 range and 24-point budget. v0.4.3 uses a shared diminishing-return skill foundation, with smaller role-specific effects:

- Nerve — consistency, clutch phases and penalty resistance
- Handling — technical/corner performance
- Aggression — legal attacking opportunities, but more tyre/warning exposure
- Mechanics — strain management and pit/reliability work
- Reflexes — traffic and hazard response
- Showmanship — momentum/late-race energy at extra tyre demand

### Track specialisation

A part can be excellent in its intended environment and mediocre elsewhere. The balance layer includes explicit venue/weather hooks for items such as Salt-Flat Skins, Dirt Track Treads, Rain-Grooved Whites, Soft Dirt Setup, Tall/Short Rear Gears, cooling hardware and rough-track protection.

## Upgrade procedure

1. Stop the bot.
2. Back up your existing SQLite database.
3. Keep your existing `.env`, database and large `assets/` folders.
4. Replace the source files with the v0.4.3 files.
5. Install/update requirements:

   ```bash
   pip install -r requirements.txt
   ```

6. Install the test dependency and run the regression suite:

   ```bash
   pip install -r requirements-dev.txt
   python -m pytest -q
   ```

7. Optional but recommended before a championship:

   ```bash
   python tools/balance_lab.py
   ```

8. Start the bot normally.

## Existing teams

Existing fitted parts and crew assignments remain valid. Their **race effects change immediately** under v0.4.3 balance rules, so old “best” setups may no longer be optimal. That is intentional.

No artwork migration is required. Missing optional car/track/media assets continue to use the existing fallbacks.
