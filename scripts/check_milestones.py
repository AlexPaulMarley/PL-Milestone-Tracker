"""Check tracked Premier League players against goal milestones and email an
alert the first time each milestone is crossed.

Data sources:
  - data/players.csv: name, FPL "web_name" to match on, career goals before
    this season started, and the milestone target to watch for.
  - Fantasy Premier League public API (bootstrap-static): this season's
    goals_scored per player, added to the baseline for a live career total.

State:
  - data/state.json records which "web_name:target" milestones have already
    triggered an email, so a milestone is only ever notified once.

Test mode (TEST_MODE=true):
  - Skips the live API call and injects a fake player that is already over
    its target, guaranteeing an email fires. Used to prove the notification
    pipeline works without waiting for a real goal.
"""

import csv
import json
import os
import smtplib
from email.mime.text import MIMEText

import requests

FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
PLAYERS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "players.csv")
STATE_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")

TEST_WEB_NAME = "__TEST__"


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


def fetch_elements():
    resp = requests.get(FPL_BOOTSTRAP_URL, timeout=30)
    resp.raise_for_status()
    return resp.json()["elements"]


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


def send_email(subject, body, recipients):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(username, password)
        server.sendmail(username, recipients, msg.as_string())


def main():
    test_mode = os.environ.get("TEST_MODE", "false").strip().lower() == "true"
    recipients = [r.strip() for r in os.environ.get("RECIPIENTS", "").split(",") if r.strip()]
    if not recipients:
        raise SystemExit("RECIPIENTS env var is empty - nothing to notify")

    players = load_players()
    state = load_state()
    elements = [] if test_mode else fetch_elements()

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
        else:
            season_goals = find_season_goals(elements, web_name)
            if season_goals is None:
                continue

        total = baseline + season_goals
        key = f"{web_name}:{target}"
        already_notified = state.get(key, False)

        if total >= target and not already_notified:
            is_test = web_name == TEST_WEB_NAME
            subject = f"{'[TEST] ' if is_test else ''}Milestone Alert: {name} has reached {target} Premier League goals"
            body = (
                f"{name} has reached {total} career Premier League goals, "
                f"crossing the {target}-goal milestone.\n"
            )
            if is_test:
                body += "\nThis is a TEST alert confirming the notification pipeline works - no real goal was scored.\n"

            send_email(subject, body, recipients)
            state[key] = True
            print(f"Sent milestone email for {name} ({target})")
        else:
            print(f"{name}: {total}/{target} - no alert")

    save_state(state)


if __name__ == "__main__":
    main()
