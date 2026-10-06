# v0.5 Test Matrix — Blacktop Racing World

| Area | Coverage |
| --- | --- |
| Race rules, DNF/DSQ/classification | existing v0.4.2+ regression suite |
| All seven archetypes | Balance Lab + v0.4.3 balance tests |
| All legal part slots | Balance Lab + structural trade-off tests |
| Illegal hardware | DSQ-risk / strain regression tests |
| All crew roles and specialists | Balance Lab + crew tests |
| Driver builds | Balance Lab |
| Replay snapshots | replay regression suite |
| XP / progression / achievements | progression regression suite |
| Sponsors | progression tests + Balance Lab |
| Garage / saved track setups | garage regression suite |
| Tournaments / scheduled rounds | championship regression suite |
| Championship close / awards | championship regression suite |
| Rivalries / world events | v0.4.8 world tests |
| Recovery / backups / restore | v0.4.9 recovery tests |
| Concurrent race/lobby protection | reliability + recovery tests |
| Permanent per-team season history | `tests/test_v050_world.py` |
| Existing-season migration/backfill | `tests/test_v050_world.py` |
| Next-season continuity | `tests/test_v050_world.py` |
| Tournament restore removes stale career snapshot | `tests/test_v050_world.py` |
| World Hub routing / readiness | `tests/test_v050_world.py` |
| Discord component row limits | `tests/test_v050_world.py` |
| Shared View error boundary | `tests/test_v050_world.py` |
| One-shot destructive UI | `tests/test_v050_world.py` |
| Full competitive integrity | mandatory full Balance Lab |

A release is not considered ready if either the full pytest suite or full Balance Lab fails.
