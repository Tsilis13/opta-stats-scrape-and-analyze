# Opta Player Statistics Pipeline

> **Description:** Automated data pipeline using Playwright and Python to scrape, process, and analyze Premier League player statistics from Opta widgets.

An automated Python toolset designed to extract granular football player performance metrics directly from Opta match widgets. It handles everything from bypassing basic bot detection to aggregating multi-game statistics into normalized per-90 leaderboards.

## Features
* **Automated Match Discovery**: Leverages headless browser automation to extract valid `data-match` IDs across fixtures.
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
Run this to retrieve the latest match IDs for the current season. You will need to manually copy the printed IDs into the `MATCH_IDS` list inside `fetch_all_stats.py`.
```bash
python scrape_ids_2026-27.py
```

### 2. Fetch Raw Stats
Executes the API calls and Playwright page scrapes for the IDs defined in the script. The data is cached locally to `epl21-9.csv` to minimize redundant network requests.
```bash
python fetch_all_stats.py
```
*(Optional)* Add the `--refetch-opta` flag to purge existing Opta rows and force a fresh scrape of the Points pages, or use `--debug <MATCH_ID>` to inspect the Points/Stats toggle behavior for a specific match.

### 3. Analyze and Generate Leaderboards
Aggregates the raw CSV data into a sorted leaderboard (`epl21-9_leaderboard.csv`). 

```bash
python analyze_stats.py --sort-by expectedGoals --top 20 --per90 --min-minutes 180
```

**Available Arguments**:
* `--sort-by`: The specific stat key to sort the leaderboard by (default: `expectedGoals`).
* `--top`: Number of top rows to output to the console (default: `30`).
* `--list-stats`: Print all 40 available stat keys (e.g., `op_passes`, `totalScoringAtt`, `expectedGoals`) and exit.
* `--per90`: Append per-90-minute rate columns to the output CSV.
* `--min-minutes`: Filter out players who haven't met a specific threshold of total minutes played.

## Project Structure
* `scrape_ids_2026-27.py`: Initial scraper targeting the main fixture list using a headed browser context and custom user-agent to avoid blocking.
* `fetch_all_stats.py`: The core extraction engine. It cross-references API data with visible table cells and uses an inverse Opta Points formula weight to deduce actual stat counts.
* `analyze_stats.py`: The data processor. Loads the raw CSV, normalizes metrics, handles edge cases (like omitting points data from cumulative totals), and exports the final leaderboard.
