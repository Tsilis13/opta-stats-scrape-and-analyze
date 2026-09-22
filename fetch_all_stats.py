import argparse
import csv
import os
import re
import shutil
import sys
import time
import requests
from bs4 import BeautifulSoup

API_URL = "https://optaplayerstats.statsperform.com/api/en_GB/soccer/playerprops/match/{match_id}"
MATCH_PAGE_URL = (
    "https://optaplayerstats.statsperform.com/en_GB/soccer/"
    "{competition}/match/view/{match_id}/match-details"
)
OPTA_POINTS_URL = (
    "https://optaplayerstats.statsperform.com/en_GB/soccer/"
    "{competition}/match/view/{match_id}/opta-points"
)

BASE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Origin": "https://optaplayerstats.statsperform.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

PAGE_WARMUP_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "User-Agent": BASE_HEADERS["User-Agent"],
}


RAW_CSV = "epl21-9.csv"
REQUEST_DELAY_SEC = 0.4

# --- Opta Points page scraping (Playwright) ---
OP_PREFIX = "op_"            # prefix for stats scraped from the Opta Points page
OP_PTS_PREFIX = "oppts_"     # prefix for the optional "Points" tab (see SCRAPE_POINTS_TAB)
HEADLESS = False             # headed mode is less likely to be blocked (same as your ID scraper)
PAGE_DELAY_SEC = 1.0         # pause between Opta Points pages
PAGE_TIMEOUT_MS = 30000
MAX_ATTEMPTS = 2
# The page has a "Points | Stats" toggle:
#   Stats  -> normal counting stats            -> stored as op_<stat>     (e.g. op_goals = 1)
#   Points -> Opta points each stat contributed -> stored as oppts_<stat> (e.g. oppts_goals = 1.0, oppts_passes = 1.54)
# Only the Stats view (normal counts) is scraped by default. Set True if you also want the
# points-formula numbers (oppts_*) - they are not needed for the leaderboard.
SCRAPE_POINTS_TAB = False
# Columns that are identical in both views, so they're only stored once (with the op_ prefix)
POINTS_TAB_SKIP = {"match_rank", "team_rank", "points", "minutes_played"}
BASE_POINTS = 5.5            # every player starts with 5.5; final rating is clamped to 3-10
USER_AGENT = BASE_HEADERS["User-Agent"]

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

def humanize_stat_key(key):
    if key in STAT_LABELS:
        return STAT_LABELS[key]
    out = []
    for ch in key:
        if ch.isupper() and out and out[-1] != " ":
            out.append(" ")
        out.append(ch)
    return "".join(out).strip().title()

def fetch_match(match_id, session, warm_up=True):
    page_url = MATCH_PAGE_URL.format(competition=COMPETITION, match_id=match_id)
    if warm_up:
        try:
            session.get(page_url, headers=PAGE_WARMUP_HEADERS, timeout=15)
        except Exception:
            pass

    api_url = API_URL.format(match_id=match_id)
    headers = dict(BASE_HEADERS)
    headers["Referer"] = page_url

    resp = session.get(api_url, headers=headers, timeout=15)
    if resp.status_code == 403:
        session.get(page_url, headers=PAGE_WARMUP_HEADERS, timeout=15)
        resp = session.get(api_url, headers=headers, timeout=15)

    resp.raise_for_status()
    return resp.json()

