# PL Milestone Tracker

Proof of concept: automatically posts an alert to a Microsoft Teams channel
the first time a tracked player crosses a Premier League career-goal
milestone. Runs on GitHub Actions (free), independent of any individual's
computer.

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
3. The first time a milestone is crossed, it posts a message to whichever
   Teams channel the webhook was created in. It won't post again for the
   same milestone — `data/state.json` tracks what's already been sent, and
   the workflow commits that file back after each run.

## One-time setup (do this before the first real run)

### 1. Create the Teams webhook

Classic "Incoming Webhook" connectors have been retired in Teams, so this
goes through the **Workflows** app instead:

1. In the Teams channel you want alerts posted to, click **⋯ (More options)**
   next to the channel name → **Workflows** (or find "Workflows" in the app
   list on the left-hand sidebar).
2. Search the templates for **"Post to a channel when a webhook request is
   received"** and select it.
3. Sign in if prompted, confirm the Team and Channel it should post to, then
   click **Add workflow**.
4. It generates a unique HTTP POST URL — copy it. This is only shown once,
   so save it somewhere safe until it's added to GitHub (step 2 below).
5. This template's default flow expects the incoming request to already be
   a full Adaptive Card (wrapped in an `attachments` array) — that's exactly
   what `scripts/check_milestones.py` sends, so you shouldn't need to touch
   the auto-generated "Initialize variable" / "Post card in a chat or
   channel" steps it creates. If it asks for a sample request body/schema,
   accept the default it suggests rather than a custom one.
6. Save the flow.

(Menu wording can vary slightly by Teams version — if "Workflows" isn't
visible, it may need enabling by IT, or search Teams docs for "Workflows
app webhook".)

### 2. Add the webhook URL to GitHub

Go to this repo's **Settings → Secrets and variables → Actions → New
repository secret**, and add:

- Name: `TEAMS_WEBHOOK_URL`
- Value: the URL you copied in step 1.4 above

## Proving it works before the season starts

Go to the **Actions** tab → **Check PL Goal Milestones** → **Run workflow**,
tick the **test** checkbox, and run it. This skips the real API and injects
a fake player that's already past its target, so you should see a message
(titled `[TEST] ...`) appear in the Teams channel within a minute or two.
This confirms the whole pipeline — Actions trigger, secret, webhook post —
without waiting for a real goal.

## Extending later

- **More players/milestones**: add a row to `data/players.csv`. The `web_name`
  column must match (or uniquely partial-match) the player's name on the FPL
  site — if it doesn't, the run logs a `WARNING` for that player and skips
  it rather than guessing.
- **Multiple channels** (e.g. a UEFA-specific chat vs a Premier League one):
  create a separate webhook per channel and either run the workflow multiple
  times with different secrets, or extend the script to post to more than
  one URL.
- **Other competitions/stats** (Champions League, assists, appearances):
  out of scope for this proof of concept, which is PL goals only.
