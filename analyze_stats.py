import argparse
import csv
import os
import sys
from collections import defaultdict


STAT_LABELS = {
    "totalScoringAtt": "Total Shots",
    "ontargetScoringAtt": "Shots on Target",
    "attemptsIbox": "Shots Inside Box",
    "attemptsObox": "Shots Outside Box",
    "attRfGoal": "Goals (Right Foot)",
    "attLfGoal": "Goals (Left Foot)",
    "attHdGoal": "Goals (Header)",
    "attHdTotal": "Headed Attempts",
    "attPenGoal": "Penalty Goals",
    "attFreekickGoal": "Free Kick Goals",
    "attOboxGoal": "Goals (Outside Box)",
    "attIboxGoal": "Goals (Inside Box)",
    "goals": "Goals",
    "hitWoodwork": "Hit Woodwork",
    "blockedScoringAtt": "Shots Blocked",
    "shotOffTarget": "Shots off Target",
    "expectedGoals": "Expected Goals (xG)",
    "shotCreated": "Shots Created (Assists + Key Passes)",
    "fantasyAssist": "Fantasy Assist",
    "goalAssist": "Assists",
    "keyPass": "Key Passes",
    "totalPass": "Total Passes",
    "accuratePass": "Accurate Passes",
    "totalCross": "Total Crosses",
    "accurateCross": "Accurate Crosses",
    "totalLongBalls": "Long Balls",
    "accurateLongBalls": "Accurate Long Balls",
    "totalThrows": "Throw-ins",
    "goalKicks": "Goal Kicks",
    "touches": "Touches",
    "totalContest": "Dribble Attempts",
    "wonContest": "Dribbles Won",
    "totalTackle": "Tackles",
    "wonTackle": "Tackles Won",
    "interception": "Interceptions",
    "totalClearance": "Clearances",
    "outfielderBlock": "Blocks",
    "totalRedCard": "Red Cards",
    "totalYellowCard": "Yellow Cards",
    "foulCommitted": "Fouls Committed",
    "foulGiven": "Fouls Won",
    "offsideProvoked": "Offsides Provoked",
    "wasFouled": "Was Fouled",
    "saves": "Saves",
    "goalsConceded": "Goals Conceded",
    "totalSaves": "Total Saves",
    "penaltySave": "Penalty Saves",
    "punches": "Punches",
    "keeperClaim": "Claims",
    "minsPlayed": "Minutes Played",
    "gameStarted": "Started",
    "totalSubOn": "Substituted On",
    "totalSubOff": "Substituted Off",
}

# Opta Points page stats: "op_" = normal counts (Stats view), "oppts_" = points earned per stat (Points view).
# Only normal counts are used here - any "oppts_" rows left in the CSV are ignored.
# These make no sense when summed over matches.
SKIP_KEYS = {"op_match_rank", "op_team_rank", "op_minutes_played"}
SKIP_PREFIXES = ("oppts_",)

def humanize_stat_key(key):
    if key in STAT_LABELS:
        return STAT_LABELS[key]
    for prefix, name in (("oppts_", "Opta Pts"), ("op_", "Opta")):
        if key.startswith(prefix):
            return f"{name}: " + key[len(prefix):].replace("_", " ").title()
    out = []
    for ch in key:
        if ch.isupper() and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
    return "".join(out).strip().title()

