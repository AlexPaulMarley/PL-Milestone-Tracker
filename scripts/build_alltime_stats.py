"""Build the dataset of every Premier League player's all-time (1992-present)
appearances and goals, from the official premierleague.com stats API.

The API's all-time totals update live during the season (verified: a goal
scored at the weekend shows in the ranked totals by Monday), so these figures
ARE current career totals - no need to add a season delta on top.

Run directly to write data/alltime_player_stats.csv/.xlsx, or import
build_dataset() to get the DataFrame (used by check_all_milestones.py).
"""

import time

import pandas as pd
import requests

API = "https://footballapi.pulselive.com/football"
HEADERS = {"Origin": "https://www.premierleague.com", "User-Agent": "Mozilla/5.0"}
PAGE_SIZE = 200


def fetch_current_squads():
    """{playerId: club name} for every player in a current PL squad list.

    The stats API's own currentTeam field means "last known club" - it still
    points retired legends at their old club (Scholes -> Man Utd), so squad
    membership is the only reliable "currently active in the PL" signal."""
    seasons = requests.get(f"{API}/competitions/1/compseasons",
                           params={"page": 0, "pageSize": 1},
                           headers=HEADERS, timeout=30).json()
    cs = int(seasons["content"][0]["id"])
    teams = requests.get(f"{API}/compseasons/{cs}/teams",
                         headers=HEADERS, timeout=30).json()
    print(f"Current season: {seasons['content'][0]['label']} ({len(teams)} clubs)")
    squads = {}
    for t in teams:
        staff = requests.get(f"{API}/teams/{int(t['id'])}/compseasons/{cs}/staff",
                             headers=HEADERS, timeout=30).json()
        for p in staff.get("players", []):
            squads[int(p["playerId"])] = t["name"]
        time.sleep(0.3)
    print(f"{len(squads)} players across current squads")
    return squads


def fetch_stat(stat):
    """Return {playerId: {..player fields.., stat: value}} for every player the
    API ranks for this stat (players with a zero value are simply absent)."""
    players = {}
    page = 0
    while True:
        resp = requests.get(
            f"{API}/stats/ranked/players/{stat}",
            params={"page": page, "pageSize": PAGE_SIZE, "comps": 1},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["stats"]
        for entry in data["content"]:
            owner = entry["owner"]
            pid = int(owner["playerId"])
            team = owner.get("currentTeam") or {}
            rec = players.setdefault(
                pid,
                {
                    "player_id": pid,
                    "name": owner["name"]["display"],
                    "position": owner.get("info", {}).get("positionInfo", ""),
                    "nationality": owner.get("nationalTeam", {}).get("country", ""),
                    "born": owner.get("birth", {}).get("date", {}).get("label", ""),
                    "current_club": team.get("club", {}).get("name", ""),
                    "current_club_id": int(team["club"]["id"]) if team.get("club") else None,
                },
            )
            rec[stat] = int(entry["value"])
        num_pages = data["pageInfo"]["numPages"]
        print(f"{stat}: page {page + 1}/{num_pages} ({len(players)} players)")
        page += 1
        if page >= num_pages:
            return players
        time.sleep(0.3)  # be polite to the API


def build_dataset():
    """DataFrame of all players, with is_current_pl marking players named in a
    current PL squad list."""
    squads = fetch_current_squads()
    appearances = fetch_stat("appearances")
    goals = fetch_stat("goals")

    # Appearances is the master list; anyone absent from the goals ranking has
    # simply never scored. A scorer missing from appearances would be an API
    # inconsistency worth surfacing, so merge from both sides.
    merged = appearances
    for pid, rec in goals.items():
        if pid in merged:
            merged[pid]["goals"] = rec["goals"]
        else:
            rec["appearances"] = 0
            merged[pid] = rec
            print(f"NOTE: {rec['name']} has goals but no ranked appearances")

    df = pd.DataFrame(merged.values())
    for col in ("appearances", "goals"):
        df[col] = df[col].fillna(0).astype(int) if col in df else 0
    df["is_current_pl"] = df["player_id"].isin(squads)
    # Squad membership is authoritative for club too; currentTeam is only a
    # last-known-club fallback for everyone else.
    df["current_club"] = df["player_id"].map(squads).fillna(df["current_club"])
    df = df[["name", "appearances", "goals", "current_club", "is_current_pl",
             "position", "nationality", "born", "player_id"]]
    df = df.sort_values(["appearances", "goals", "name"], ascending=[False, False, True])
    df.insert(0, "rank_by_apps", range(1, len(df) + 1))
    return df


def write_spreadsheets(df):
    df.to_csv("data/alltime_player_stats.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter("data/alltime_player_stats.xlsx", engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="All-time PL players", index=False)
        top_goals = df.sort_values("goals", ascending=False).head(100)
        top_goals.to_excel(xl, sheet_name="Top 100 scorers", index=False)
    print(f"Wrote {len(df)} players to data/alltime_player_stats.csv/.xlsx")


if __name__ == "__main__":
    frame = build_dataset()
    write_spreadsheets(frame)
    print(frame.head(10).to_string(index=False))
