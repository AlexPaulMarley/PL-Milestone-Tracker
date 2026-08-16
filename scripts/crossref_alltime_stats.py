"""Cross-reference data/alltime_player_stats.csv (premierleague.com API) against
two independent publishers:

  - Wikipedia: "List of Premier League players with 300 or more appearances"
               (top-appearances table) and "...with 100 or more goals"
  - Transfermarkt: all-time PL top scorers and all-time record appearance makers

worldfootball.net was considered as a source but sits behind a Cloudflare
challenge, so Transfermarkt stands in as the second independent publisher.

Writes data/crossref_report.md summarising agreements and discrepancies.
"""

import io
import re
import time
import unicodedata

import pandas as pd
import requests
from bs4 import BeautifulSoup

WIKI_UA = {"User-Agent": "PLMilestoneTracker/1.0 (alexmarley.am@googlemail.com)"}
TM_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}
WIKI_APPS = "https://en.wikipedia.org/wiki/List_of_Premier_League_players_with_300_or_more_appearances"
WIKI_GOALS = "https://en.wikipedia.org/wiki/List_of_Premier_League_players_with_100_or_more_goals"
TM_GOALS = "https://www.transfermarkt.com/premier-league/ewigetorschuetzen/wettbewerb/GB1"
TM_APPS = "https://www.transfermarkt.com/premier-league/rekordspieler/wettbewerb/GB1"


# NFKD decomposition doesn't touch these, so map them explicitly or the
# letter just gets dropped ("Sorensen" -> "Srensen").
SPECIAL_CHARS = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L",
                               "æ": "ae", "Æ": "AE", "ð": "d", "Ð": "D",
                               "þ": "th", "Þ": "Th", "ß": "ss"})
# Common short forms so e.g. Wikipedia's "Andy Cole" matches the API's
# "Andrew Cole".
FIRST_NAME_ALIASES = {"andy": "andrew", "matt": "matthew", "steve": "steven",
                      "jimmy": "james", "danny": "daniel", "eddie": "edward"}


# norm -> display name as first seen, so the report shows "Peter Crouch"
# rather than the token-sorted matching key ("crouch peter").
DISPLAY = {}


def norm_name(name):
    """Normalise for matching across sources: strip accents, footnote markers
    ([a], *, daggers), punctuation and case; expand common first-name short
    forms; fold the Dutch ij/y spelling variation (Nistelrooij/Nistelrooy);
    sort tokens so "Son Heung-min" and "Heung-min Son" agree."""
    display = " ".join(re.sub(r"\[.*?\]", "", str(name)).split())
    name = display.translate(SPECIAL_CHARS)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^a-zA-Z ]", "", name)
    tokens = [t.replace("ij", "y") for t in name.lower().split()]
    if tokens:
        tokens[0] = FIRST_NAME_ALIASES.get(tokens[0], tokens[0])
    key = " ".join(sorted(tokens))
    DISPLAY.setdefault(key, display)
    return key


def first_int(value):
    m = re.search(r"\d+", str(value).replace(",", "").replace(".", ""))
    return int(m.group()) if m else None


