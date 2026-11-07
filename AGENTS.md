# Runtime rules agreed with the owner (07/11/2026)

- Do not add fixed sleeps/delays between production actions. Observe the screen,
  act only on a recognized state, then capture again to verify the result.
  `runtime_policy.no_step_delay` and `LaunchControl.sleep` are delay-free.
  `fixed_waits=True` is only for explicit simulated-clock unit tests, not scripts
  or GUI flows. OS command timeouts and pause/cancel waits are separate controls.
- `test_multithreads.py` names the two-MuMu login test, default five successful
  accounts per instance. Add a separate named script for a different future test.
- In this test, 120 seconds without meaningful screen change (or without a
  readable screenshot) restarts only the stalled VM. Maintain the current
  worker/account reservation, re-read and validate its X row, and authenticate
  again. X is a reservation, never proof of a successful login.
- Status V/ERR and completed-day values must survive VM recovery. Never clear
  the production workbook automatically. A new Python process cannot infer which worker
  owned historical X rows; do not guess or silently reassign them.
- Exception explicitly requested by the owner: `test_multithreads.py` uses
  only `test_script.xlsx` containing STT 1-10. Back it up and clear X/V/ERR and
  days 1-15 ONCE before starting workers on each new run. Never reset during
  watchdog recovery. GUI login tests also read this dedicated file. Normal
  A/B/C runs still use account.xlsx. Both credential workbooks stay Git-ignored.
- A recognized "nhấp vào khoảng trống" overlay must be tapped in the blank
  bottom strip and captured again until it disappears. Do not proceed using
  the pre-tap screenshot or stop after an arbitrary five fast attempts.
  Skills that own a reward/result must read it before dismissing it; do not
  globally dismiss their result before wins/rewards are recorded.
- When reporting Excel, include Status AND days 1-15 (including blank versus
  completed values). Never print usernames/passwords or save unredacted login
  fields in diagnostics.