def main():
    parser = argparse.ArgumentParser(description="Analyze local Opta player stats.")
    parser.add_argument("--sort-by", default="expectedGoals", help="Stat key to sort by (default: expectedGoals)")
    parser.add_argument("--top", type=int, default=30, help="How many rows to print (default: 30)")
    parser.add_argument("--list-stats", action="store_true", help="List all stat keys found in CSV and exit")
    parser.add_argument("--per90", action="store_true", help="Include per-90 rates in CSV output")
    parser.add_argument("--min-minutes", type=int, default=0, help="Minimum total minutes threshold")
    parser.add_argument("--input", required=True, help=f"Raw stats CSV to read ")
    parser.add_argument("--output", required=True, help=f"Leaderboard CSV to write ")
    args = parser.parse_args()

    global RAW_CSV, LEADERBOARD_CSV
    RAW_CSV = args.input
    LEADERBOARD_CSV = args.output

    if not os.path.exists(RAW_CSV):
        print(f"Error: '{RAW_CSV}' not found. Run fetch_raw_stats.py first.")
        sys.exit(1)

    agg = defaultdict(lambda: {
        "name": "", "team": "", "matches": set(),
        "totals": defaultdict(float),
    })
    all_stat_keys = set()

    with open(RAW_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p_id = row["player_id"]
            stat_key = row["stat_key"]
            val = float(row["value"])
            
            agg[p_id]["name"] = row["player"]
            if row["team"]:
                agg[p_id]["team"] = row["team"]
            agg[p_id]["matches"].add(row["match_id"])
            if stat_key in SKIP_KEYS or stat_key.startswith(SKIP_PREFIXES):
                continue
            agg[p_id]["totals"][stat_key] += val
            all_stat_keys.add(stat_key)

    all_stat_keys = sorted(all_stat_keys)
    minutes_key = "minsPlayed" if "minsPlayed" in all_stat_keys else None
    per90_keys = {f"{k}_per90" for k in all_stat_keys if k != minutes_key}
    valid_sort_keys = set(all_stat_keys) | per90_keys

    if args.list_stats:
        print(f"\nDiscovered {len(all_stat_keys)} stat keys:\n")
        width = max(len(k) for k in all_stat_keys) + 2
        for k in all_stat_keys:
            print(f"  {k:<{width}} {humanize_stat_key(k)}")
        sys.exit(0)

    if args.sort_by not in valid_sort_keys:
        print(f"Error: '{args.sort_by}' is not a valid stat key. Use --list-stats to see options.")
        sys.exit(1)

    if args.sort_by in per90_keys and not args.per90:
        args.per90 = True

    leaderboard = []
    for p_id, a in agg.items():
        games = len(a["matches"])
        row = {"player": a["name"], "team": a["team"], "games": games}
        minutes = a["totals"].get(minutes_key, 0) if minutes_key else 0
        
        for stat_name in all_stat_keys:
            total = a["totals"].get(stat_name, 0.0)
            row[stat_name] = round(total, 3) if total != int(total) else int(total)
            if stat_name != minutes_key:
                per90 = (total / minutes * 90) if minutes else 0.0
                row[f"{stat_name}_per90"] = round(per90, 3)
        leaderboard.append(row)

    if args.min_minutes and minutes_key:
        leaderboard = [r for r in leaderboard if r.get(minutes_key, 0) >= args.min_minutes]

    leaderboard.sort(key=lambda r: r.get(args.sort_by, 0), reverse=True)

    stat_columns = list(all_stat_keys)
    if args.per90:
        stat_columns += [f"{k}_per90" for k in all_stat_keys if k != minutes_key]

    def column_header(key):
        if key.endswith("_per90"):
            base = key[: -len("_per90")]
            return f"{humanize_stat_key(base)} per90 ({key})"
        return f"{humanize_stat_key(key)} ({key})"

    header_row = ["Player", "Team", "Games"] + [column_header(k) for k in stat_columns]

    out_dir = os.path.dirname(LEADERBOARD_CSV)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(LEADERBOARD_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header_row)
        for r in leaderboard:
            w.writerow([r["player"], r["team"], r["games"]] + [r.get(k, "") for k in stat_columns])

    print(f"\nWrote {LEADERBOARD_CSV} sorted by '{humanize_stat_key(args.sort_by.replace('_per90',''))}' ({args.sort_by}).\n")
    print(f"{'Player':<26}{'Team':<18}{'GP':>4}{humanize_stat_key(args.sort_by.replace('_per90','')):>22}")
    print("-" * 70)
    for r in leaderboard[:args.top]:
        print(f"{r['player']:<26}{r['team']:<18}{r['games']:>4}{r.get(args.sort_by, ''):>22}")

if __name__ == "__main__":
    main()