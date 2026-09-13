"""Render the static status page (docs/index.html)."""
from __future__ import annotations

import html as htmllib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from watch import config
from watch import history as history_mod
from watch.parser import Grid
from watch import settings as settings_mod
from watch.settings import Settings

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
.rate-btn { margin:0 6px 6px 0; padding:4px 10px; border:1px solid var(--line); border-radius:6px;
            background:var(--card); color:var(--fg); cursor:pointer; font:inherit; }
.rate-btn.active { background:var(--accent); color:#fff; border-color:var(--accent); }
h3 { font-size:1rem; margin:16px 0 6px; }
#chart-fs { float:right; }
#chart-box { position:relative; }
.chart-wrap { position:relative; height:340px; }
#chart-box .fs-close { display:none; }
#chart-box.fs { position:fixed; inset:0; z-index:100; background:var(--card); padding:12px 12px 8px;
                display:flex; flex-direction:column; overflow:hidden; }
#chart-box.fs .chart-wrap { flex:1; min-height:0; height:auto; }
#chart-box.fs .fs-close { display:block; position:absolute; top:6px; right:10px; z-index:1; width:36px; height:36px;
                          border:1px solid var(--line); border-radius:50%; background:var(--card); color:var(--fg);
                          font:20px/1 system-ui,sans-serif; cursor:pointer; }
#chart-box.fs .rate-btns { padding-right:44px; margin-top:0; }
.gated form { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.gated input[type=password] { padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg);
                  color:var(--fg); font:inherit; min-width:180px; }
.gated input[type=number] { padding:6px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg);
                  color:var(--fg); font:inherit; width:70px; }
.gated button { padding:6px 12px; border:0; border-radius:6px; background:var(--accent); color:#fff;
                   font:inherit; font-weight:600; cursor:pointer; }
