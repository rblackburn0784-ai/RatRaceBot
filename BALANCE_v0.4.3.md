# v0.4.3 Balance Report — Competitive Integrity

Release validation performed 2026-10-04 using deterministic Monte Carlo races across all 10 tracks.

## Design rule

> There is no best car and no best build. There is only the best compromise for the track, weather, driver and strategy.

## Release targets

| Check | Target | Measured |
|---|---:|---:|
| Stock archetype overall win rate | 10–18% each | **11.58–16.92%** |
| Driver profile spread | ≤10 percentage points | **7.25 pp** |
| Developed stress build vs 9 stock cars | ≤35% wins | **21.25%** |
| Legal part slot leader | <30% | **25.00% max** |
| Crew role leader | <25% | **20.67% max** |
| Legal parts with a meaningful drawback | 100% | **100%** |

## Stock archetypes

Equal 24-point drivers, stock cars, mixed deterministic identities, 1,200 races across the full schedule:

| Archetype | Win rate |
|---|---:|
| 1932 Chopped Coupe | 11.58% |
| 1929 Barebones Roadster | 14.42% |
| 1950 Shop Truck | 16.33% |
| Low-Slung Leadsled | 13.08% |
| Moonshine Gasser | 14.17% |
| Salt-Flat Lakester | 13.50% |
| Four-Door Sleeper Sedan | 16.92% |

The spread is intentionally not zero. Individual tracks should favour different strengths; the complete championship schedule is the fairness target.

## Driver allocations

Seven representative legal 24-point profiles were raced in identical Sedans across the full schedule:

| Profile | Win rate |
|---|---:|
| Balanced 4/4/4/4/4/4 | 16.50% |
| Handling/Reflex specialist | 18.83% |
| Aggressive | 11.58% |
| Mechanic | 11.92% |
| Nerve | 13.92% |
| Showman | 12.42% |
| Extreme min-max 5/8/1/1/8/1 | 14.83% |

The previous extreme Handling/Reflex build could dominate a balanced driver. v0.4.3 reduces that to a competitive choice rather than an automatic answer.

## Developed-team stress test

A deliberately performance-leaning eight-part legal build plus a strong five-person crew was raced against nine stock equivalent cars across the complete schedule.

**Measured win rate: 21.25%.**

The same type of stacking could exceed 70% before the v0.4.3 balance work. Mechanical Strain and Tuning Efficiency now make full-slot builds a strategic commitment rather than a guaranteed upgrade path.

The stress build measured:

- Tuning Efficiency: approximately **39%**
- Mechanical Strain: **14 — Knife-Edge**

Positive hardware bonuses diminish as the build becomes more complex. Negative trade-offs remain fully active.

## Legal part slot leaders

Highest mixed-track win rate in each seven-choice legal slot test:

| Slot | Leading option | Win rate |
|---|---|---:|
| Engine | Blueprinted Flathead | 19.00% |
| Tyres | Dirt Track Treads | 21.67% |
| Suspension | Rebuilt Race Shocks | 22.00% |
| Brakes | Handbrake Turn Bar | 25.00% |
| Body | Channelled Body | 19.00% |
| Transmission | Quick-Change Rear End | 23.33% |
| Fuel | Dual Carb Setup | 18.67% |
| Trick | Lucky Dashboard Charm | 24.67% |

Specialist parts may be substantially stronger or weaker on one venue than their overall rate suggests. That is intentional: Salt-Flat Skins, dirt setups, wet-weather tyres and gear choices are meant to be track decisions rather than globally optimal items.

## Crew role leaders

Crew are now contextual specialists and do not modify permanent rod stats.

| Role | Leading member in mixed-track test | Win rate on 7-car comparison grid |
|---|---|---:|
| Crew Chief | Mae Clipboard | 16.67% |
| Lead Mechanic | Grace Grease | 20.67% |
| Tyre Changer | Lou Whitewall | 20.67% |
| Fuel Runner | Mabel Meter | 19.00% |
| Spotter | Sue Side-Eye | 20.33% |

## Illegal parts

- Scrutineering risk remains **+6% DSQ per illegal part**.
- One illegal part is allowed to be an attractive shortcut.
- Multiple illegal systems also create extra Mechanical Strain.
- All eight illegal systems together produce **48% pre-race DSQ risk** and very high strain, making an all-illegal super-build a gamble rather than a rational optimum.

## Reliability regression

A separate mixed-build 500-race stress run generated **26,163 events** and produced:

- 0 classification-order failures
- 0 DNF/DSQ point awards
- 0 failed-car winner errors
- 0 race-engine exceptions

The complete automated release suite passes **28/28 tests**.

## Re-running the lab

Full deterministic balance sample:

```bash
python tools/balance_lab.py
```

Short smoke sample:

```bash
python tools/balance_lab.py --quick
```

JSON output for external analysis:

```bash
python tools/balance_lab.py --json --no-fail
```

Monte Carlo targets are regression guardrails, not a promise that short samples or individual championships will exactly match these percentages.
