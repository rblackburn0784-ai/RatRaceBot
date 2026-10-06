# v0.4.9 Release-Candidate Test Matrix

| Area | Automated coverage |
| --- | --- |
| Race rules / DNF / DSQ / timing | `tests/test_v042_regressions.py` |
| All stock archetypes | `tests/test_v043_balance.py` + full Balance Lab |
| All legal parts / trade-offs | `tests/test_v043_balance.py` + full Balance Lab |
| Illegal hardware | `tests/test_v043_balance.py` |
| All crew roles/members | `tests/test_v043_balance.py` + full Balance Lab |
| Driver builds | `tests/test_v043_balance.py` + full Balance Lab |
| Race replay / snapshots | `tests/test_v046_progression.py`, v0.4.8 replay-state tests |
| Progression / achievements | `tests/test_v042_regressions.py`, `tests/test_v046_progression.py` |
| Sponsors | `tests/test_v046_progression.py` + full Balance Lab |
| Tournaments / scoring | `tests/test_v042_regressions.py`, `tests/test_v047_championships.py` |
| Championship close/history | `tests/test_v047_championships.py` |
| Rivalry/world idempotency | `tests/test_v048_racing_world.py` |
| Backups / restore | `tests/test_v049_recovery.py` |
| Concurrent race reservations | `tests/test_v042_regressions.py`, `tests/test_v049_recovery.py` |
| Undo / reprocess / correction | `tests/test_v049_recovery.py` |
| Team repair / DB validation | `tests/test_v049_recovery.py` |
| Recovery schema upgrades | `tests/test_v049_recovery.py` |
| Full balance regression | mandatory GitHub Actions `balance-lab` job |

Release is blocked if either the regression suite or Balance Lab fails.
