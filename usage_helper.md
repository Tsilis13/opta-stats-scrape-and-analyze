# Stat Key Reference

The list below is what `analyze_stats.py --list-stats` discovers from a given raw stats CSV — the exact set depends on which stats were present in that CSV, so regenerate it per-competition/per-season with:

```bash
python analyze_stats.py --input <raw_stats.csv> --output <leaderboard.csv> --list-stats
```

Keys prefixed `op_` come from the Opta Points page (scraped counts, not the API). Everything else comes from the match-details API.

## Match API stats

| Key | Description |
|---|---|
| `accuratePass` | Accurate Passes |
| `attFreekickGoal` | Free Kick Goals |
| `attHdGoal` | Goals (Header) |
| `attHdTotal` | Headed Attempts |
| `attLfGoal` | Goals (Left Foot) |
| `attOboxGoal` | Goals (Outside Box) |
| `attPenGoal` | Penalty Goals |
| `attRfGoal` | Goals (Right Foot) |
| `attemptsIbox` | Shots Inside Box |
| `attemptsObox` | Shots Outside Box |
| `expectedGoals` | Expected Goals (xG) |
| `fantasyAssist` | Fantasy Assist |
| `gameStarted` | Started |
| `goalKicks` | Goal Kicks |
| `hitWoodwork` | Hit Woodwork |
| `minsPlayed` | Minutes Played |
| `shotCreated` | Shots Created (Assists + Key Passes) |
| `totalSubOn` | Substituted On |
| `totalThrows` | Throw-ins |

## Opta Points page stats (`op_` prefix)

| Key | Description |
|---|---|
| `op_assists` | Opta: Assists |
| `op_cards_red` | Opta: Cards Red |
| `op_cards_yellow` | Opta: Cards Yellow |
| `op_crosses` | Opta: Crosses |
| `op_fouls_conceded` | Opta: Fouls Conceded |
| `op_fouls_won` | Opta: Fouls Won |
| `op_goals` | Opta: Goals |
| `op_goals_conceeded` | Opta: Goals Conceded *(sic — source site's own spelling)* |
| `op_interceptions` | Opta: Interceptions |
| `op_offsides` | Opta: Offsides |
| `op_own_goals` | Opta: Own Goals |
| `op_passes` | Opta: Passes |
| `op_penalties_saved` | Opta: Penalties Saved |
| `op_penalties_won` | Opta: Penalties Won |
| `op_points` | Opta: Points |
| `op_saves_total` | Opta: Saves Total |
| `op_shots_blocked` | Opta: Shots Blocked |
| `op_shots_off_target` | Opta: Shots Off Target |
| `op_shots_on_target` | Opta: Shots On Target |
| `op_tackles` | Opta: Tackles |

## Notes

- Any stat key above also has a `<key>_per90` variant available for `--sort-by` once you pass `--per90` (per-90-minute rate, normalized on `minsPlayed`).
- `op_match_rank`, `op_team_rank`, and `op_minutes_played` are scraped but excluded from aggregation (they're per-match ranks/duplicates, not cumulative stats).
- `oppts_*` keys (Opta Points-view contributions) are ignored entirely by `analyze_stats.py` — only `op_*` (Stats-view counts) are aggregated.
