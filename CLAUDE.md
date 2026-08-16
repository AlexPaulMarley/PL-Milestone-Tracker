# PL Milestone tracker 2

Project conventions and context for agents working here.

## Business context (why this exists)

A P Marley (jewellery/medals business) offers medals to players for career
milestones - 50, 100, 150 goals "and that". The goal is to get ahead of the
game commercially: a Teams notification when a player is *approaching* a
milestone, so a medal can be prepared/offered before it happens.

## Agreed direction (recorded 2026-08-16, not yet built - wait for the user
## to say they're ready before building)

- The weekly Monday GitHub Action should eventually scan ALL players using the
  all-time stats dataset (scripts/build_alltime_stats.py), not just the
  hand-picked few in data/players.csv.
- data/alltime_player_stats.xlsx should be refreshed weekly on GitHub.
- Teams alerts: warn when a player is near a milestone, alert when reached.
- Open questions parked with the user: milestone intervals (every 50 goals?
  appearances too?), "near" threshold (within 3/5/10?), weekly digest vs
  individual alert cards.
