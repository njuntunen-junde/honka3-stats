#!/usr/bin/env python3
"""
Scrapes tulospalvelu.basket.fi for Honka 3 (Miesten III divisioona, Eteläinen alue)
and writes data.json with everything render.py needs.

Only reads public, rendered pages on tulospalvelu.basket.fi (allowed by its
robots.txt — only /person/ is disallowed there). Does NOT call the
koripallo-api.torneopal.net REST API directly: that host's robots.txt
disallows it, so we go through the same rendered pages a browser would.
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

TEAM_ID = "815"
CLUB_ID = "1515"
SEASON = "2026-2027"
TEAM_TITLE = "Honka 3"
BASE = "https://tulospalvelu.basket.fi"
OUT = Path(__file__).parent / "data.json"

WEEKDAY_DATE_RE = re.compile(r"^(ma|ti|ke|to|pe|la|su)\s+(\d{1,2}\.\d{1,2}\.)$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def norm_lines(text):
    lines = [l.strip() for l in text.split("\n")]
    return [l for l in lines if l != ""]


def goto_text(page, url, wait_selector=None, settle=1200):
    page.goto(url, wait_until="networkidle", timeout=45000)
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=15000)
        except Exception:
            pass
    page.wait_for_timeout(settle)
    return page.inner_text("body")


def parse_results(lines):
    games = []
    i, n = 0, len(lines)
    while i < n:
        m = WEEKDAY_DATE_RE.match(lines[i])
        if m:
            weekday, date = m.groups()
            competition = lines[i - 1] if i > 0 else None
            idx = i + 1
            time_s = None
            if idx < n and TIME_RE.match(lines[idx]):
                time_s = lines[idx]
                idx += 1
            venue = lines[idx] if idx < n else None
            idx += 1
            try:
                team_a = lines[idx]; idx += 1
                score_a = int(lines[idx]); idx += 1
                idx += 1  # "–"
                score_b = int(lines[idx]); idx += 1
                team_b = lines[idx]; idx += 1
            except (ValueError, IndexError):
                i += 1
                continue
            attendance = None
            if idx < n and lines[idx].startswith("Yleisö"):
                idx += 1
                if idx < n and lines[idx].isdigit():
                    attendance = int(lines[idx])
                    idx += 1
            games.append({
                "weekday": weekday, "date": date, "time": time_s,
                "competition": competition, "venue": venue,
                "teamA": team_a, "scoreA": score_a,
                "scoreB": score_b, "teamB": team_b,
                "attendance": attendance,
            })
            i = idx
        else:
            i += 1
    return games


def parse_fixture(lines):
    games = []
    i, n = 0, len(lines)
    while i < n:
        m = WEEKDAY_DATE_RE.match(lines[i])
        if m:
            weekday, date = m.groups()
            idx = i + 1
            time_s = None
            if idx < n and TIME_RE.match(lines[idx]):
                time_s = lines[idx]
                idx += 1
            venue = lines[idx] if idx < n else None
            idx += 1
            team_a = lines[idx] if idx < n else None
            idx += 1
            notes = []
            team_b = None
            # scan ahead until the next weekday/date marker or EOF
            while idx < n and not WEEKDAY_DATE_RE.match(lines[idx]):
                if lines[idx] == "–":
                    idx += 1
                    continue
                if team_b is None and idx + 1 >= n:
                    team_b = lines[idx]; idx += 1
                elif team_b is None:
                    # heuristic: last plain line before the next date marker is team B;
                    # anything earlier is a note (e.g. "Ottelu siirtyy")
                    look = idx
                    while look < n and not WEEKDAY_DATE_RE.match(lines[look]):
                        look += 1
                    team_b = lines[look - 1]
                    notes = lines[idx:look - 1]
                    idx = look
                else:
                    idx += 1
            games.append({
                "weekday": weekday, "date": date, "time": time_s,
                "venue": venue, "teamA": team_a, "teamB": team_b,
                "notes": notes,
            })
            i = idx
        else:
            i += 1
    return games


def split_name_row(line, two_nums_required=False):
    """'<jersey?> <name words...> [| C] <num> [<num>]' -> (jersey, name, nums[])"""
    tokens = line.replace("|", " | ").split()
    # drop a trailing/embedded captain marker
    tokens = [t for t in tokens if t != "|" and t != "C"]
    nums = []
    while tokens and re.fullmatch(r"-?\d+", tokens[-1]) and len(nums) < 2:
        nums.insert(0, tokens.pop())
    if two_nums_required and len(nums) != 2:
        return None
    if not nums:
        return None
    jersey = None
    if tokens and re.fullmatch(r"-?\d+", tokens[0]):
        jersey = tokens.pop(0)
    name = " ".join(tokens).strip()
    if not name:
        return None
    return jersey, name, [int(x) for x in nums]


def parse_players_page(lines):
    """Season totals from /players: {name: {games, points}}"""
    out = {}
    try:
        start = lines.index("Pelaajat") + 1
    except ValueError:
        start = 0
    try:
        end = lines.index("Taustahenkilöt")
    except ValueError:
        end = len(lines)
    for line in lines[start:end]:
        if line in ("#", "Nimi", "O", "P", "O:", "Ottelut", "P:", "Pisteet"):
            continue
        parsed = split_name_row(line)
        if not parsed:
            continue
        _, name, nums = parsed
        games_p = nums[0]
        points = nums[1] if len(nums) > 1 else 0
        out[name] = {"games": games_p, "points": points}
    return out


def parse_lineups(text, honka_title):
    """Returns {name: {pts, fouls}} for Honka's roster in this game, or None
    if the page has no Kokoonpanot content at all (needs an /events fallback)."""
    lines = norm_lines(text)
    if "Kokoonpanot" not in lines:
        return None
    start = lines.index("Kokoonpanot")
    try:
        h = lines.index(honka_title, start)
    except ValueError:
        return None
    # skip the 4 column-header lines: # / Nimi / P / V
    idx = h + 1
    skipped = 0
    while idx < len(lines) and skipped < 4 and lines[idx] in ("#", "Nimi", "P", "V"):
        idx += 1
        skipped += 1
    roster = {}
    while idx < len(lines):
        if lines[idx] == "Aloitusviisikko alleviivattu":
            break
        parsed = split_name_row(lines[idx], two_nums_required=True)
        if not parsed:
            break
        _, name, nums = parsed
        roster[name] = {"pts": nums[0], "fouls": nums[1]}
        idx += 1
    return roster if roster else None


def parse_events_fallback(text, known_honka_names):
    """Best-effort per-player points from the play-by-play feed, used only
    when a game's /lineups page has no boxscore at all."""
    lines = norm_lines(text)
    pts = {}
    participants = set()
    name_re = re.compile(r"^#-?\d+\s+(.+)$")
    for i, line in enumerate(lines):
        m = name_re.match(line)
        if not m:
            continue
        raw_name = m.group(1).strip()
        # events show fuller names; match against known roster by prefix
        match = next((n for n in known_honka_names if raw_name == n or raw_name.startswith(n)), None)
        if not match:
            continue
        participants.add(match)
        if i + 1 < len(lines) and re.fullmatch(r"\d+pt", lines[i + 1]):
            pts[match] = pts.get(match, 0) + int(lines[i + 1][:-2])
    roster = {name: {"pts": pts.get(name, 0), "fouls": None} for name in participants}
    return roster if roster else None


