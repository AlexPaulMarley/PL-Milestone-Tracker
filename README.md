# PL Milestone Tracker

Proof of concept: automatically emails an alert the first time a tracked
player crosses a Premier League career-goal milestone. Runs on GitHub
Actions (free), independent of any individual's computer.

Currently tracking (career goals as of 24 July 2026, before the season starts):

| Player | Current | Milestone |
|---|---|---|
| Erling Haaland | 112 | 113 |
| Ollie Watkins | 91 | 92 |
| Bruno Fernandes | 71 | 72 |

## How it works

1. `.github/workflows/check-milestones.yml` runs weekly (Mondays 08:00 UTC)
   via GitHub Actions, plus on-demand from the Actions tab.
2. `scripts/check_milestones.py` pulls each player's goals scored so far
   this season from the free Fantasy Premier League API, adds that to their
   baseline in `data/players.csv`, and compares the total to the milestone
   target.
3. The first time a milestone is crossed, it emails the recipient list. It
   won't email again for the same milestone — `data/state.json` tracks what's
   already been sent, and the workflow commits that file back after each run.

## One-time setup (do this before the first real run)

Add these as **repo secrets** (Settings → Secrets and variables → Actions →
New repository secret):

- `SMTP_HOST` — e.g. `smtp.office365.com`
- `SMTP_PORT` — e.g. `587`
- `SMTP_USERNAME` — the sending mailbox, e.g. `alex.marley@thomaslyte.com`
- `SMTP_PASSWORD` — an app password for that mailbox (Microsoft 365 with MFA
  requires an app password rather than the normal login password; you may
  need to ask IT to enable SMTP AUTH for the mailbox if it's currently
  blocked at the tenant level)

## Proving it works before the season starts

Go to the **Actions** tab → **Check PL Goal Milestones** → **Run workflow**,
tick the **test** checkbox, and run it. This skips the real API and injects
a fake player that's already past its target, so you should get a real
email (subject prefixed `[TEST]`) within a minute or two, sent to whoever is
listed in `RECIPIENTS` in the workflow file. This confirms the whole
pipeline — Actions trigger, secrets, SMTP send — without waiting for a real
goal.

## Extending later

- **More recipients**: edit the `RECIPIENTS` env var in
  `.github/workflows/check-milestones.yml` (currently just Alex and Liam for
  this test phase — add Ian, Chris, Markeec once it's proven out).
- **More players/milestones**: add a row to `data/players.csv`. The `web_name`
  column must match (or uniquely partial-match) the player's name on the FPL
  site — if it doesn't, the run logs a `WARNING` for that player and skips
  it rather than guessing.
- **Teams webhook instead of / as well as email**: swap or add a sender
  function alongside `send_email` in `scripts/check_milestones.py` — the
  rest of the logic (matching, state, dedup) doesn't need to change.
- **Other competitions/stats** (Champions League, assists, appearances):
  out of scope for this proof of concept, which is PL goals only.