def extract_player_rows(match_json, match_id):
    live = match_json.get("liveData", {})
    for team in live.get("lineUp", []):
        team_name = team.get("name", "")
        for p in team.get("players", []):
            raw_stats = p.get("stats", {}) or {}
            numeric_stats = {
                k: v for k, v in raw_stats.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            yield (
                p.get("playerId"),
                p.get("matchName", "?"),
                team_name,
                match_id,
                numeric_stats,
            )

def opta_label(key):
    if key.startswith(OP_PTS_PREFIX):
        return "Opta Pts: " + key[len(OP_PTS_PREFIX):].replace("_", " ").title()
    if key.startswith(OP_PREFIX):
        return "Opta: " + key[len(OP_PREFIX):].replace("_", " ").title()
    return humanize_stat_key(key)

# ---------------------------------------------------------------------------
# Opta Points page parsing
# ---------------------------------------------------------------------------
PLAYER_ID_RE = re.compile(r"^Opta-Player-([a-z0-9]{20,})$")

def parse_opta_points_html(html, prefix=OP_PREFIX):
    """
    Returns {player_id: {"name": str, "side": "home"/"away", "stats": {key: value}}}
    Rows look like <tr role="row" data-playerside="away"> with a <th class="Opta-Player-<id>">
    and <td class="Opta-Stat Opta-Stat-shots_off_target" data-srt="1"> cells.
    """
    soup = BeautifulSoup(html, "html.parser")
    players = {}
    for tr in soup.select('tr[role="row"][data-playerside]'):
        player_id, name = None, ""
        for th in tr.find_all("th"):
            for c in th.get("class", []):
                m = PLAYER_ID_RE.match(c)
                if m:
                    player_id = m.group(1)
                    name = th.get_text(" ", strip=True)
                    break
            if player_id:
                break
        if not player_id:
            continue

        entry = players.setdefault(
            player_id, {"name": name, "side": tr.get("data-playerside", ""), "stats": {}}
        )
        for td in tr.find_all("td"):
            key_cls = next((c for c in td.get("class", []) if c.startswith("Opta-Stat-")), None)
            if not key_cls:
                continue
            raw = td.get("data-srt")
            if raw is None:
                raw = td.get_text(strip=True)
            try:
                value = round(float(raw), 4)
            except (TypeError, ValueError):
                continue
            entry["stats"].setdefault(prefix + key_cls[len("Opta-Stat-"):], value)
    return players

# ---------------------------------------------------------------------------
# Read the table AS RENDERED in the browser (what you actually see on screen).
# The old code read the data-srt attribute, which is a *sort key* and can stay the
# same when you flip between Points/Stats - so both views came out looking alike.
# innerText only returns the visible text, so hidden duplicates are ignored too.
# ---------------------------------------------------------------------------
TABLE_JS = r"""
() => {
  const idRe = /^Opta-Player-([a-z0-9]{20,})$/;
  const rows = [];
  document.querySelectorAll('tr[role="row"][data-playerside]').forEach(tr => {
    let pid = null, name = '';
    tr.querySelectorAll('th').forEach(th => {
      if (pid) return;
      for (const c of th.classList) {
        const m = idRe.exec(c);
        if (m) { pid = m[1]; name = th.innerText.trim(); break; }
      }
    });
    if (!pid) return;
    const cells = [];
    tr.querySelectorAll('td').forEach(td => {
      const cls = Array.from(td.classList).find(c => c.startsWith('Opta-Stat-'));
      if (!cls) return;
      cells.push({key: cls.slice('Opta-Stat-'.length), text: td.innerText.trim(), srt: td.getAttribute('data-srt')});
    });
    const texts = Array.from(tr.children).map(c => c.innerText.trim());
    rows.push({pid: pid, name: name, side: tr.getAttribute('data-playerside') || '', gk: texts.includes('GK'), cells: cells});
  });
  return rows;
}
"""

SNAPSHOT_JS = r"""
() => Array.from(document.querySelectorAll('tr[role="row"][data-playerside]'))
        .slice(0, 6).map(tr => tr.innerText).join('|')
"""

def _to_number(*candidates):
    """First candidate that parses as a number (handles '1,234', '85%')."""
    for raw in candidates:
        if raw is None:
            continue
        s = str(raw).strip().replace(",", "").rstrip("%")
        try:
            return round(float(s), 4)
        except ValueError:
            continue
    return None

def read_opta_table(page, prefix):
    """Same return shape as parse_opta_points_html, but uses the visible cell text (data-srt only as fallback)."""
    players = {}
    for row in page.evaluate(TABLE_JS):
        entry = players.setdefault(row["pid"], {"name": row["name"], "side": row["side"], "gk": bool(row.get("gk")), "stats": {}})
        for cell in row["cells"]:
            value = _to_number(cell["text"], cell["srt"])
            if value is None:
                continue
            entry["stats"].setdefault(prefix + cell["key"], value)
    return players

# ---------------------------------------------------------------------------
# Opta Points formula (from the page's own legend):
#   rating = clamp(5.5 + sum(count * weight), 3, 10)
# "Stats" view = the counts, "Points" view = count * weight. So one view can always be
# turned into the other, and we don't depend on the Points/Stats toggle behaving.
# ---------------------------------------------------------------------------
OPTA_WEIGHTS = {  # abbreviation: (outfield weight, goalkeeper weight)
    "G": (1.0, 1.0), "SOnT": (0.4, 0.4), "SOffT": (0.2, 0.2), "BS": (0.2, 0.2),
    "OG": (-0.5, -0.5), "A": (0.6, 0.6), "P": (0.02, 0.02), "C": (0.02, 0.02),
    "Tk": (0.2, 0.2), "INT": (0.2, 0.2), "FW": (0.1, 0.1), "FC": (-0.1, -0.1),
    "O": (-0.1, -0.1), "YC": (-0.2, -0.2), "RC": (-0.5, -0.5),
    "GC": (-0.1, -0.6), "PW": (0.4, 0.4), "SAV": (0.0, 0.5), "PSAV": (0.0, 0.5),
}
# normalised column-class name (letters only, lowercase) -> abbreviation
_ALIASES = {}
for _abbr, _names in {
    "G": "goals goal g", "SOnT": "shotsontarget shotontarget sont", "SOffT": "shotsofftarget shotofftarget sofft",
    "BS": "blockedshots blockedshot shotsblocked shotblocked bs", "OG": "owngoals owngoal og", "A": "assists assist a",
    "P": "passes pass p", "C": "crosses cross c", "Tk": "tackles tackle tk",
    "INT": "interceptions interception int", "FW": "foulswon foulwon fw",
    "FC": "foulsconceded foulconceded foulscommitted foulcommitted foulsagainst fc", "O": "offsides offside o",
    "YC": "yellowcards yellowcard cardsyellow yc", "RC": "redcards redcard cardsred rc",
    "GC": "goalsconceded goalconceded goalsconceeded goalconceeded gc", "PW": "penaltieswon penaltywon pw",
    "SAV": "saves save savestotal totalsaves sav",
    "PSAV": "penaltiessaved penaltysaved penaltysaves penaltysave penaltiessave psav",
}.items():
    for _n in _names.split():
        _ALIASES[_n] = _abbr

# The page always lists the 19 point-earning columns in this order (same as the legend).
# Used as a fallback for any column whose name isn't in _ALIASES.
STAT_COLUMN_ORDER = ["G", "SOnT", "SOffT", "BS", "OG", "A", "P", "C", "Tk", "INT",
                     "FW", "FC", "O", "YC", "RC", "GC", "PW", "SAV", "PSAV"]
NON_STAT_COLUMNS = {"match_rank", "team_rank", "points", "minutes_played"}

def _base_key(key):
    for pre in (OP_PTS_PREFIX, OP_PREFIX):
        if key.startswith(pre):
            return key[len(pre):]
    return key

def canon_stat(key):
    """'op_shots_on_target' -> 'SOnT' (None if it's not one of the point-earning stats)."""
    return _ALIASES.get(re.sub(r"[^a-z]", "", _base_key(key).lower()))

def abbr_map(stats):
    """{column key: abbreviation} for one player's stats dict.
    Column names are matched first; a column whose name isn't recognised is filled in by its
    position when the page shows exactly the 19 expected columns."""
    keys = [k for k in stats
            if _base_key(k) not in NON_STAT_COLUMNS and not _base_key(k).endswith("_rank")]
    mapping = {k: canon_stat(k) for k in keys}
    if len(keys) == len(STAT_COLUMN_ORDER):
        used = {a for a in mapping.values() if a}
        for k, abbr in zip(keys, STAT_COLUMN_ORDER):
            if mapping[k] is None and abbr not in used:
                mapping[k] = abbr
    return {k: a for k, a in mapping.items() if a}

def _clamp(x):
    return min(10.0, max(3.0, x))

def _by_abbr(pdata):
    return {a: pdata["stats"][k] for k, a in abbr_map(pdata["stats"]).items()}

def _weighted(vals, gk):
    return sum(v * OPTA_WEIGHTS[a][1 if gk else 0] for a, v in vals.items())

def detect_view(players):
    """Decide whether the scraped numbers are COUNTS or POINTS by checking them against each player's PTS.
    Returns (kind, n_ok, n_total) where kind is 'counts', 'points' or 'unknown'."""
    counts_ok = points_ok = total = 0
    for pdata in players.values():
        pts = pdata["stats"].get(OP_PREFIX + "points")
        vals = _by_abbr(pdata)
        if pts is None or not any(vals.values()):
            continue                       # players with no events fit both readings - skip them
        total += 1
        if any(abs(_clamp(BASE_POINTS + _weighted(vals, gk)) - pts) <= 0.03 for gk in (False, True)):
            counts_ok += 1
        if abs(_clamp(BASE_POINTS + sum(vals.values())) - pts) <= 0.03:
            points_ok += 1
    if total and counts_ok >= 0.8 * total and counts_ok > points_ok:
        return "counts", counts_ok, total
    if total and points_ok >= 0.8 * total and points_ok > counts_ok:
        return "points", points_ok, total
    return "unknown", max(counts_ok, points_ok), total

def points_to_counts(players):
    """The page showed the Points view: divide each contribution by its weight to get the real counts."""
    out = {}
    for pid, pdata in players.items():
        vals = _by_abbr(pdata)
        gk = pdata.get("gk") or vals.get("SAV", 0) > 0 or vals.get("PSAV", 0) > 0
        amap = abbr_map(pdata["stats"])
        new = dict(pdata["stats"])
        for k, v in pdata["stats"].items():
            a = amap.get(k)
            if a:
                w = OPTA_WEIGHTS[a][1 if gk else 0]
                new[k] = float(round(v / w)) if w else 0.0
        out[pid] = {**pdata, "stats": new}
    return out

def counts_to_points(players):
    """Points-view numbers (count * weight) computed from the counts, keyed oppts_<stat>."""
    out = {}
    for pid, pdata in players.items():
        pts = pdata["stats"].get(OP_PREFIX + "points")
        vals = _by_abbr(pdata)
        gk = bool(pdata.get("gk"))
        if pts is not None and abs(_clamp(BASE_POINTS + _weighted(vals, gk)) - pts) > 0.03 \
                and abs(_clamp(BASE_POINTS + _weighted(vals, not gk)) - pts) <= 0.03:
            gk = not gk                    # position cell not found / wrong: trust the maths
        contrib = {}
        amap = abbr_map(pdata["stats"])
        for k, v in pdata["stats"].items():
            a = amap.get(k)
            if a:
                contrib[OP_PTS_PREFIX + k[len(OP_PREFIX):]] = round(v * OPTA_WEIGHTS[a][1 if gk else 0], 4)
        out[pid] = {"name": pdata["name"], "side": pdata["side"], "stats": contrib}
    return out

class TableNotRecognised(Exception):
    pass

def points_tab_only(players):
    """Drop columns that are the same in both views (rank, PTS, minutes) from a Points-tab parse."""
    for pdata in players.values():
        pdata["stats"] = {
            k: v for k, v in pdata["stats"].items()
            if k[len(OP_PTS_PREFIX):] not in POINTS_TAB_SKIP
        }
    return players

def views_identical(stats_players, points_players):
    """True if the Points-tab parse is the same numbers as the Stats view (= the tab click didn't switch views)."""
    a = {(pid, k[len(OP_PREFIX):]): v for pid, d in stats_players.items() for k, v in d["stats"].items()}
    b = {(pid, k[len(OP_PTS_PREFIX):]): v for pid, d in points_players.items() for k, v in d["stats"].items()}
    common = set(a) & set(b)
    return bool(common) and all(a[k] == b[k] for k in common)

def check_points_reconcile(stats_players, points_players):
    """Sanity check: clamp(5.5 + sum of point contributions, 3, 10) should equal the page's PTS."""
    ok = total = 0
    for pid, sp in stats_players.items():
        pts = sp["stats"].get(OP_PREFIX + "points")
        contrib = points_players.get(pid, {}).get("stats")
        if pts is None or not contrib:
            continue
        expected = min(10.0, max(3.0, BASE_POINTS + sum(contrib.values())))
        total += 1
        ok += abs(expected - pts) <= 0.1
    return ok, total

def table_snapshot(page):
    try:
        return page.evaluate(SNAPSHOT_JS)
    except Exception:
        return ""

def describe_toggle(page):
    """outerHTML of the Points/Stats toggle, so we can see which one is marked active."""
    try:
        return page.evaluate("""() => {
            const b = document.querySelector('button[value="stats"]') || document.querySelector('button[value="points"]');
            return b && b.parentElement ? b.parentElement.outerHTML : 'toggle not found';
        }""")
    except Exception as e:
        return f"toggle lookup failed: {e}"

def active_view(page):
    """'stats' or 'points' depending on which toggle button has the Opta-On class (None if unknown)."""
    try:
        return page.evaluate("""() => {
            const s = document.querySelector('button[value="stats"]');
            const p = document.querySelector('button[value="points"]');
            if (s && s.classList.contains('Opta-On')) return 'stats';
            if (p && p.classList.contains('Opta-On')) return 'points';
            return null;
        }""")
    except Exception:
        return None

def click_view(page, name):
    """Click the 'Points' or 'Stats' toggle, then wait until the table text actually changes (max ~4s).
    Returns True if a click happened. (No change is fine if that view was already active.)"""
    other = "Stats" if name == "Points" else "Points"
    candidates = [
        # the toggle is <button type="button" value="points">Points</button> (and value="stats")
        page.locator(f'button[value="{name.lower()}"]'),
        # element whose text is `name` and which has a sibling with the other toggle's text
        page.locator(f"xpath=//*[normalize-space(text())='{name}' and ../*[normalize-space(text())='{other}']]"),
        page.get_by_text(name, exact=True),
    ]
    for loc in candidates:
        try:
            if loc.count() > 0:
                before = table_snapshot(page)
                loc.first.click(timeout=3000)
                for _ in range(10):
                    page.wait_for_timeout(250)
                    if table_snapshot(page) != before:
                        break
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    return False

def scrape_opta_points_page(page, match_id, want_points):
    """Returns (stats_players, points_players, note). Stats = real counts, whichever view the page ended up showing."""
    url = OPTA_POINTS_URL.format(competition=COMPETITION, match_id=match_id)
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    page.wait_for_selector('tr[role="row"][data-playerside]', timeout=PAGE_TIMEOUT_MS)
    page.wait_for_timeout(1500)

    # The page loads on the Points view, so switch to Stats (normal counts) and make sure it really switched.
    for _ in range(3):
        click_view(page, "Stats")
        page.wait_for_timeout(500)
        if active_view(page) != "points":
            break
    scraped = read_opta_table(page, OP_PREFIX)   # still verified against PTS below
    kind, ok, total = detect_view(scraped)

    if kind == "counts":
        stats_players, note = scraped, "read as COUNTS"
    elif kind == "points":
        stats_players, note = points_to_counts(scraped), "page showed POINTS -> converted to counts"
    else:
        first = next(iter(scraped.values()), {"stats": {}})
        raise TableNotRecognised(
            f"could not match the table to the Opta Points formula ({ok}/{total} players fit). "
            f"Column keys seen: {list(first['stats'].keys())}. Sample: {dict(list(first['stats'].items())[:8])}. "
            f"Run:  python fetch_all_stats.py --debug {match_id}  and send me the output.")
    points_players = counts_to_points(stats_players) if want_points else {}
    return stats_players, points_players, f"{note} ({ok}/{total} players reconcile with PTS)"

# ---------------------------------------------------------------------------
# CSV state / phases
# ---------------------------------------------------------------------------
def load_csv_state():
    """Returns (api_done, op_done, pts_done, player_info) based on what is already in RAW_CSV."""
    api_done, op_done, pts_done, info = set(), set(), set(), {}
    if not os.path.exists(RAW_CSV):
        return api_done, op_done, pts_done, info
    with open(RAW_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mid = row["match_id"]
            key = row["stat_key"]
            if key.startswith(OP_PTS_PREFIX):
                pts_done.add(mid)
            elif key.startswith(OP_PREFIX):
                op_done.add(mid)
            else:
                api_done.add(mid)
            info[(mid, row["player_id"])] = (row["player"], row["team"])
    return api_done, op_done, pts_done, info

def run_api_phase(match_ids, writer, f, info):
    if not match_ids:
        print("API stats: nothing new to fetch.")
        return
    print(f"\n=== Match details API: fetching {len(match_ids)} match(es) ===")
    session = requests.Session()
    for i, match_id in enumerate(match_ids, 1):
        print(f"[{i}/{len(match_ids)}] {match_id} ...", end=" ")
        try:
            data = fetch_match(match_id, session)
            n = 0
            for player_id, name, team, mid, stats in extract_player_rows(data, match_id):
                info[(mid, player_id)] = (name, team)
                for stat_name, value in stats.items():
                    writer.writerow([mid, player_id, name, team, stat_name, humanize_stat_key(stat_name), value])
                    n += 1
            print(f"ok, {n} stat rows added")
            f.flush()
        except Exception as e:
            print(f"FAILED ({e})")
        time.sleep(REQUEST_DELAY_SEC)

def run_opta_points_phase(match_ids, need_op, need_pts, writer, f, info):
    """need_op / need_pts: sets of match_ids still missing the Stats view / Points tab data."""
    if not match_ids:
        print("Opta Points: nothing new to fetch.")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. Run:  pip install playwright && playwright install chromium")
        return

    print(f"\n=== Opta Points pages: fetching {len(match_ids)} match(es) ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        try:
            for i, match_id in enumerate(match_ids, 1):
                print(f"[{i}/{len(match_ids)}] {match_id} ...", end=" ")
                want_points = match_id in need_pts
                stats_players, points_players, note, error, fatal = None, {}, "", None, None
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    try:
                        stats_players, points_players, note = scrape_opta_points_page(page, match_id, want_points)
                        if stats_players:
                            break
                    except TableNotRecognised as e:
                        fatal = e
                        break
                    except Exception as e:
                        error = e
                if fatal:
                    print(f"\nSTOPPING: {fatal}")
                    break
                if not stats_players:
                    print(f"FAILED ({error})" if error else "no player rows found, skipped")
                    continue

                n = 0
                for source, wanted in ((stats_players, match_id in need_op), (points_players, want_points)):
                    if not wanted:
                        continue
                    for player_id, pdata in source.items():
                        name, team = info.get((match_id, player_id), (pdata["name"], pdata["side"]))
                        for key, value in pdata["stats"].items():
                            writer.writerow([match_id, player_id, name, team, key, opta_label(key), value])
                            n += 1

                print(f"ok, {len(stats_players)} players, {n} stat rows added | {note}")
                f.flush()
                time.sleep(PAGE_DELAY_SEC)
        finally:
            browser.close()

def purge_opta_rows():
    """Remove every op_* / oppts_* row from RAW_CSV (backup kept) so those phases run again."""
    if not os.path.exists(RAW_CSV):
        print(f"{RAW_CSV} not found - nothing to purge.")
        return
    backup = RAW_CSV + ".bak"
    shutil.copyfile(RAW_CSV, backup)
    tmp = RAW_CSV + ".tmp"
    kept = removed = 0
    with open(RAW_CSV, "r", encoding="utf-8", newline="") as src, open(tmp, "w", encoding="utf-8", newline="") as dst:
        reader, writer = csv.reader(src), csv.writer(dst)
        header = next(reader)
        writer.writerow(header)
        idx = header.index("stat_key")
        for row in reader:
            if row[idx].startswith(OP_PREFIX) or row[idx].startswith(OP_PTS_PREFIX):
                removed += 1
            else:
                writer.writerow(row)
                kept += 1
    os.replace(tmp, RAW_CSV)
    print(f"Purged {removed} Opta rows, kept {kept}. Backup: {backup}")

def debug_one_match(match_id):
    """Open one match, flip through both views and print what the browser really shows vs data-srt."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context(user_agent=USER_AGENT).new_page()
        page.goto(OPTA_POINTS_URL.format(competition=COMPETITION, match_id=match_id), wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        page.wait_for_selector('tr[role="row"][data-playerside]', timeout=PAGE_TIMEOUT_MS)
        page.wait_for_timeout(1500)
        print("\nTOGGLE HTML on load:\n", describe_toggle(page))
        for view in ("Points", "Stats"):
            clicked = click_view(page, view)
            print(f"\n===== after clicking '{view}' (clicked={clicked}) =====")
            print("TOGGLE HTML:\n", describe_toggle(page))
            rows = page.evaluate(TABLE_JS)
            if rows:
                print("First player:", rows[0]["name"], "| active toggle:", active_view(page))
                first_stats = {OP_PREFIX + c["key"]: c["text"] for c in rows[0]["cells"]}
                amap = abbr_map(first_stats)
                for c in rows[0]["cells"]:
                    abbr = amap.get(OP_PREFIX + c["key"], "-")
                    print(f"  {c['key']:<28} {abbr:<6} text={c['text']!r:<10} data-srt={c['srt']!r}")
            kind, ok, total = detect_view(read_opta_table(page, OP_PREFIX))
            print(f"Numbers on screen look like: {kind.upper()} ({ok}/{total} players reconcile with PTS)")
            with open(f"debug_{view.lower()}.html", "w", encoding="utf-8") as fh:
                fh.write(page.content())
            print(f"(saved debug_{view.lower()}.html)")
        browser.close()

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument(
        "--input",
        required=True,
        help="text file containing one match ID per line"
    )

    ap.add_argument(
        "--output",
        required=True,
        help="output CSV file"
    )

    ap.add_argument(
        "--refetch-opta",
        action="store_true",
        help="delete all op_/oppts_ rows from the CSV first, then re-scrape the Opta Points pages"
    )

    ap.add_argument(
        "--debug",
        metavar="MATCH_ID",
        help="inspect one match's Points/Stats toggle and exit"
    )

    ap.add_argument(
        "--competition",
        required=True,
        help=(
            "competition slug/id path, e.g. "
            "'super-league-1-2026-2027/13prgjp0qzce661j00a3jy3o4' "
        )
    )

    args = ap.parse_args()

    global RAW_CSV, COMPETITION
    RAW_CSV = args.output
    COMPETITION = args.competition

    with open(args.input, "r", encoding="utf-8") as fh:
        all_ids = [
            re.sub(r'^[\'",\s]+|[\'",\s]+$', '', line)
            for line in fh
            if line.strip() and not line.lstrip().startswith("#")
        ]
        all_ids = [x for x in all_ids if x]

    all_ids = list(dict.fromkeys(all_ids))

    if not all_ids:
        print(f"No match IDs found in {args.input}")
        return

    if args.debug:
        debug_one_match(args.debug)
        return
    if args.refetch_opta:
        purge_opta_rows()

    api_done, op_done, pts_done, info = load_csv_state()
    need_api = [m for m in all_ids if m not in api_done]
    need_op = {m for m in all_ids if m not in op_done}
    need_pts = {m for m in all_ids if SCRAPE_POINTS_TAB and m not in pts_done}
    need_opta = [m for m in all_ids if m in need_op or m in need_pts]

    if not need_api and not need_opta:
        print(f"All {len(all_ids)} match IDs are already cached in {RAW_CSV}.")
        return

    out_dir = os.path.dirname(RAW_CSV)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    file_exists = os.path.exists(RAW_CSV)
    with open(RAW_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["match_id", "player_id", "player", "team", "stat_key", "stat_label", "value"])
        run_api_phase(need_api, writer, f, info)
        run_opta_points_phase(need_opta, need_op, need_pts, writer, f, info)

    print(f"\nDone. Saved raw match data to {RAW_CSV}")

if __name__ == "__main__":
    main()