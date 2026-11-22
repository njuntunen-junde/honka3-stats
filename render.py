#!/usr/bin/env python3
"""Builds index.html from data.json. Pure string templating, no deps."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
TEAM = DATA["team_title"]

MONTHS_FI = {}


def esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def is_honka(name):
    return name == TEAM


def game_result(g):
    """Returns (honka_pts, opp_pts, won, home) for a played game."""
    if is_honka(g["teamA"]):
        return g["scoreA"], g["scoreB"], g["scoreA"] > g["scoreB"], True
    else:
        return g["scoreB"], g["scoreA"], g["scoreB"] > g["scoreA"], False


def build():
    played = DATA["played"]  # newest first
    match_ids = DATA["match_ids"]
    boxscores = DATA["boxscores"]
    season_totals = DATA["season_totals"]
    upcoming = DATA["upcoming"]

    linked = len(match_ids) == len(played)

    wins = losses = 0
    home_w = home_l = away_w = away_l = 0
    home_pf = home_pa = away_pf = away_pa = 0
    pf_total = pa_total = 0

    # per player: games played (derived), wins (derived)
    derived_games = {}
    derived_wins = {}

    game_blocks = []
    for i, g in enumerate(played):
        hp, op, won, home = game_result(g)
        pf_total += hp
        pa_total += op
        if won:
            wins += 1
        else:
            losses += 1
        if home:
            if won: home_w += 1
            else: home_l += 1
            home_pf += hp; home_pa += op
        else:
            if won: away_w += 1
            else: away_l += 1
            away_pf += hp; away_pa += op

        roster = {}
        if linked:
            mid = match_ids[i]
            roster = boxscores.get(mid, {}) or {}
        for name in roster:
            derived_games[name] = derived_games.get(name, 0) + 1
            if won:
                derived_wins[name] = derived_wins.get(name, 0) + 1

        top3 = sorted(
            [(n, r.get("pts") or 0) for n, r in roster.items()],
            key=lambda x: -x[1],
        )[:3]

        badge_cls = "W" if won else "L"
        badge_letter = "V" if won else "H"
        if is_honka(g["teamA"]):
            teams_html = f'<span class="honka">{esc(TEAM)}</span> – {esc(g["teamB"])}'
        else:
            teams_html = f'{esc(g["teamA"])} – <span class="honka">{esc(TEAM)}</span>'
        score_html = f'{g["scoreA"]}–{g["scoreB"]}'

        if roster and any(v.get("pts") for v in roster.values()):
            scorers_html = "".join(
                f'<span><span class="sc-name">{esc(n)}</span> <span class="sc-pts">{p}</span></span>'
                for n, p in top3
            )
        elif roster:
            scorers_html = '<span class="none">Pelaajakohtaisia pisteitä ei kirjattu tähän otteluun</span>'
        else:
            scorers_html = '<span class="none">Kokoonpanoa ei saatavilla</span>'

        game_blocks.append(f'''    <div class="game-block">
      <div class="game">
        <div class="date">{esc(g["date"])}</div>
        <span class="badge {badge_cls}">{badge_letter}</span>
        <div class="teams">{teams_html}</div>
        <div class="score">{score_html}</div>
        <div class="loc">{esc((g.get("venue") or "").split(",")[0])}</div>
      </div>
      <div class="scorers">{scorers_html}</div>
    </div>''')

    # player table: prefer official season totals (games/points) from /players,
    # fall back to derived numbers where a player is missing from that page
    rows = []
    for name, totals in season_totals.items():
        gp = totals["games"]
        pts = totals["points"]
        if gp <= 0:
            continue
        ppg = pts / gp
        dgp = derived_games.get(name)
        dw = derived_wins.get(name, 0)
        wp = (dw / dgp * 100) if dgp else None
        rows.append({"name": name, "gp": gp, "pts": pts, "ppg": ppg, "wp": wp})

    rows.sort(key=lambda r: -r["ppg"])

    player_rows_html = []
    for r in rows:
        wp_html = (
            f'<div class="wp-bar-wrap"><div class="wp-track">'
            f'<div class="wp-fill" style="width:{r["wp"]:.1f}%"></div></div>'
            f'<span class="wp-val">{r["wp"]:.1f}%</span></div>'
            if r["wp"] is not None else
            '<span class="wp-val" style="opacity:.4">–</span>'
        )
        player_rows_html.append(f'''        <tr data-name="{esc(r["name"])}" data-gp="{r["gp"]}" data-pts="{r["pts"]}" data-ppg="{r["ppg"]:.1f}" data-wp="{r["wp"] if r["wp"] is not None else -1:.1f}">
          <td class="rank-cell"></td>
          <td class="player-name">{esc(r["name"])}</td>
          <td class="num-cell">{r["gp"]}</td><td class="num-cell">{r["pts"]}</td><td class="num-cell ppg-cell">{r["ppg"]:.1f}</td>
          <td class="num-cell">{wp_html}</td>
        </tr>''')

    # upcoming
    upcoming_html = []
    for u in upcoming:
        if is_honka(u["teamA"]):
            opp_html = f'<span class="honka">{esc(TEAM)}</span> – {esc(u["teamB"])}'
        else:
            opp_html = f'{esc(u["teamA"])} – <span class="honka">{esc(TEAM)}</span>'
        note = f' <span class="postponed">({esc(u["notes"][0])})</span>' if u.get("notes") else ""
        upcoming_html.append(f'''    <div class="upcoming-item">
      <div class="when"><div class="d">{u["weekday"].capitalize()} {esc(u["date"])}</div><div class="t">{esc(u.get("time") or "")}</div></div>
      <div class="opp">{opp_html}{note}</div>
      <div class="venue">{esc(u.get("venue") or "")}</div>
    </div>''')

    record = f"{wins}–{losses}"
    diff = pf_total - pa_total
    diff_s = f"+{diff}" if diff >= 0 else str(diff)

    # last-5 streak (played is newest-first; show oldest-of-5 -> newest, left to right)
    last5 = played[:5][::-1]
    streak_html = "".join(
        f'<span class="{"W" if game_result(g)[2] else "L"}">{"V" if game_result(g)[2] else "H"}</span>'
        for g in last5
    )

    html = TEMPLATE.format(
        team=esc(TEAM),
        season=DATA["season"],
        record=record,
        pf=pf_total, pa=pa_total, diff=diff_s,
        home_record=f"{home_w}–{home_l}", home_score=f"{home_pf}–{home_pa}", home_n=home_w + home_l,
        away_record=f"{away_w}–{away_l}", away_score=f"{away_pf}–{away_pa}", away_n=away_w + away_l,
        n_played=len(played),
        games_html="\n\n".join(game_blocks),
        player_rows_html="\n".join(player_rows_html),
        upcoming_html="\n\n".join(upcoming_html),
        streak_html=streak_html,
        generated_at=DATA["generated_at"],
    )
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print("Wrote index.html")


TEMPLATE = """<!DOCTYPE html>
<html lang="fi">
<head>
<meta charset="UTF-8">
<title>{team} – kausiyhteenveto</title>
<style>
  :root{{
    --bg:#0a0e1a;
    --bg-grad: radial-gradient(1200px 600px at 10% -10%, rgba(59,130,246,.18), transparent 60%),
               radial-gradient(1000px 500px at 110% 10%, rgba(168,85,247,.12), transparent 55%),
               #0a0e1a;
    --card:#121829;
    --card-border: rgba(255,255,255,.06);
    --win:#22c55e;
    --loss:#f43f5e;
    --text:#e6e9f2;
    --muted:#8891a7;
    --border: rgba(255,255,255,.08);
  }}
  *{{box-sizing:border-box;}}
  body{{
    margin:0;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:var(--bg-grad);
    color:var(--text);
    padding:24px 16px 48px;
    min-height:100%;
  }}
  .wrap{{max-width:900px;margin:0 auto;}}
  header{{
    position:relative; overflow:hidden;
    background:linear-gradient(135deg, rgba(59,130,246,.18), rgba(139,92,246,.14));
    border:1px solid var(--card-border);
    border-radius:20px;
    padding:30px 28px 26px;
    margin-bottom:20px;
    backdrop-filter:blur(6px);
  }}
  header::before{{
    content:""; position:absolute; inset:0;
    background:radial-gradient(400px 200px at 90% -20%, rgba(139,92,246,.35), transparent 70%);
    pointer-events:none;
  }}
  header h1{{
    margin:0 0 4px; font-size:30px; font-weight:800; letter-spacing:-.02em;
    background:linear-gradient(135deg,#fff,#b9c6ff);
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }}
  header p{{margin:0;color:var(--muted);font-size:14px;}}
  .standing{{display:flex; gap:28px; margin-top:20px; flex-wrap:wrap; position:relative;}}
  .standing .stat{{min-width:76px;}}
  .standing .stat .num{{font-size:22px;font-weight:700;letter-spacing:-.01em;}}
  .standing .stat .lbl{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:2px;}}
  .streak{{display:flex;gap:5px;margin-top:18px;position:relative;}}
  .streak span{{
    width:22px;height:22px;border-radius:6px;
    display:flex;align-items:center;justify-content:center;
    font-size:10px;font-weight:800;color:white;
  }}
  .streak span.W{{background:linear-gradient(135deg,#22c55e,#16a34a);}}
  .streak span.L{{background:linear-gradient(135deg,#f43f5e,#be123c);}}
  .card{{
    background:var(--card); border:1px solid var(--card-border); border-radius:16px;
    padding:20px 22px; margin-bottom:18px; box-shadow:0 10px 30px -15px rgba(0,0,0,.5);
  }}
  .card h2{{margin:0 0 14px;font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;}}
  .split-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px;}}
  .split-row .card{{flex:1;min-width:200px;margin-bottom:0;}}
  .splitbig{{font-size:28px;font-weight:800;letter-spacing:-.02em;}}
  .splitsub{{font-size:13px;color:var(--muted);margin-top:4px;}}
  table{{width:100%;border-collapse:collapse;font-size:14px;}}
  th{{
    text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.04em;
    color:var(--muted);padding:8px 8px;border-bottom:1px solid var(--border);font-weight:600;
  }}
  th.sortable{{cursor:pointer;user-select:none;-webkit-user-select:none;transition:color .15s;}}
  th.sortable:hover{{color:var(--text);}}
  th.sortable.active{{color:#cdd7ff;}}
  th.sortable .arrow{{display:inline-block;margin-left:4px;font-size:9px;opacity:.35;}}
  th.sortable.active .arrow{{opacity:1;}}
  td{{padding:10px 8px;border-bottom:1px solid var(--border);vertical-align:middle;}}
  tr:last-child td{{border-bottom:none;}}
  tbody tr{{transition:background .15s;}}
  tbody tr:hover{{background:rgba(255,255,255,.03);}}
  .num-cell{{text-align:right;font-variant-numeric:tabular-nums;}}
  .rank-cell{{color:var(--muted);font-size:12px;width:24px;}}
  .player-name{{font-weight:600;}}
  .ppg-cell{{font-weight:700;color:#cdd7ff;}}
  .wp-bar-wrap{{display:flex;align-items:center;gap:8px;justify-content:flex-end;}}
  .wp-track{{width:56px;height:6px;border-radius:4px;background:rgba(255,255,255,.08);overflow:hidden;flex-shrink:0;}}
  .wp-fill{{height:100%;border-radius:4px;background:linear-gradient(90deg,#22c55e,#4ade80);}}
  .wp-val{{font-variant-numeric:tabular-nums;font-weight:600;font-size:13px;width:40px;text-align:right;}}
  .game-block{{padding:11px 0;border-bottom:1px solid var(--border);}}
  .game-block:last-child{{border-bottom:none;}}
  .game{{display:flex;align-items:center;gap:12px;}}
  .game .date{{width:64px;font-size:12px;color:var(--muted);flex-shrink:0;}}
  .game .teams{{flex:1;font-size:14px;color:var(--text);}}
  .game .teams .honka{{font-weight:700;color:#cdd7ff;}}
  .game .score{{font-weight:700;font-variant-numeric:tabular-nums;width:66px;text-align:center;flex-shrink:0;}}
  .badge{{
    display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;
    border-radius:7px;font-size:12px;font-weight:800;color:white;flex-shrink:0;
  }}
  .badge.W{{background:linear-gradient(135deg,#22c55e,#16a34a);}}
  .badge.L{{background:linear-gradient(135deg,#f43f5e,#be123c);}}
  .loc{{font-size:11px;color:var(--muted);width:66px;text-align:right;flex-shrink:0;}}
  .scorers{{margin-top:7px;padding-left:36px;font-size:12px;color:var(--muted);display:flex;gap:16px;flex-wrap:wrap;}}
  .scorers .sc-name{{color:#cdd7ff;font-weight:600;}}
  .scorers .sc-pts{{color:var(--muted);}}
  .scorers .none{{font-style:italic;opacity:.7;}}
  .upcoming-item{{display:flex;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid var(--border);}}
  .upcoming-item:last-child{{border-bottom:none;}}
  .upcoming-item .when{{width:150px;flex-shrink:0;}}
  .upcoming-item .when .d{{font-weight:700;font-size:14px;}}
  .upcoming-item .when .t{{font-size:12px;color:var(--muted);}}
  .upcoming-item .opp{{flex:1;font-size:14px;}}
  .upcoming-item .venue{{font-size:12px;color:var(--muted);text-align:right;max-width:180px;}}
  .postponed{{color:var(--loss);font-size:12px;font-weight:700;}}
  footer{{text-align:center;color:var(--muted);font-size:12px;margin-top:20px;}}
  @media (max-width:480px){{
    .loc{{display:none;}}
    .game .date{{width:52px;}}
    .wp-track{{width:40px;}}
  }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <h1>{team}</h1>
    <p>Miesten III divisioona, Eteläinen alue A-lohko · Kausi {season}</p>
    <div class="standing">
      <div class="stat"><div class="num">{record}</div><div class="lbl">Voitot–Tappiot</div></div>
      <div class="stat"><div class="num">{pf}–{pa}</div><div class="lbl">Koripisteet</div></div>
      <div class="stat"><div class="num">{diff}</div><div class="lbl">Ero</div></div>
    </div>
    <div class="streak" title="5 viimeisintä ottelua, vanhin vasemmalla">{streak_html}</div>
  </header>

  <div class="split-row">
    <div class="card">
      <h2>Kotiottelut</h2>
      <div class="splitbig">{home_record}</div>
      <div class="splitsub">{home_score} ({home_n} ottelua)</div>
    </div>
    <div class="card">
      <h2>Vierasottelut</h2>
      <div class="splitbig">{away_record}</div>
      <div class="splitsub">{away_score} ({away_n} ottelua)</div>
    </div>
  </div>

  <div class="card">
    <h2>Pelatut ottelut ({n_played})</h2>
{games_html}
  </div>

  <div class="card">
    <h2>Pelaajatilastot <span style="opacity:.6;">· klikkaa saraketta sortataksesi</span></h2>
    <table id="stats-table">
      <thead>
        <tr>
          <th class="rank-cell">#</th>
          <th class="sortable" data-key="name" data-type="str">Pelaaja<span class="arrow">▲▼</span></th>
          <th class="sortable num-cell" data-key="gp" data-type="num">Ott.<span class="arrow">▲▼</span></th>
          <th class="sortable num-cell" data-key="pts" data-type="num">Pist.<span class="arrow">▲▼</span></th>
          <th class="sortable num-cell active" data-key="ppg" data-type="num" data-dir="desc">Piste-ka<span class="arrow">▲▼</span></th>
          <th class="sortable num-cell" data-key="wp" data-type="num">Voitto-%<span class="arrow">▲▼</span></th>
        </tr>
      </thead>
      <tbody>
{player_rows_html}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>Seuraavat ottelut</h2>
{upcoming_html}
  </div>

  <footer>Lähde: tulospalvelu.basket.fi · {team}, kausi {season} · Voitto-% laskettu kunkin pelaajan pelaamista otteluista, kun kokoonpanotieto on saatavilla · Päivittyy automaattisesti pelin jälkeisenä iltana · Päivitetty {generated_at}</footer>
</div>

<script>
(function(){{
  var table = document.getElementById('stats-table');
  var tbody = table.querySelector('tbody');
  var ths = Array.prototype.slice.call(table.querySelectorAll('th.sortable'));

  function renumber(){{
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    rows.forEach(function(row, i){{ row.querySelector('.rank-cell').textContent = i + 1; }});
  }}

  function sortBy(key, type, dir){{
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    rows.sort(function(a, b){{
      var av = a.getAttribute('data-' + key);
      var bv = b.getAttribute('data-' + key);
      if(type === 'num'){{
        av = parseFloat(av); bv = parseFloat(bv);
        return dir === 'asc' ? av - bv : bv - av;
      }} else {{
        av = av.toLowerCase(); bv = bv.toLowerCase();
        if(av < bv) return dir === 'asc' ? -1 : 1;
        if(av > bv) return dir === 'asc' ? 1 : -1;
        return 0;
      }}
    }});
    rows.forEach(function(row){{ tbody.appendChild(row); }});
    renumber();
  }}

  ths.forEach(function(th){{
    th.addEventListener('click', function(){{
      var key = th.getAttribute('data-key');
      var type = th.getAttribute('data-type');
      var curDir = th.getAttribute('data-dir');
      var newDir = curDir === 'desc' ? 'asc' : 'desc';
      ths.forEach(function(t){{ t.classList.remove('active'); t.removeAttribute('data-dir'); }});
      th.classList.add('active');
      th.setAttribute('data-dir', newDir);
      sortBy(key, type, newDir);
    }});
  }});

  renumber();
}})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
