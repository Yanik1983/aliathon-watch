"""Render the static status page (docs/index.html)."""
from __future__ import annotations

import html as htmllib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from watch import config
from watch import history as history_mod
from watch.parser import Grid

CYPRUS = ZoneInfo("Europe/Nicosia")

_CSS = """
:root { --bg:#fafafa; --fg:#1a1a1a; --muted:#666; --open:#c8f0c8; --open-fg:#0a5a0a;
        --sold:#f6d3d3; --sold-fg:#8a1c1c; --line:#ddd; --card:#fff; --accent:#0b5ed7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#111; --fg:#eee; --muted:#aaa; --open:#1f4d1f; --open-fg:#b8f0b8;
          --sold:#4d1f1f; --sold-fg:#f0b8b8; --line:#333; --card:#1b1b1b; --accent:#6ea8fe; }
}
* { box-sizing:border-box; }
body { margin:0; padding:16px; font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
       background:var(--bg); color:var(--fg); }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
.sub { color:var(--muted); margin:0 0 1rem; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; }
.ok { border-left:6px solid #2e9e4f; }
.none { border-left:6px solid var(--muted); }
.fail { border-left:6px solid #d9534f; }
table { border-collapse:collapse; width:100%; }
.wrap { overflow-x:auto; }
th, td { border:1px solid var(--line); padding:4px 6px; text-align:center; white-space:nowrap; font-size:12px; }
th.room, td.room { text-align:left; font-weight:600; position:sticky; left:0; background:var(--card); }
td.open { background:var(--open); color:var(--open-fg); font-weight:600; }
td.sold { background:var(--sold); color:var(--sold-fg); }
tr.target td.room { color:var(--accent); }
ul.windows { list-style:none; padding:0; margin:0; }
ul.windows li { padding:8px 0; border-bottom:1px solid var(--line); }
ul.windows li:last-child { border-bottom:0; }
a.book { display:inline-block; margin-left:8px; padding:4px 10px; background:var(--accent); color:#fff;
         border-radius:6px; text-decoration:none; font-weight:600; }
.legend span { display:inline-block; padding:2px 8px; border-radius:4px; margin-right:8px; }
footer { color:var(--muted); font-size:12px; margin-top:16px; }
"""


def _fmt_dt(dt: datetime | None) -> tuple[str, str]:
    if dt is None:
        return ("never", "never")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    cy = dt.astimezone(CYPRUS).strftime("%Y-%m-%d %H:%M Cyprus")
    return utc, cy


def _fmt_day(d: date) -> str:
    return d.strftime("%a %d %b")


def _windows_section(confirmed: dict) -> str:
    if not confirmed:
        return (
            '<section class="card none"><h2>No bookable stays right now</h2>'
            "<p>Watching for 5–8 nights in a One Bedroom or Superior One Bedroom "
            "Apartment, check-in from Sat 14 Aug 2027, check-out by Sun 29 Aug 2027.</p></section>"
        )
    items = []
    for entry in sorted(confirmed.values(), key=lambda e: (e["checkin"], e["nights"], e["room"])):
        checkin = date.fromisoformat(entry["checkin"])
        checkout = checkin + timedelta(days=int(entry["nights"]))
        price = entry.get("price")
        price_s = f"€{price:,}" if isinstance(price, int) else ""
        items.append(
            "<li><strong>{name}</strong>: {ci} → {co} ({n} nights) {price}"
            '<a class="book" href="{url}" target="_blank" rel="noopener">Book</a></li>'.format(
                name=htmllib.escape(entry.get("room_name") or entry["room"]),
                ci=_fmt_day(checkin),
                co=_fmt_day(checkout),
                n=entry["nights"],
                price=price_s,
                url=htmllib.escape(entry["url"]),
            )
        )
    return (
        '<section class="card ok"><h2>Bookable now ({n})</h2><ul class="windows">{items}</ul>'
        "</section>".format(n=len(items), items="".join(items))
    )


def _grid_section(grid: Grid | None) -> str:
    if grid is None:
        return '<section class="card"><p>No data yet — first poll has not completed.</p></section>'
    head = "".join(
        f"<th><span>{d.strftime('%a')}</span><br>{d.strftime('%b %d')}</th>" for d in grid.dates
    )
    ordered = [c for c in config.TARGET_ROOMS if c in grid.rooms] + [
        c for c in grid.rooms if c not in config.TARGET_ROOMS
    ]
    rows = []
    for code in ordered:
        row = grid.rooms[code]
        cells = []
        for d in grid.dates:
            price = row.nights.get(d)
            if price is None:
                cells.append(f'<td class="sold" data-room="{code}" data-date="{d.isoformat()}">✕</td>')
            else:
                cells.append(
                    f'<td class="open" data-room="{code}" data-date="{d.isoformat()}">€{price}</td>'
                )
        cls = ' class="target"' if code in config.TARGET_ROOMS else ""
        rows.append(
            f'<tr{cls}><td class="room">{htmllib.escape(row.name)}</td>{"".join(cells)}</tr>'
        )
    return (
        '<section class="card"><h2>Per-night availability, 14–28 Aug 2027</h2>'
        '<p class="legend"><span class="open" style="background:var(--open);color:var(--open-fg)">€ open</span>'
        '<span style="background:var(--sold);color:var(--sold-fg)">✕ sold out</span>'
        " Highlighted rooms are the ones being watched. A stay needs every night open "
        "<em>and</em> the hotel to accept those exact dates; the list above shows only confirmed stays.</p>"
        f'<div class="wrap"><table><thead><tr><th class="room">Room</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>'
    )


_CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
_PALETTE = ["#0b5ed7", "#d63384", "#198754", "#fd7e14", "#6f42c1", "#20c997", "#dc3545", "#6c757d"]


def _history_section(history: list[dict]) -> str:
    series = history_mod.series(history)
    if not series:
        return (
            '<section class="card" id="history"><h2>Price history</h2>'
            "<p>No history yet. A point is recorded every time a price or availability changes.</p></section>"
        )
    ordered = [c for c in config.TARGET_ROOMS if c in series] + [
        c for c in series if c not in config.TARGET_ROOMS
    ]
    datasets = []
    for i, code in enumerate(ordered):
        pts = [{"x": t, "y": price} for t, price in series[code]["points"]]
        datasets.append(
            {
                "label": series[code]["name"],
                "data": pts,
                "borderColor": _PALETTE[i % len(_PALETTE)],
                "backgroundColor": _PALETTE[i % len(_PALETTE)],
                "borderWidth": 3 if code in config.TARGET_ROOMS else 1.5,
                "pointRadius": 3,
                "stepped": True,
                "spanGaps": False,
            }
        )
    rows = []
    for code in ordered:
        pts = series[code]["points"]
        first = next((p for _, p in pts if p is not None), None)
        now = pts[-1][1]
        if first is None or now is None:
            delta = "n/a" if now is None else "new"
        else:
            diff = now - first
            delta = f"{'+' if diff > 0 else ''}{diff}"
        first_s = f"€{first}" if first is not None else "—"
        now_s = f"€{now}" if now is not None else "sold out"
        rows.append(
            f'<tr><td class="room">{htmllib.escape(series[code]["name"])}</td>'
            f"<td>{first_s}</td><td>{now_s}</td><td>{delta}</td></tr>"
        )
    first_t = history[0]["t"][:10]
    payload = json.dumps(datasets).replace("</", "<\\/")
    return f"""<section class="card" id="history"><h2>Price history</h2>
<p class="sub">Lowest open-night price per room type, EUR per night, since {first_t}. {len(history)} change(s) recorded; a point is added only when a price or availability changes.</p>
<div style="position:relative;height:340px"><canvas id="priceChart"></canvas></div>
<div class="wrap"><table><thead><tr><th class="room">Room</th><th>First seen</th><th>Now</th><th>Change</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<script src="{_CHART_JS}"></script>
<script>
(function(){{
  var datasets = {payload};
  datasets.forEach(function(d){{ d.data = d.data.map(function(p){{ return {{x: Date.parse(p.x), y: p.y}}; }}); }});
  var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var fg = dark ? '#ddd' : '#333', grid = dark ? '#333' : '#e5e5e5';
  function fmt(ms){{ return new Date(ms).toISOString().slice(0,10); }}
  if (!window.Chart) {{ document.getElementById('priceChart').outerHTML = '<p>Chart library failed to load.</p>'; return; }}
  new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{datasets: datasets}},
    options: {{
      responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: {{mode: 'nearest', intersect: false}},
      scales: {{
        x: {{type: 'linear', ticks: {{color: fg, maxTicksLimit: 8, callback: fmt}}, grid: {{color: grid}}}},
        y: {{ticks: {{color: fg, callback: function(v){{ return '€' + v; }}}}, grid: {{color: grid}}, title: {{display: true, text: 'EUR / night', color: fg}}}}
      }},
      plugins: {{
        legend: {{labels: {{color: fg}}}},
        tooltip: {{callbacks: {{title: function(items){{ return new Date(items[0].parsed.x).toUTCString().slice(0,22); }},
                               label: function(c){{ return c.dataset.label + ': €' + c.parsed.y; }}}}}}
      }}
    }}
  }});
}})();
</script>
</section>"""


def render_page(
    grid: Grid | None,
    confirmed: dict,
    checked_at: datetime | None,
    fail_count: int,
    history: list[dict] | None = None,
) -> str:
    utc, cy = _fmt_dt(checked_at)
    fail_html = ""
    if fail_count >= 1:
        fail_html = (
            f'<section class="card fail"><strong>Warning:</strong> {fail_count} consecutive '
            "failed polls. Data below may be stale.</section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Aliathon Aegean watch</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>Aliathon Aegean — August 2027 availability</h1>
<p class="sub">Last checked {utc} ({cy}). Polls every 10 minutes.
<a href="{config.BASE_URL}/" target="_blank" rel="noopener">Booking site</a> · <a href="#history">Price history</a></p>
{fail_html}
{_windows_section(confirmed)}
{_grid_section(grid)}
{_history_section(history or [])}
<footer>Source: aliathonaegean.reserve-online.net availability for 1 room, 2 adults, 2 children. Prices in EUR per night, lowest rate shown.</footer>
</main>
</body>
</html>
"""