def collect_match_ids(page, path):
    """The results/fixture lists are virtualized; scroll repeatedly to force
    every row into the DOM and collect every /match/<id>/... link."""
    page.goto(f"{BASE}{path}?title=Honka+3&club_id={CLUB_ID}&season={SEASON}",
              wait_until="networkidle", timeout=45000)
    page.wait_for_timeout(1000)
    ids = []
    seen_heights = []
    for _ in range(40):
        hrefs = page.eval_on_selector_all(
            'a[href*="/match/"]', "els => els.map(e => e.getAttribute('href'))"
        )
        for h in hrefs:
            m = re.search(r"/match/(\d+)/", h)
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
        height = page.evaluate("document.body.scrollHeight")
        seen_heights.append(height)
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(300)
        if len(seen_heights) > 6 and len(set(seen_heights[-6:])) == 1:
            break
    return ids


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 2000})

        print("Fetching player season totals…", file=sys.stderr)
        players_text = goto_text(
            page, f"{BASE}/team/{TEAM_ID}/players?title=Honka+3&club_id={CLUB_ID}&season={SEASON}"
        )
        season_totals = parse_players_page(norm_lines(players_text))
        known_names = set(season_totals.keys())

        print("Fetching results…", file=sys.stderr)
        results_text = goto_text(page, f"{BASE}/team/{TEAM_ID}/results?title=Honka+3&club_id={CLUB_ID}&season={SEASON}")
        played = parse_results(norm_lines(results_text))

        print("Fetching fixture…", file=sys.stderr)
        fixture_text = goto_text(page, f"{BASE}/team/{TEAM_ID}/fixture?title=Honka+3&club_id={CLUB_ID}&season={SEASON}")
        upcoming = parse_fixture(norm_lines(fixture_text))

        print("Collecting match ids from results list…", file=sys.stderr)
        match_ids = collect_match_ids(page, f"/team/{TEAM_ID}/results")
        print(f"  found {len(match_ids)} match ids", file=sys.stderr)

        boxscores = {}
        for mid in match_ids:
            try:
                text = goto_text(page, f"{BASE}/match/{mid}/lineups", settle=800)
                roster = parse_lineups(text, TEAM_TITLE)
                if roster is None:
                    print(f"  {mid}: lineups empty, falling back to /events", file=sys.stderr)
                    ev_text = goto_text(page, f"{BASE}/match/{mid}/events", settle=800)
                    roster = parse_events_fallback(ev_text, known_names)
                boxscores[mid] = roster or {}
            except Exception as e:
                print(f"  {mid}: FAILED ({e}) — keeping empty boxscore", file=sys.stderr)
                boxscores[mid] = {}
            time.sleep(0.3)

        browser.close()

    data = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "team_title": TEAM_TITLE,
        "season": SEASON,
        "season_totals": season_totals,
        "played": played,
        "upcoming": upcoming,
        "match_ids": match_ids,
        "boxscores": boxscores,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
