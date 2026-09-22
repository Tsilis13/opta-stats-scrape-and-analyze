# Opta Player Statistics Pipeline

> **Description:** Automated data pipeline using Playwright and Python to scrape, process, and analyze football player statistics from Opta widgets, for any competition Statsperform covers.

An automated Python toolset designed to extract granular football player performance metrics directly from Opta match widgets. It handles everything from bypassing basic bot detection to aggregating multi-game statistics into normalized per-90 leaderboards. The pipeline is competition-agnostic — every script takes its inputs, outputs, and (where relevant) competition as command-line arguments, so the same scripts work for the Premier League, Greek Super League, or any other Statsperform-hosted competition.

## Features
* **Automated Match Discovery**: Leverages headless browser automation to extract valid `data-match` IDs across fixtures for any competition URL you point it at.
* **Intelligent Parsing**: Safely extracts both raw API match details and dynamic Opta Points HTML tables, handling DOM text extraction and point-to-count formula conversions.
* **Custom Analytics**: Aggregates player data across multiple matches and calculates per-90-minute rates for fair statistical comparisons.

## Prerequisites
* Python 3.8+
* `playwright`
* `beautifulsoup4`
* `requests`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/opta-stats-pipeline.git
   cd opta-stats-pipeline
   ```
2. Install the required Python packages:
   ```bash
   pip install playwright beautifulsoup4 requests
   ```
3. Install the Playwright Chromium browser:
   ```bash
   playwright install chromium
   ```

## Usage Workflow

The pipeline is split into three sequential scripts to separate extraction from analysis.

### 1. Scrape Match IDs
Run this to retrieve the match IDs for a competition's fixture list widget. Writes one bare match ID per line to the output file (no quotes, no trailing commas) — ready to feed straight into `fetch_all_stats.py`.
```bash
python scrape_ids_2026-27.py --url "https://optaplayerstats.statsperform.com/en_GB/soccer/<competition-slug>/<competition-id>/opta-player-stats" --output match_ids.txt
```
`--url` defaults to the Premier League 2026-27 widget if omitted. For another competition, copy the competition slug/ID from that competition's own Opta widget page and pass the full URL.

### 2. Fetch Raw Stats
Executes the API calls and Playwright page scrapes for the match IDs in your input file. Results are cached to your chosen output CSV to minimize redundant network requests, and rerunning skips match IDs already present in that CSV.
```bash
python fetch_all_stats.py --input match_ids.txt --output raw_stats.csv --competition "super-league-1-2026-2027/13prgjp0qzce661j00a3jy3o4"
```
`--input`, `--output`, and `--competition` are all required. `--competition` is the `<slug>/<id>` path segment from the competition's Opta match page URL (same value as used in step 1's `--url`), and it must match the competition the match IDs actually belong to, or the match-detail page lookups will fail.

*(Optional)* Add the `--refetch-opta` flag to purge existing Opta rows from the output CSV and force a fresh scrape of the Points pages, or use `--debug <MATCH_ID>` to inspect the Points/Stats toggle behavior for a specific match.

### 3. Analyze and Generate Leaderboards
Aggregates a raw stats CSV into a sorted leaderboard CSV.

```bash
python analyze_stats.py --input raw_stats.csv --output leaderboard.csv --sort-by expectedGoals --top 20 --per90 --min-minutes 180
```

**Available Arguments**:
* `--input`: Raw stats CSV to read (required — the CSV produced by `fetch_all_stats.py`).
* `--output`: Leaderboard CSV to write (required).
* `--sort-by`: The specific stat key to sort the leaderboard by (default: `expectedGoals`).
* `--top`: Number of top rows to output to the console (default: `30`).
* `--list-stats`: Print all available stat keys found in the input CSV (e.g., `op_passes`, `totalScoringAtt`, `expectedGoals`) and exit.
* `--per90`: Append per-90-minute rate columns to the output CSV.
* `--min-minutes`: Filter out players who haven't met a specific threshold of total minutes played.

## Project Structure
* `scrape_ids_2026-27.py`: Initial scraper targeting a competition's fixture list widget using a headed browser context and custom user-agent to avoid blocking. Takes `--url` (competition widget page) and `--output` (match IDs file).
* `fetch_all_stats.py`: The core extraction engine. Takes `--input` (match IDs file), `--output` (raw stats CSV), and `--competition` (slug/ID path used to build match-detail and Opta Points page URLs). Cross-references API data with visible table cells and uses an inverse Opta Points formula weight to deduce actual stat counts.
* `analyze_stats.py`: The data processor. Takes `--input` (raw stats CSV) and `--output` (leaderboard CSV). Loads the raw CSV, normalizes metrics, handles edge cases (like omitting points data from cumulative totals), and exports the final leaderboard.