# PL Milestone tracker 2

Project conventions and context for agents working here.

## Business context (why this exists)

A P Marley (jewellery/medals business) offers medals to players for career
milestones - 50, 100, 150 goals "and that". The goal is to get ahead of the
game commercially: a Teams notification when a player is *approaching* a
milestone, so a medal can be prepared/offered before it happens.

## How it works (built 2026-08-24)

The weekly Monday GitHub Action runs scripts/check_all_milestones.py, which:

- Rebuilds career totals for ALL players from the official PL stats API
  (scripts/build_alltime_stats.py) - the API's all-time numbers update live
  during the season, and current-squad membership (not the API's misleading
  currentTeam field, which means "last known club") marks who's active.
- Refreshes data/alltime_player_stats.xlsx/.csv on GitHub.
- Milestones every 50 for BOTH goals and appearances (50, 100, 150...).
- Posts a weekly Teams digest of active players within NEAR=5 of a milestone
  (deduped per day in state.json - two Monday crons both fire), plus an
  individual card per milestone actually reached (deduped forever;
  crossings detected against data/milestone_snapshot.json, baselined
  2026-08-24 so nothing historical alerts).
- Constants STEP/NEAR live at the top of check_all_milestones.py.