def wiki_table(url, value_col_pattern):
    """Largest table on the page that has both a player-name column and a
    column matching value_col_pattern (a per-club records table also matches,
    but the career list is always bigger... except on the appearances page,
    where the per-club table is bigger - so also require no 'Club' rank column)."""
    html = requests.get(url, headers=WIKI_UA, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    candidates = []
    for t in tables:
        cols = [str(c) for c in t.columns]
        name_col = next((c for c in cols if re.search(r"name|player", c, re.I)), None)
        val_col = next((c for c in cols if re.search(value_col_pattern, c, re.I)), None)
        is_per_club = any(str(c).strip().lower() == "club" for c in cols)
        if name_col and val_col and not is_per_club:
            candidates.append((len(t), t, name_col, val_col))
    if not candidates:
        raise RuntimeError(f"no matching table found at {url}")
    _, t, name_col, val_col = max(candidates, key=lambda x: x[0])
    out = {}
    for _, row in t.iterrows():
        name = norm_name(row[name_col])
        val = first_int(row[val_col])
        if name and val is not None:
            out[name] = val
    return out


def transfermarkt_list(base_url, pages=4):
    """Player -> value from Transfermarkt's 'eternal' ranking tables (25 per
    page). The player name lives in the td.hauptlink anchor; the ranked value
    is the last cell of each row."""
    out = {}
    for page in range(1, pages + 1):
        url = base_url if page == 1 else f"{base_url}/page/{page}"
        resp = requests.get(url, headers=TM_UA, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.select_one("table.items")
        before = len(out)
        for row in table.select("tbody > tr"):
            link = row.select_one("td.hauptlink a")
            cells = row.find_all("td", recursive=False)
            if not link or len(cells) < 3:
                continue
            val = first_int(cells[-1].get_text(strip=True))
            name = norm_name(link.get_text(strip=True))
            if name and val is not None and name not in out:
                out[name] = val
        if len(out) == before:  # pagination exhausted or page not paginating
            break
        time.sleep(1)  # be polite
    return out


def compare(api_map, source_map, source_label, stat_label):
    diffs, unmatched = [], []
    matched = agree = 0
    for name, src_val in source_map.items():
        if name not in api_map:
            unmatched.append(name)
            continue
        matched += 1
        api_val = api_map[name]
        if api_val == src_val:
            agree += 1
        else:
            diffs.append((name, api_val, src_val))
    lines = [f"### {source_label} - {stat_label}",
             "",
             f"- Players in source list: **{len(source_map)}**",
             f"- Matched by name to API dataset: **{matched}**",
             f"- Exact agreement: **{agree}** ({agree / matched:.1%})" if matched else "- No matches",
             ""]
    if diffs:
        lines.append(f"| Player | premierleague.com | {source_label} | diff |")
        lines.append("|---|---|---|---|")
        for name, a, s in sorted(diffs, key=lambda d: -abs(d[1] - d[2])):
            lines.append(f"| {DISPLAY.get(name, name.title())} | {a} | {s} | {a - s:+d} |")
    else:
        lines.append("No value discrepancies.")
    if unmatched:
        lines.append("")
        lines.append(f"Unmatched names ({len(unmatched)}): "
                     + ", ".join(DISPLAY.get(n, n.title()) for n in unmatched))
    lines.append("")
    return "\n".join(lines)


def main():
    df = pd.read_csv("data/alltime_player_stats.csv")
    df["norm"] = df["name"].map(norm_name)
    # A handful of players share a normalised name (e.g. Danny Ward); keep the
    # one with the most appearances, which is always the one these all-time
    # lists mean.
    df = df.sort_values("appearances", ascending=False).drop_duplicates("norm")
    api_apps = dict(zip(df["norm"], df["appearances"]))
    api_goals = dict(zip(df["norm"], df["goals"]))

    print("Fetching Wikipedia top appearances...")
    wiki_apps = wiki_table(WIKI_APPS, r"app")
    print(f"  {len(wiki_apps)} players")
    print("Fetching Wikipedia 100+ goals...")
    wiki_goals = wiki_table(WIKI_GOALS, r"goal")
    print(f"  {len(wiki_goals)} players")
    print("Fetching Transfermarkt all-time top scorers...")
    tm_goals = transfermarkt_list(TM_GOALS)
    print(f"  {len(tm_goals)} players")
    print("Fetching Transfermarkt all-time appearances...")
    tm_apps = transfermarkt_list(TM_APPS)
    print(f"  {len(tm_apps)} players")

    report = [
        "# All-time PL player stats - cross-reference report",
        "",
        f"Generated {pd.Timestamp.now():%Y-%m-%d %H:%M} against data/alltime_player_stats.csv "
        f"({len(df)} unique players, source: premierleague.com official stats API).",
        "",
        compare(api_apps, wiki_apps, "Wikipedia", "appearances"),
        compare(api_goals, wiki_goals, "Wikipedia", "goals (100+ club)"),
        compare(api_goals, tm_goals, "Transfermarkt", "goals"),
        compare(api_apps, tm_apps, "Transfermarkt", "appearances"),
    ]
    with open("data/crossref_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("\nWrote data/crossref_report.md")


if __name__ == "__main__":
    main()