.gated button:disabled { opacity:.6; cursor:wait; }
.gated .msg { margin:8px 0 0; }
.gated .msg.err { color:#d9534f; }
.gated .msg.ok { color:#2e9e4f; }
#settings form { display:block; }
#settings fieldset { border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin:0 0 10px; }
#settings legend { padding:0 4px; color:var(--muted); }
#settings fieldset label { display:inline-block; margin:2px 14px 2px 0; }
#settings .row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:10px; }
#settings input[type=date] { padding:5px 8px; border:1px solid var(--line); border-radius:6px; background:var(--bg);
                             color:var(--fg); font:inherit; }
#settings .current { margin:0 0 12px; padding:8px 12px; background:var(--bg); border-radius:8px; }
#settings .current.pending { border-left:4px solid #fd7e14; }
#settings button.secondary { background:var(--card); color:var(--fg); border:1px solid var(--line); }
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


def _room_names(settings: Settings, grid: Grid | None) -> list[str]:
    rooms = grid.rooms if grid else {}
    return [rooms[c].name if c in rooms else c for c in settings.rooms]


def _watch_text(settings: Settings, grid: Grid | None) -> str:
    names = [htmllib.escape(n) for n in _room_names(settings, grid)]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
    nights = (
        f"{settings.min_nights} nights"
        if settings.min_nights == settings.max_nights
        else f"{settings.min_nights}–{settings.max_nights} nights"
    )
    return (
        f"Watching for {nights} in {joined}, check-in from {_fmt_day(settings.first_checkin)}, "
        f"check-out by {_fmt_day(settings.last_checkout)}."
    )


def _windows_section(confirmed: dict, settings: Settings, grid: Grid | None) -> str:
    if not confirmed:
        return (
            '<section class="card none"><h2>No bookable stays right now</h2>'
            f"<p>{_watch_text(settings, grid)}</p></section>"
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


def _date_range(dates: list[date]) -> str:
    a, b = dates[0], dates[-1]
    if (a.year, a.month) == (b.year, b.month):
        return f"{a:%d}–{b:%d %b %Y}"
    return f"{a:%d %b} – {b:%d %b %Y}"


def _grid_section(grid: Grid | None, settings: Settings) -> str:
    if grid is None:
        return '<section class="card"><p>No data yet — first poll has not completed.</p></section>'
    head = "".join(
        f"<th><span>{d.strftime('%a')}</span><br>{d.strftime('%b %d')}</th>" for d in grid.dates
    )
    ordered = [c for c in settings.rooms if c in grid.rooms] + [
        c for c in grid.rooms if c not in settings.rooms
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
        cls = ' class="target"' if code in settings.rooms else ""
        rows.append(
            f'<tr{cls}><td class="room">{htmllib.escape(row.name)}</td>{"".join(cells)}</tr>'
        )
    return (
        f'<section class="card"><h2>Per-night availability, {_date_range(grid.dates)}</h2>'
        '<p class="legend"><span class="open" style="background:var(--open);color:var(--open-fg)">€ open</span>'
        '<span style="background:var(--sold);color:var(--sold-fg)">✕ sold out</span>'
        " Highlighted rooms are the ones being watched. A stay needs every night open "
        "<em>and</em> the hotel to accept those exact dates; the list above shows only confirmed stays.</p>"
        f'<div class="wrap"><table><thead><tr><th class="room">Room</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div></section>'
    )


_CHART_JS = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"
_PALETTE = ["#0b5ed7", "#d63384", "#198754", "#fd7e14", "#6f42c1", "#20c997", "#dc3545", "#6c757d"]
_DASHES = [[], [8, 4], [2, 3], [12, 4, 2, 4]]  # per package: solid, dashed, dotted, dash-dot


def _short_rate(rate: str) -> str:
    """'Standard Rate | Breakfast' -> 'Breakfast'."""
    return rate.split("|")[-1].strip() if "|" in rate else rate


def _history_section(history: list[dict], now: datetime, settings: Settings) -> str:
    series = history_mod.series(history)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now_iso = now.isoformat()
    if not series:
        return (
            '<section class="card" id="history"><h2>Price history</h2>'
            "<p>No history yet. A point is recorded every time a price or availability changes.</p></section>"
        )
    rates = history_mod.rate_names(history)
    ordered = [c for c in settings.rooms if c in series] + [
        c for c in series if c not in settings.rooms
    ]
    datasets = []
    for i, code in enumerate(ordered):
        for rate in rates:
            pts = series[code]["rates"].get(rate)
            if not pts:
                continue
            datasets.append(
                {
                    "label": series[code]["name"],
                    "rate": rate,
                    # The price holds until the next change, so extend every series
                    # to the check time (hidden point) — one snapshot still draws a line.
                    "data": [{"x": t, "y": price} for t, price in pts]
                    + [{"x": now_iso, "y": pts[-1][1]}],
                    "borderColor": _PALETTE[i % len(_PALETTE)],
                    "backgroundColor": _PALETTE[i % len(_PALETTE)],
                    "borderWidth": 3 if code in settings.rooms else 1.5,
                    # Colour = room, line style = package.
                    "borderDash": _DASHES[rates.index(rate) % len(_DASHES)],
                    "pointRadius": [3] * len(pts) + [0],
                    "stepped": True,
                    "spanGaps": False,
                    "hidden": False,
                }
            )

    # Table: room x package. Cell = price now, change since first seen,
    # and for non-base packages the pattern (difference vs the base package).
    base = rates[0] if rates else ""
    head = "".join(
        f"<th>{htmllib.escape(_short_rate(r))}"
        + (f"<br><small>vs {htmllib.escape(_short_rate(base))}</small>" if r != base else "")
        + "</th>"
        for r in rates
    )
    rows = []
    for code in ordered:
        cells = []
        base_now = None
        for rate in rates:
            pts = series[code]["rates"].get(rate) or []
            first = next((p for _, p in pts if p is not None), None)
            now = pts[-1][1] if pts else None
            if rate == base:
                base_now = now
            if now is None:
                cell = "sold out" if pts else "—"
            else:
                cell = f"€{now}"
                if first is not None and first != now:
                    diff = now - first
                    cell += f' <small>({"+" if diff > 0 else ""}{diff} since first)</small>'
                if rate != base and base_now is not None:
                    cell += f" <small>(+{now - base_now})</small>"
            cells.append(f"<td>{cell}</td>")
        rows.append(
            f'<tr><td class="room">{htmllib.escape(series[code]["name"])}</td>{"".join(cells)}</tr>'
        )

    first_t = history[0]["t"][:10]
    buttons = '<button type="button" class="rate-btn active" data-rate="*">All</button>' + "".join(
        f'<button type="button" class="rate-btn" data-rate="{htmllib.escape(r)}">'
        f"{htmllib.escape(_short_rate(r))}</button>"
        for r in rates
    )
    payload = json.dumps(datasets).replace("</", "<\\/")
    return f"""<section class="card" id="history"><h2>Price history</h2>
<p class="sub">Lowest open-night price per room type, EUR per night, since {first_t}. {len(history)} change(s) recorded; a point is added only when a price or availability changes.</p>
<div id="chart-box">
<button type="button" class="fs-close" aria-label="Exit full screen">✕</button>
<p class="rate-btns"><button type="button" id="chart-fs">Full screen</button> Package: {buttons} <small>Colour = room, line style = package (solid, dashed, dotted).</small></p>
<div class="chart-wrap"><canvas id="priceChart"></canvas></div>
</div>
<h3>Packages now</h3>
<div class="wrap"><table><thead><tr><th class="room">Room</th>{head}</tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<script src="{_CHART_JS}"></script>
<script>
(function(){{
  var datasets = {payload};
  var xMin = Date.parse('{history[0]["t"]}'), xMax = Date.parse('{now_iso}');
  if (!(xMax > xMin)) {{ xMax = xMin + 3600000; }}
  datasets.forEach(function(d){{ d.data = d.data.map(function(p){{ return {{x: Date.parse(p.x), y: p.y}}; }}); }});
  var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var fg = dark ? '#ddd' : '#333', grid = dark ? '#333' : '#e5e5e5';
  function fmt(ms){{ return new Date(ms).toISOString().slice(0,10); }}
  if (!window.Chart) {{ document.getElementById('priceChart').outerHTML = '<p>Chart library failed to load.</p>'; return; }}
  var chart = new Chart(document.getElementById('priceChart'), {{
    type: 'line',
    data: {{datasets: datasets}},
    options: {{
      responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: {{mode: 'nearest', intersect: false}},
      scales: {{
        x: {{type: 'linear', min: xMin, max: xMax, ticks: {{color: fg, maxTicksLimit: 8, callback: fmt}}, grid: {{color: grid}}}},
        y: {{ticks: {{color: fg, callback: function(v){{ return '€' + v; }}}}, grid: {{color: grid}}, title: {{display: true, text: 'EUR / night', color: fg}}}}
      }},
      plugins: {{
        legend: {{labels: {{color: fg, filter: function(item, data){{ return !data.datasets[item.datasetIndex].hidden; }}}}}},
        tooltip: {{callbacks: {{title: function(items){{ return new Date(items[0].parsed.x).toUTCString().slice(0,22); }},
                               label: function(c){{ return c.dataset.label + ' (' + c.dataset.rate.split('|').pop().trim() + '): €' + c.parsed.y; }}}}}}
      }}
    }}
  }});
  document.querySelectorAll('.rate-btn').forEach(function(btn){{
    btn.addEventListener('click', function(){{
      var rate = btn.getAttribute('data-rate');
      document.querySelectorAll('.rate-btn').forEach(function(b){{ b.classList.toggle('active', b === btn); }});
      chart.data.datasets.forEach(function(d, i){{ var show = rate === '*' || d.rate === rate; chart.setDatasetVisibility(i, show); d.hidden = !show; }});
      chart.update();
    }});
  }});
  // Full screen: CSS overlay always (works on iPhone too), real Fullscreen API where available.
  var box = document.getElementById('chart-box'), fsBtn = document.getElementById('chart-fs');
  function setFs(on){{
    box.classList.toggle('fs', on);
    fsBtn.textContent = on ? 'Exit full screen' : 'Full screen';
    document.body.style.overflow = on ? 'hidden' : '';
    setTimeout(function(){{ chart.resize(); }}, 50);
  }}
  function enterFs(){{
    setFs(true);
    if (box.requestFullscreen) {{ box.requestFullscreen().catch(function(){{}}); }}
  }}
  function exitFs(){{
    if (document.fullscreenElement && document.exitFullscreen) {{ document.exitFullscreen().catch(function(){{}}); }}
    setFs(false);
  }}
  fsBtn.addEventListener('click', function(){{ box.classList.contains('fs') ? exitFs() : enterFs(); }});
  box.querySelector('.fs-close').addEventListener('click', exitFs);
  document.addEventListener('fullscreenchange', function(){{ if (!document.fullscreenElement && box.classList.contains('fs')) setFs(false); }});
  document.addEventListener('keydown', function(e){{ if (e.key === 'Escape' && box.classList.contains('fs')) exitFs(); }});
}})();
</script>
</section>"""


_DECRYPT_JS = """<script>
// Shared by the password-gated cards: PBKDF2-HMAC-SHA256 -> AES-256-GCM, mirrors watch/pagecrypt.py.
window.aliathonDecrypt = function(blob, password){
  function b64(s){ var bin = atob(s), out = new Uint8Array(bin.length); for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; }
  var enc = new TextEncoder();
  return crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey'])
    .then(function(base){ return crypto.subtle.deriveKey(
      {name: 'PBKDF2', salt: b64(blob.salt), iterations: blob.iter, hash: 'SHA-256'},
      base, {name: 'AES-GCM', length: 256}, false, ['decrypt']); })
    .then(function(key){ return crypto.subtle.decrypt({name: 'AES-GCM', iv: b64(blob.iv)}, key, b64(blob.ct)); })
    .then(function(buf){ return new TextDecoder().decode(buf); });
};
</script>
"""


def _json_payload(blob: dict) -> str:
    return json.dumps(blob).replace("</", "<\\/")


def _test_push_section(blob: dict | None) -> str:
    if not blob:
        return ""
    payload = _json_payload(blob)
    server = htmllib.escape(config.NTFY_SERVER)
    return f"""<section class="card gated" id="testpush"><h2>Test notification</h2>
<p class="sub">Sends a test push to the phone through the same ntfy topic the watcher uses. The topic is stored
here encrypted; the password decrypts it in your browser only.</p>
<form autocomplete="off">
<input type="password" id="tp-pw" placeholder="Password" autocomplete="current-password">
<label><input type="checkbox" id="tp-remember"> remember on this device</label>
<button type="submit" id="tp-send">Send test push</button>
</form>
<p class="msg" id="tp-msg"></p>
<script>
(function(){{
  var blob = {payload}, server = "{server}";
  var form = document.querySelector('#testpush form'), pw = document.getElementById('tp-pw'),
      remember = document.getElementById('tp-remember'), btn = document.getElementById('tp-send'),
      msg = document.getElementById('tp-msg'), KEY = 'aliathon-ntfy-topic';
  function say(text, cls){{ msg.textContent = text; msg.className = 'msg ' + (cls || ''); }}
  function saved(){{ try {{ return localStorage.getItem(KEY) || ''; }} catch (e) {{ return ''; }} }}
  function sendTest(topic){{
    var now = new Date();
    return fetch(server + '/' + topic, {{method: 'POST',
      headers: {{'Title': 'Aliathon test push', 'Priority': 'high', 'Tags': 'hotel,bell'}},
      body: 'Test from status page at ' + now.toISOString().slice(0, 16).replace('T', ' ') + ' UTC'}});
  }}
  if (saved()) {{ pw.placeholder = 'Password (remembered)'; remember.checked = true; }}
  if (!(window.crypto && crypto.subtle)) {{ say('This browser cannot decrypt here (needs https).', 'err'); btn.disabled = true; }}
  form.addEventListener('submit', function(ev){{
    ev.preventDefault();
    btn.disabled = true; say('Working…');
    var topicP = (!pw.value && saved()) ? Promise.resolve(saved()) : aliathonDecrypt(blob, pw.value);
    topicP.then(function(topic){{
      try {{ if (remember.checked) localStorage.setItem(KEY, topic); else localStorage.removeItem(KEY); }} catch (e) {{}}
      return sendTest(topic);
    }}).then(function(resp){{
      if (resp.ok) say('Sent. Check the phone.', 'ok'); else say('ntfy returned ' + resp.status, 'err');
    }}).catch(function(e){{
      var wrong = e && (e.name === 'OperationError' || /decrypt/i.test(String(e)));
      say(wrong ? 'Wrong password.' : 'Failed: ' + (e && e.message || e), 'err');
      if (wrong) {{ try {{ localStorage.removeItem(KEY); }} catch (x) {{}} }}
    }}).then(function(){{ btn.disabled = false; pw.value = ''; }});
  }});
}})();
</script>
</section>"""


def _fmt_short(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CYPRUS).strftime("%a %d %b %H:%M")


_ALERT_LABELS = {
    "all": "All changes",
    "improvements": "Only improvements (price down or nights opened)",
    "off": "Off",
}


def _current_line(settings: Settings, grid: Grid | None) -> str:
    names = ", ".join(htmllib.escape(n) for n in _room_names(settings, grid))
    nights = (
        f"{settings.min_nights} nights"
        if settings.min_nights == settings.max_nights
        else f"{settings.min_nights}–{settings.max_nights} nights"
    )
    pkgs = ", ".join(htmllib.escape(_short_rate(x)) for x in settings.packages) or "all packages"
    price = f"max €{settings.max_price:,}" if settings.max_price else "no price cap"
    applied = (
        f"Applied {_fmt_short(settings.updated)} Cyprus."
        if settings.updated
        else "Defaults from config, nothing saved yet."
    )
    return (
        f"<strong>Current:</strong> {names} · {nights} · "
        f"{_fmt_day(settings.first_checkin)} to {_fmt_day(settings.last_checkout)} · "
        f"{settings.adults} adults, {settings.children} children · {price} · "
        f"price alerts: {_ALERT_LABELS[settings.price_alerts].split(' (')[0].lower()}, {pkgs}. {applied}"
    )


def _settings_section(
    grid: Grid | None,
    settings: Settings,
    blob: dict | None,
    repo: str,
    known_packages: list[str],
) -> str:
    if not blob or not repo:
        return ""
    payload = _json_payload(blob)
    api = htmllib.escape(f"https://api.github.com/repos/{repo}/actions/workflows")
    rooms = dict(grid.rooms) if grid else {}
    codes = [c for c in settings.rooms if c in rooms] + [c for c in rooms if c not in settings.rooms]
    codes += [c for c in settings.rooms if c not in rooms]
    boxes = "".join(
        '<label><input type="checkbox" name="room" value="{code}"{chk}> {name}</label>'.format(
            code=htmllib.escape(code),
            chk=" checked" if code in settings.rooms else "",
            name=htmllib.escape(rooms[code].name if code in rooms else code),
        )
        for code in codes
    )
    pkg_names = list(known_packages) + [x for x in settings.packages if x not in known_packages]
    pkg_boxes = "".join(
        '<label><input type="checkbox" name="package" value="{v}"{chk}> {name}</label>'.format(
            v=htmllib.escape(x, quote=True),
            chk=" checked" if x in settings.packages else "",
            name=htmllib.escape(_short_rate(x)),
        )
        for x in pkg_names
    ) or "<em>No packages seen yet.</em>"
    radios = "".join(
        '<label><input type="radio" name="alerts" value="{v}"{chk}> {label}</label>'.format(
            v=v, chk=" checked" if settings.price_alerts == v else "", label=label
        )
        for v, label in _ALERT_LABELS.items()
    )
    max_price = settings.max_price if settings.max_price else ""
    return f"""<section class="card gated" id="settings" data-client-id="{htmllib.escape(settings.client_id)}">
<h2>Notification settings</h2>
<p class="current" id="st-current">{_current_line(settings, grid)}</p>
<p class="sub">Saving starts a GitHub workflow that stores the settings and polls once; this page reloads by itself
when the change is live (about a minute). "Poll now" restarts the watcher for an immediate check.</p>
<form autocomplete="off">
<fieldset><legend>Rooms</legend>{boxes}</fieldset>
<fieldset><legend>Stay</legend>
<div class="row"><label>Check-in from <input type="date" id="st-from" value="{settings.first_checkin.isoformat()}"></label>
<label>check-out by <input type="date" id="st-to" value="{settings.last_checkout.isoformat()}"></label></div>
<div class="row"><label>Nights: min <input type="number" id="st-min" min="1" max="{settings_mod.MAX_WINDOW_NIGHTS}" value="{settings.min_nights}"></label>
<label>max <input type="number" id="st-max" min="1" max="{settings_mod.MAX_WINDOW_NIGHTS}" value="{settings.max_nights}"></label></div>
</fieldset>
<fieldset><legend>Guests and budget</legend>
<div class="row"><label>Adults <input type="number" id="st-adults" min="1" max="{settings_mod.MAX_GUESTS}" value="{settings.adults}"></label>
<label>Children <input type="number" id="st-children" min="0" max="{settings_mod.MAX_GUESTS}" value="{settings.children}"></label>
<label>Max total price € <input type="number" id="st-price" min="1" step="1" value="{max_price}" placeholder="none"></label></div>
</fieldset>
<fieldset><legend>Price-change pushes</legend>
<div class="row">{radios}</div>
<div>Packages (none ticked = all): {pkg_boxes}</div>
</fieldset>
<div class="row">
<input type="password" id="st-pw" placeholder="Password" autocomplete="current-password">
<label><input type="checkbox" id="st-remember"> remember on this device</label>
<button type="submit" id="st-save">Save</button>
<button type="button" id="st-poll" class="secondary">Poll now</button>
</div>
</form>
<p class="msg" id="st-msg"></p>
<script>
(function(){{
  var blob = {payload}, api = "{api}", MAX_WINDOW = {settings_mod.MAX_WINDOW_NIGHTS}, MAX_GUESTS = {settings_mod.MAX_GUESTS};
  var card = document.getElementById('settings'), form = card.querySelector('form'),
      pw = document.getElementById('st-pw'), remember = document.getElementById('st-remember'),
      btn = document.getElementById('st-save'), pollBtn = document.getElementById('st-poll'),
      msg = document.getElementById('st-msg'), current = document.getElementById('st-current'),
      KEY = 'aliathon-settings-token', PENDING = 'aliathon-settings-pending';
  function $(id){{ return document.getElementById(id); }}
  function say(text, cls){{ msg.textContent = text; msg.className = 'msg ' + (cls || ''); }}
  function saved(){{ try {{ return localStorage.getItem(KEY) || ''; }} catch (e) {{ return ''; }} }}
  function store(k, v){{ try {{ if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); }} catch (e) {{}} }}
  function get(k){{ try {{ return localStorage.getItem(k); }} catch (e) {{ return null; }} }}
  function checked(name){{ return Array.prototype.map.call(form.querySelectorAll('input[name=' + name + ']:checked'), function(el){{ return el.value; }}); }}
  function num(id){{ return parseInt($(id).value, 10); }}
  function daysBetween(a, b){{ return Math.round((Date.parse(b) - Date.parse(a)) / 86400000); }}
  function payloadOrError(){{
    var rooms = checked('room'), from = $('st-from').value, to = $('st-to').value, window_ = daysBetween(from, to);
    var lo = num('st-min'), hi = num('st-max'), adults = num('st-adults'), children = num('st-children');
    var price = $('st-price').value.trim();
    if (!rooms.length) return {{error: 'Select at least one room.'}};
    if (!from || !to || !(window_ >= 1 && window_ <= MAX_WINDOW)) return {{error: 'Check-out must be 1 to ' + MAX_WINDOW + ' nights after check-in.'}};
    if (!(lo >= 1 && lo <= hi && hi <= window_)) return {{error: 'Nights must satisfy 1 \\u2264 min \\u2264 max \\u2264 ' + window_ + ' (the date window).'}};
    if (!(adults >= 1 && adults <= MAX_GUESTS && children >= 0 && children <= MAX_GUESTS)) return {{error: 'Adults 1-' + MAX_GUESTS + ', children 0-' + MAX_GUESTS + '.'}};
    if (price && !(parseInt(price, 10) >= 1)) return {{error: 'Max price must be a positive number or empty.'}};
    var id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    return {{data: {{rooms: rooms, first_checkin: from, last_checkout: to, min_nights: lo, max_nights: hi,
      adults: adults, children: children, max_price: price ? parseInt(price, 10) : null,
      packages: checked('package'), price_alerts: (checked('alerts')[0] || 'all'), client_id: id}}}};
  }}
  function dispatch(token, workflow, inputs){{
    return fetch(api + '/' + workflow + '/dispatches', {{method: 'POST',
      headers: {{'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'}},
      body: JSON.stringify({{ref: 'main', inputs: inputs}})}});
  }}
  function withToken(fn){{
    var tokenP = (!pw.value && saved()) ? Promise.resolve(saved()) : aliathonDecrypt(blob, pw.value);
    return tokenP.then(function(token){{
      store(KEY, remember.checked ? token : null);
      return fn(token);
    }}).then(function(resp){{
      if (resp.status === 204) return true;
      if (resp.status === 401) store(KEY, null);
      return resp.text().then(function(t){{ say('GitHub returned ' + resp.status + ': ' + t.slice(0, 200), 'err'); return false; }});
    }}).catch(function(e){{
      var wrong = e && (e.name === 'OperationError' || /decrypt/i.test(String(e)));
      say(wrong ? 'Wrong password.' : 'Failed: ' + (e && e.message || e), 'err');
      if (wrong) store(KEY, null);
      return false;
    }});
  }}
  function busy(on){{ btn.disabled = on; pollBtn.disabled = on; if (!on) pw.value = ''; }}
  // A save is "pending" until a page carrying its client_id is served.
  var pending = get(PENDING);
  if (pending) {{
    if (card.getAttribute('data-client-id') === pending) {{ store(PENDING, null); }}
    else {{
      current.classList.add('pending');
      current.innerHTML += ' <strong>Saved, waiting for the watcher to apply it… this page reloads every 30 s.</strong>';
      setTimeout(function(){{ location.reload(); }}, 30000);
    }}
  }}
  if (saved()) {{ pw.placeholder = 'Password (remembered)'; remember.checked = true; }}
  if (!(window.crypto && crypto.subtle)) {{ say('This browser cannot decrypt here (needs https).', 'err'); busy(true); }}
  form.addEventListener('submit', function(ev){{
    ev.preventDefault();
    var p = payloadOrError();
    if (p.error) {{ say(p.error, 'err'); return; }}
    busy(true); say('Working…');
    withToken(function(token){{ return dispatch(token, 'settings.yml', {{settings: JSON.stringify(p.data)}}); }})
      .then(function(ok){{
        if (ok) {{ store(PENDING, p.data.client_id); say('Saved. Applying takes about a minute; the page reloads by itself.', 'ok');
                  setTimeout(function(){{ location.reload(); }}, 45000); }}
        busy(false);
      }});
  }});
  pollBtn.addEventListener('click', function(){{
    busy(true); say('Working…');
    withToken(function(token){{ return dispatch(token, 'poll.yml', {{}}); }})
      .then(function(ok){{ if (ok) say('Poll started. Fresh data in about a minute.', 'ok'); busy(false); }});
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
    test_push: dict | None = None,
    settings: Settings | None = None,
    settings_card: dict | None = None,
    repo: str = "",
) -> str:
    settings = settings or settings_mod.defaults()
    utc, cy = _fmt_dt(checked_at)
    epoch = int(checked_at.timestamp() * 1000) if checked_at else 0
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
<p class="sub">Last checked <strong>{cy}</strong> <span id="ago" data-checked="{epoch}"></span><br>({utc}). Polls every 10 minutes.
<a href="{config.BASE_URL}/" target="_blank" rel="noopener">Booking site</a> · <a href="#history">Price history</a></p>
{fail_html}
{_windows_section(confirmed, settings, grid)}
{_grid_section(grid, settings)}
{_history_section(history or [], checked_at or datetime.now(timezone.utc), settings)}
{_DECRYPT_JS if (test_push or settings_card) else ""}
{_settings_section(grid, settings, settings_card, repo, history_mod.rate_names(history or []))}
{_test_push_section(test_push)}
<script>
(function(){{
  var el = document.getElementById('ago'); var t = el && Number(el.getAttribute('data-checked'));
  if (!t) return;
  function tick(){{ var m = Math.round((Date.now() - t) / 60000);
    el.textContent = m < 1 ? '(just now)' : m < 120 ? '(' + m + ' min ago)' : '(' + Math.round(m / 60) + ' h ago)';
    el.style.color = m > 30 ? '#d9534f' : ''; }}
  tick(); setInterval(tick, 30000);
}})();
</script>
<footer>Source: aliathonaegean.reserve-online.net availability for 1 room, {settings.adults} adults, {settings.children} children. Prices in EUR per night, lowest rate shown.</footer>
</main>
</body>
</html>
"""
