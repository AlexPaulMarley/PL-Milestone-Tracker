"""Check tracked Premier League players against goal milestones and post an
alert to a Teams channel the first time each milestone is crossed.

Data sources:
  - data/players.csv: name, FPL "web_name" to match on, career goals before
    this season started, and the milestone target to watch for.
  - Fantasy Premier League public API (bootstrap-static): this season's
    goals_scored per player, added to the baseline for a live career total.

State:
  - data/state.json records which "web_name:target" milestones have already
    triggered an alert, so a milestone is only ever notified once.

Test mode (TEST_MODE=true):
  - Skips the live API call and injects a fake player that is already over
    its target, guaranteeing an alert fires. Used to prove the notification
    pipeline works without waiting for a real goal.
"""

import csv
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PLAYERS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "players.csv")
STATE_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")

TEST_WEB_NAME = "__TEST__"

# One-off: prove a scheduled trigger posts a test alert on its own, without a
# manual workflow_dispatch, before any real milestone exists to trigger one.
# Self-expiring - only matches these dates, so no cleanup is needed afterwards
# beyond removing the corresponding temporary cron line(s) in the workflow.
ONE_OFF_SCHEDULED_TEST_DATES = {"2026-07-27", "2026-07-28"}


def is_one_off_scheduled_test():
    """Only true for a scheduled trigger landing on one of ONE_OFF_SCHEDULED_TEST_DATES
    - never for manual workflow_dispatch runs, which already have their own
    explicit test input."""
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return False
    today = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    return today in ONE_OFF_SCHEDULED_TEST_DATES


def load_players():
    with open(PLAYERS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_state():
    if os.path.exists(STATE_JSON):
        with open(STATE_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def fetch_bootstrap():
    resp = requests.get(FPL_BOOTSTRAP_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()


def season_has_started(bootstrap):
    """Before a new PL season kicks off, the FPL API still reports each
    player's goals_scored from the just-finished season rather than 0 -
    it doesn't reset until the first gameweek actually begins. Adding that
    stale number to a baseline that already includes it double-counts, so
    treat season goals as 0 until a gameweek has actually started."""
    return any(e.get("finished") or e.get("is_current") for e in bootstrap.get("events", []))


def find_season_goals(elements, web_name):
    """Match a player by exact web_name, falling back to a case-insensitive
    substring match on second_name. Returns None (and logs a warning) if the
    match isn't unique, so a bad name in players.csv never silently sends
    wrong data instead of crashing the whole run."""
    needle = web_name.strip().lower()

    exact = [el for el in elements if el["web_name"].strip().lower() == needle]
    if len(exact) == 1:
        return exact[0]["goals_scored"]

    partial = [el for el in elements if needle in el["second_name"].strip().lower()]
    if len(partial) == 1:
        return partial[0]["goals_scored"]

    print(f"WARNING: could not uniquely match web_name '{web_name}' "
          f"({len(exact)} exact, {len(partial)} partial matches) - skipping")
    return None


def post_to_teams(title, text):
    """The Teams "Post to a channel when a webhook request is received"
    workflow template posts via an Adaptive Card attachment, not plain
    title/text fields - it expects the request body itself to already be a
    fully-formed card, wrapped in an "attachments" array."""
    webhook_url = os.environ["TEAMS_WEBHOOK_URL"]
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "weight": "Bolder",
                            "size": "Medium",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": text,
                            "wrap": True,
                        },
                    ],
                },
            }
        ],
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    test_mode = os.environ.get("TEST_MODE", "false").strip().lower() == "true"
    if not test_mode and is_one_off_scheduled_test():
        test_mode = True
        print("One-off scheduled test enabled - proving a scheduled trigger "
              "posts on its own before real milestones exist")

    debug_all_scorers = os.environ.get("DEBUG_ALL_SCORERS", "false").strip().lower() == "true"

    players = load_players()
    state = load_state()

    if test_mode:
        elements = []
        started = True  # unused in test mode, but keeps the branch simple
    else:
        bootstrap = fetch_bootstrap()
        elements = bootstrap["elements"]
        started = season_has_started(bootstrap)
        if not started:
            print("Season hasn't started yet - ignoring goals_scored (still last season's stale totals)")

    if debug_all_scorers and not test_mode:
        if not started:
            print("DEBUG_ALL_SCORERS: season hasn't started yet - no season goals to report")
        else:
            scorers = sorted(
                (el for el in elements if el.get("goals_scored", 0) > 0),
                key=lambda el: el["goals_scored"],
                reverse=True,
            )
            if scorers:
                lines = "\n\n".join(
                    f"- {el['web_name']}: {el['goals_scored']} goal(s) this season" for el in scorers
                )
                post_to_teams(
                    "[DEBUG] Live scorer check - every player with a goal this season",
                    f"{len(scorers)} player(s) have scored in the Premier League this season so far:\n\n{lines}\n\n"
                    "This is a one-off debug alert confirming the live API connection works - not a milestone check.",
                )
                print(f"DEBUG_ALL_SCORERS: posted one alert listing {len(scorers)} scorer(s)")
            else:
                print("DEBUG_ALL_SCORERS: season has started but no one has scored yet")

    if test_mode:
        players = players + [{
            "name": "Test Player",
            "web_name": TEST_WEB_NAME,
            "baseline_goals_before_season": "0",
            "milestone_target": "1",
        }]

    for p in players:
        name = p["name"]
        web_name = p["web_name"]
        baseline = int(p["baseline_goals_before_season"])
        target = int(p["milestone_target"])

        if web_name == TEST_WEB_NAME:
            season_goals = 1  # guarantees the fake player crosses its target
        elif not started:
            season_goals = 0
        else:
            season_goals = find_season_goals(elements, web_name)
            if season_goals is None:
                continue

        total = baseline + season_goals
        key = f"{web_name}:{target}"
        already_notified = state.get(key, False)

        if total >= target and not already_notified:
            is_test = web_name == TEST_WEB_NAME
            title = f"{'[TEST] ' if is_test else ''}Milestone Alert: {name} has reached {target} Premier League goals"
            text = (
                f"{name} has reached {total} career Premier League goals, "
                f"crossing the {target}-goal milestone."
            )
            if is_test:
                text += " This is a TEST alert confirming the notification pipeline works - no real goal was scored."

            post_to_teams(title, text)
            state[key] = True
            save_state(state)  # persist immediately so a later player's failure can't lose this alert's record
            print(f"Posted milestone alert for {name} ({target}) - total {total} = baseline {baseline} + season {season_goals}")
        else:
            print(f"{name}: {total}/{target} - no alert (baseline {baseline} + season {season_goals})")


if __name__ == "__main__":
    main()
