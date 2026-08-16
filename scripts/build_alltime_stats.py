"""Build a spreadsheet of every Premier League player's all-time (1992-present)
appearances and goals, from the official premierleague.com stats API.

Output:
  - data/alltime_player_stats.csv
  - data/alltime_player_stats.xlsx

Run scripts/crossref_alltime_stats.py afterwards to verify the top of each
list against independent sources.
"""

import time

import pandas as pd
import requests

API = "https://footballapi.pulselive.com/football/stats/ranked/players/{stat}"
HEADERS = {"Origin": "https://www.premierleague.com", "User-Agent": "Mozilla/5.0"}
PAGE_SIZE = 200


def fetch_stat(stat):
    """Return {playerId: {..player fields.., stat: value}} for every player the
    API ranks for this stat (players with a zero value are simply absent)."""
    players = {}
    page = 0
    while True:
        resp = requests.get(
            API.format(stat=stat),
            params={"page": page, "pageSize": PAGE_SIZE, "comps": 1},
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["stats"]
        for entry in data["content"]:
            owner = entry["owner"]
            pid = int(owner["playerId"])
            rec = players.setdefault(
                pid,
                {
                    "player_id": pid,
                    "name": owner["name"]["display"],
                    "position": owner.get("info", {}).get("positionInfo", ""),
                    "nationality": owner.get("nationalTeam", {}).get("country", ""),
                    "born": owner.get("birth", {}).get("date", {}).get("label", ""),
                },
            )
            rec[stat] = int(entry["value"])
        num_pages = data["pageInfo"]["numPages"]
        print(f"{stat}: page {page + 1}/{num_pages} ({len(players)} players)")
        page += 1
        if page >= num_pages:
            return players
        time.sleep(0.3)  # be polite to the API


def main():
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
    df["appearances"] = df.get("appearances", 0)
    df["goals"] = df["goals"].fillna(0).astype(int) if "goals" in df else 0
    df["appearances"] = df["appearances"].fillna(0).astype(int)
    df = df[["name", "appearances", "goals", "position", "nationality", "born", "player_id"]]
    df = df.sort_values(["appearances", "goals", "name"], ascending=[False, False, True])
    df.insert(0, "rank_by_apps", range(1, len(df) + 1))

    df.to_csv("data/alltime_player_stats.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter("data/alltime_player_stats.xlsx", engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="All-time PL players", index=False)
        top_goals = df.sort_values("goals", ascending=False).head(100)
        top_goals.to_excel(xl, sheet_name="Top 100 scorers", index=False)

    print(f"\nWrote {len(df)} players to data/alltime_player_stats.csv/.xlsx")
    print(df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
