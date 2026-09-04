"""Scan every current Premier League player against career milestones and
notify a Teams channel.

Milestones (both stats, every 50): goals 50, 100, 150, 200...
                                   appearances 50, 100, 150, 200, 250, 300...

Business context: A P Marley prepares/offers medals for these milestones, so
the point is advance warning - see CLAUDE.md.

Each weekly run:
  1. Rebuilds the all-time dataset from the official PL API (career totals
     update live during the season) - the workflow commits the refreshed
     spreadsheet.
  2. Posts ONE digest card listing every current-PL player within NEAR of
     their next milestone (deduped per day via state.json, because the
     workflow's two Monday crons both fire).
  3. Posts an individual card per milestone actually REACHED since the last
     run, detected by comparing against data/milestone_snapshot.json and
     deduped forever via state.json - so the very first run just records a
     baseline and alerts on nothing historical.

Env:
  TEAMS_WEBHOOK_URL  webhook (required unless DRY_RUN)
  DRY_RUN=true       print cards instead of posting; write no files
  TEST_MODE=true     post one fake [TEST] digest card to prove the pipeline
"""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from build_alltime_stats import build_dataset, write_spreadsheets

STEP = 50
NEAR = 10  # was 5 until 2026-09-04; user wanted more lead time
STATS = ("goals", "appearances")
STATE_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")
SNAPSHOT_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "milestone_snapshot.json")
MAX_DIGEST_ROWS = 100  # per stat section, to stay inside Teams card size limits


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def post_to_teams(title, text, dry_run):
    if dry_run:
        print(f"\n--- DRY RUN card ---\n{title}\n{text}\n--- end card ---")
        return
    webhook_url = os.environ["TEAMS_WEBHOOK_URL"]
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": [
                    {"type": "TextBlock", "text": title, "weight": "Bolder",
                     "size": "Medium", "wrap": True},
                    {"type": "TextBlock", "text": text, "wrap": True},
                ],
            },
        }],
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def next_target(total):
    return (total // STEP + 1) * STEP


def crossed_milestones(prev, now):
    """Milestone values passed going from prev to now (prev < m <= now)."""
    return [m for m in range(STEP, now + 1, STEP) if m > prev]


def build_digest(active):
    """One line per player within NEAR of their next milestone."""
    sections = []
    for stat in STATS:
        rows = []
        for p in active:
            total = p[stat]
            to_go = next_target(total) - total
            if to_go <= NEAR:
                rows.append((to_go, -total, f"**{p['name']}** ({p['current_club']}) - "
                             f"{total} {stat}, **{to_go} to go** for {next_target(total)}"))
        rows.sort()
        shown = [r[2] for r in rows[:MAX_DIGEST_ROWS]]
        if len(rows) > MAX_DIGEST_ROWS:
            shown.append(f"...and {len(rows) - MAX_DIGEST_ROWS} more within {NEAR}")
        body = "\n\n".join(shown) if shown else f"No one within {NEAR} right now."
        sections.append(f"**{stat.upper()}** ({len(rows)} player(s) close)\n\n{body}")
    return "\n\n---\n\n".join(sections)


def main():
    dry_run = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    test_mode = os.environ.get("TEST_MODE", "false").strip().lower() == "true"
    today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()

    if test_mode:
        post_to_teams(
            "[TEST] PL milestone watch",
            "**GOALS**\n\n**Test Player** (Test FC) - 49 goals, **1 to go** for 50\n\n"
            "This is a TEST card proving the milestone-watch pipeline works - not real data.",
            dry_run,
        )
        print("TEST_MODE: posted fake digest card")
        return

    df = build_dataset()
    if not dry_run:
        write_spreadsheets(df)

    active = df[df["is_current_pl"]].to_dict("records")
    print(f"{len(active)} players at current PL clubs")

    state = load_json(STATE_JSON, {})
    snapshot = load_json(SNAPSHOT_JSON, None)
    first_run = snapshot is None

    # --- individual "milestone reached" alerts -----------------------------
    if first_run:
        print("No snapshot yet - recording baseline, no reached-alerts this run")
    else:
        for p in active:
            prev = snapshot.get(str(p["player_id"]))
            if not prev:
                continue  # new to the PL - nothing crossed under our watch
            for stat in STATS:
                for m in crossed_milestones(prev[stat], p[stat]):
                    key = f"reached:{stat}:{p['player_id']}:{m}"
                    if state.get(key):
                        continue
                    post_to_teams(
                        f"Milestone reached: {p['name']} - {m} Premier League {stat}",
                        f"**{p['name']}** ({p['current_club']}) has reached "
                        f"**{m} career Premier League {stat}** "
                        f"(now on {p[stat]}). Time to get the medal out!",
                        dry_run,
                    )
                    state[key] = True
                    if not dry_run:
                        save_json(STATE_JSON, state)  # persist per alert so a later failure can't lose it
                    print(f"Reached: {p['name']} {m} {stat}")

    # --- weekly "who's close" digest ---------------------------------------
    digest_key = f"digest:{today}"
    if state.get(digest_key):
        print("Digest already posted today - skipping duplicate")
    else:
        post_to_teams(f"PL milestone watch - {today}", build_digest(active), dry_run)
        state[digest_key] = True
        print("Posted digest")

    if not dry_run:
        new_snapshot = {str(p["player_id"]): {"name": p["name"],
                                              "goals": p["goals"],
                                              "appearances": p["appearances"]}
                        for p in active}
        save_json(SNAPSHOT_JSON, new_snapshot)
        save_json(STATE_JSON, state)


if __name__ == "__main__":
    main()
