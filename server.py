"""
Local results dashboard (port 8000).

Serves a simple HTML page that lists the latest scraped results in output/,
plus JSON endpoints for programmatic access.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse


APP_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = APP_ROOT / "output"
SESSIONS_DIR = APP_ROOT / "sessions"
TIKTOK_SESSION_PATH = SESSIONS_DIR / "tiktok.json"
X_SESSION_PATH = SESSIONS_DIR / "x.json"
REDDIT_SESSION_PATH = SESSIONS_DIR / "reddit.json"

PLATFORMS = ("tiktok", "x", "reddit", "youtube", "google_trends")
PLATFORM_META: dict[str, dict[str, str]] = {
    "tiktok": {"label": "TikTok", "accent": "#ff4fd8", "glyph": "♪"},
    "x": {"label": "X Trends", "accent": "#9a7bff", "glyph": "X"},
    "reddit": {"label": "Reddit Hot", "accent": "#ff6b3d", "glyph": "R"},
    "youtube": {"label": "YouTube Trending", "accent": "#ff2d2d", "glyph": "▶"},
    "google_trends": {"label": "Google Trends", "accent": "#34a853", "glyph": "G"},
}

# 显示用的国家名称映射（代码 -> 完整名称，仅单一国家，不含区域组）
COUNTRY_LABELS: dict[str, str] = {
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "JP": "Japan",
    "IN": "India",
    "BR": "Brazil",
    # 中东
    "AE": "United Arab Emirates",
    "SA": "Saudi Arabia",
    "QA": "Qatar",
    "KW": "Kuwait",
    "OM": "Oman",
    "BH": "Bahrain",
    "EG": "Egypt",
    "IR": "Iran",
    "IQ": "Iraq",
    # 东南亚
    "SG": "Singapore",
    "MY": "Malaysia",
    "ID": "Indonesia",
    "TH": "Thailand",
    "VN": "Vietnam",
    "PH": "Philippines",
}


def _latest_json_for(platform: str) -> Path | None:
    files = sorted(OUTPUT_DIR.glob(f"{platform}-hot-topics-*.json"))
    return files[-1] if files else None


def _json_for_date(platform: str, date_str: str, region: str | None = None) -> Path | None:
    region = (region or "").strip().upper()
    if region:
        p = OUTPUT_DIR / f"{platform}-hot-topics-{date_str}-{region}.json"
        return p if p.exists() else None
    # No region specified: fall back to non-region-specific file for that date.
    p2 = OUTPUT_DIR / f"{platform}-hot-topics-{date_str}.json"
    return p2 if p2.exists() else None


def _available_dates() -> list[str]:
    # Extract YYYY-MM-DD from filenames like platform-hot-topics-YYYY-MM-DD(-REGION).json
    dates: set[str] = set()
    for f in OUTPUT_DIR.glob("*-hot-topics-*.json"):
        stem = f.stem
        # Robust match regardless of trailing region suffix.
        import re

        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", stem)
        if m:
            dates.add(m.group(1))
    return sorted(dates)


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fmt_dt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


app = FastAPI(title="Flow Scrapper Dashboard")

# In-memory job stores (best-effort, per server process)
LOGIN_JOBS: dict[str, dict[str, Any]] = {}
SCRAPE_JOBS: dict[str, dict[str, Any]] = {}


def _env_path() -> Path:
    return APP_ROOT / ".env"


def _read_env_file() -> dict[str, str]:
    p = _env_path()
    if not p.exists():
        return {}
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _write_env_file(values: dict[str, str]) -> None:
    # Overwrite with only known keys (keep it simple, avoid leaking/merging unknown values).
    keys = ["YOUTUBE_API_KEY", "APIFY_TOKEN"]
    lines = ["# Local secrets (do NOT commit this file)"]
    for k in keys:
        v = (values.get(k) or "").strip()
        if not v:
            continue
        lines.append(f"{k}={v}")
    _env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.get("/settings", response_class=HTMLResponse)
def settings() -> str:
    existing = _read_env_file()
    yt = existing.get("YOUTUBE_API_KEY", "")
    apify = existing.get("APIFY_TOKEN", "")
    # Mask for display (don’t show full secret)
    def mask(s: str) -> str:
        s = s or ""
        if len(s) <= 6:
            return "*" * len(s)
        return s[:3] + "*" * (len(s) - 6) + s[-3:]

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Settings</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {{ margin:0; font-family:\"Plus Jakarta Sans\",system-ui,Segoe UI,Arial; background:#0b0b12; color:#e9eaf2; }}
    .wrap {{ max-width: 920px; margin: 0 auto; padding: 22px 18px 46px; }}
    .card {{ border:1px solid rgba(255,255,255,.10); border-radius: 16px; background: rgba(255,255,255,.04); padding: 16px; }}
    label {{ display:block; font-size: 12px; color: rgba(233,234,242,.70); margin: 12px 0 6px; }}
    input {{ width: 100%; padding: 10px 12px; border-radius: 12px; border:1px solid rgba(255,255,255,.14); background: rgba(0,0,0,.18); color:#fff; }}
    .row {{ display:flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }}
    .btn {{ padding: 10px 12px; border-radius: 12px; border: 0; background: #9a7bff; color:#0b0b12; font-weight: 800; cursor:pointer; }}
    .btn.secondary {{ background: rgba(255,255,255,.08); color:#e9eaf2; border:1px solid rgba(255,255,255,.14); }}
    .hint {{ margin-top: 8px; font-size: 12.5px; color: rgba(233,234,242,.62); }}
    code {{ background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); padding: 2px 6px; border-radius: 10px; color: #e9eaf2; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h2 style="margin:0 0 14px;">Settings</h2>
    <div class="card">
      <div class="hint">These keys are saved to <code>.env</code> next to the app. They are local-only and should never be committed.</div>
      <label>YouTube API key (YOUTUBE_API_KEY)</label>
      <input id="yt" placeholder="AIza..." value="{mask(yt)}"/>
      <label>Apify token (APIFY_TOKEN) (optional)</label>
      <input id="apify" placeholder="apify_api_..." value="{mask(apify)}"/>
      <div class="row">
        <button class="btn" id="save">Save</button>
        <a class="btn secondary" href="/">Back</a>
      </div>
      <div class="hint" id="msg"></div>
    </div>
  </div>
  <script>
    const msg = document.getElementById('msg');
    const yt = document.getElementById('yt');
    const apify = document.getElementById('apify');
    document.getElementById('save').addEventListener('click', async () => {{
      msg.textContent = 'Saving...';
      const res = await fetch('/api/settings', {{
        method:'POST',
        headers:{{'Content-Type':'application/json'}},
        body: JSON.stringify({{ YOUTUBE_API_KEY: yt.value, APIFY_TOKEN: apify.value }})
      }});
      const data = await res.json();
      msg.textContent = data.ok ? 'Saved. You can run scrapes now.' : ('Error: ' + (data.error || 'unknown'));
    }});
  </script>
</body>
</html>
"""


@app.post("/api/settings")
def api_settings(payload: dict[str, Any]) -> dict[str, Any]:
    # If the user pasted a masked value, we treat it as "no change".
    existing = _read_env_file()
    def normalize(key: str) -> str:
        raw = str(payload.get(key) or "").strip()
        # masked display contains '*' so ignore it
        if "*" in raw:
            return existing.get(key, "")
        return raw

    values = {
        "YOUTUBE_API_KEY": normalize("YOUTUBE_API_KEY"),
        "APIFY_TOKEN": normalize("APIFY_TOKEN"),
    }
    try:
        _write_env_file(values)
        # Apply to current process immediately
        for k, v in values.items():
            if v:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
def index(date: str | None = None, region: str | None = None, scrape_country: str | None = None) -> str:
    OUTPUT_DIR.mkdir(exist_ok=True)
    dates = _available_dates()
    selected_date = date or (dates[-1] if dates else datetime.now().strftime("%Y-%m-%d"))
    selected_region = (region or "US").upper()
    selected_scrape_country = (scrape_country or selected_region).upper()

    columns: list[str] = []
    OUTPUT_DIR.mkdir(exist_ok=True)

    for p in PLATFORMS:
        # 当指定了 region 时，优先看该国家对应的文件；
        chosen = _json_for_date(p, selected_date, selected_region)
        acc = PLATFORM_META.get(p, {}).get("accent", "#7c5cff")
        label = PLATFORM_META.get(p, {}).get("label", p.upper())
        glyph = PLATFORM_META.get(p, {}).get("glyph", p[:1].upper())
        region_label = COUNTRY_LABELS.get(selected_region, selected_region)

        items_html = ""
        if chosen:
            data = _load_json(chosen)
            topics = list(data.get("topics") or [])
            for i, t in enumerate(topics[:6], start=1):
                name = str(t.get("name") or "-")
                metric = (
                    t.get("tweet_volume")
                    or t.get("video_views")
                    or t.get("views")
                    or t.get("likes")
                    or t.get("score")
                    or ""
                )
                metric_txt = f"{metric}" if metric not in ("", None) else ""
                # Simple bar based on rank position
                pct = max(8, int(100 - (i - 1) * (100 / 6)))
                items_html += f"""
                  <div class="item" style="--acc:{acc}">
                    <div class="item-top">
                      <div class="item-title">{name}</div>
                      <div class="item-rank">#{i}</div>
                    </div>
                    <div class="item-meta">{metric_txt}</div>
                    <div class="bar"><div class="fill" style="width:{pct}%"></div></div>
                  </div>
                """
        else:
            items_html = '<div class="empty">No results yet. Run <code>python main.py --platform {}</code></div>'.format(p)

        columns.append(
            f"""
            <section class="col">
              <div class="col-head">
                <div class="icon" style="--acc:{acc}">{glyph}</div>
                <div>
                  <div class="col-title">{label}</div>
                  <div class="col-sub">{region_label} · {selected_date}</div>
                </div>
              </div>
              <div class="col-body">
                {items_html if items_html else '<div class="empty">(empty)</div>'}
              </div>
              <div class="col-foot">
                <a class="link" href="/view/{p}?date={selected_date}&region={selected_region}">View</a>
                <a class="link ghost" href="/api/latest/{p}?date={selected_date}&region={selected_region}">JSON</a>
              </div>
            </section>
            """
        )

    tt_logged_in = TIKTOK_SESSION_PATH.exists()
    tt_status = "Logged in" if tt_logged_in else "Not logged in"
    tt_status_color = "#24d18a" if tt_logged_in else "#ffb020"

    x_logged_in = X_SESSION_PATH.exists()
    x_status = "Logged in" if x_logged_in else "Not logged in"
    x_status_color = "#24d18a" if x_logged_in else "#ffb020"

    rd_logged_in = REDDIT_SESSION_PATH.exists()
    rd_status = "Logged in" if rd_logged_in else "Not logged in"
    rd_status_color = "#24d18a" if rd_logged_in else "#ffb020"

    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>LocalTrendz</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0a0a0f;
      --panel: rgba(255,255,255,.05);
      --panel2: rgba(255,255,255,.03);
      --stroke: rgba(255,255,255,.08);
      --text: #e9eaf2;
      --muted: rgba(233,234,242,.62);
      --shadow: rgba(0,0,0,.55);
    }}
    body {{
      margin: 0;
      font-family: "Plus Jakarta Sans", ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: linear-gradient(180deg, #07070c, #0b0b12 40%, #0a0a10);
      color: var(--text);
    }}
    code {{ background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.10); padding: 2px 6px; border-radius: 10px; color: var(--text); }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(12px);
      background: rgba(10,10,15,.72);
      border-bottom: 1px solid rgba(255,255,255,.06);
    }}
    .topbar-inner {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 14px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
    }}
    .brand {{
      display:flex; align-items:center; gap:10px;
      font-weight: 800;
      letter-spacing: .2px;
    }}
    .brand .mark {{
      width: 22px; height: 22px;
      border-radius: 6px;
      background: linear-gradient(135deg, #9a7bff, #ff4fd8);
      box-shadow: 0 10px 30px rgba(154,123,255,.25);
    }}
    .controls {{ display:flex; gap: 12px; align-items:center; flex-wrap: wrap; }}
    label {{ font-size: 12px; color: var(--muted); margin-right: 6px; }}
    select, input[type="date"] {{
      background: #050509;
      border: 1px solid rgba(255,255,255,.20);
      color: #ffffff;
      padding: 8px 10px;
      border-radius: 10px;
      outline: none;
      font-size: 12.5px;
    }}
    select:hover, input[type="date"]:hover {{
      background: #12121a;
      border-color: rgba(255,255,255,.35);
      color: #ffffff;
    }}
    .btn {{
      background: linear-gradient(180deg, rgba(154,123,255,.95), rgba(154,123,255,.75));
      color: #0b0b12;
      border: 0;
      padding: 8px 12px;
      border-radius: 10px;
      font-weight: 700;
      cursor: pointer;
      font-size: 12.5px;
    }}
    .btn:active {{ transform: translateY(1px); }}
    .btn.secondary {{
      background: rgba(255,255,255,.08);
      color: var(--text);
      border: 1px solid rgba(255,255,255,.14);
    }}
    .btn.secondary:hover {{ border-color: rgba(255,255,255,.25); }}
    .status {{
      display:inline-flex;
      align-items:center;
      gap: 8px;
      font-size: 12px;
      color: var(--muted);
      margin-left: 6px;
    }}
    .status .dot {{
      width: 8px; height: 8px; border-radius: 99px;
      background: currentColor;
      box-shadow: 0 0 0 3px color-mix(in oklab, currentColor, transparent 80%);
    }}
    .wrap {{ max-width: 1200px; margin: 0 auto; padding: 18px 18px 46px; }}
    .grid {{
      display:grid;
      grid-template-columns: repeat(4, minmax(220px, 1fr));
      gap: 16px;
    }}
    @media (max-width: 1080px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(220px, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
    .col {{
      background: linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.03));
      border: 1px solid rgba(255,255,255,.07);
      border-radius: 16px;
      padding: 14px;
      box-shadow: 0 20px 70px rgba(0,0,0,.45);
      min-height: 560px;
    }}
    .col-head {{ display:flex; gap: 10px; align-items:center; }}
    .icon {{
      width: 28px; height: 28px;
      border-radius: 9px;
      display:grid; place-items:center;
      background: color-mix(in oklab, var(--acc), black 30%);
      border: 1px solid rgba(255,255,255,.12);
      box-shadow: 0 0 0 4px color-mix(in oklab, var(--acc), transparent 82%);
      font-weight: 800;
    }}
    .col-title {{ font-weight: 800; }}
    .col-sub {{ margin-top: 2px; font-size: 12px; color: var(--muted); }}
    .col-body {{ margin-top: 12px; display:flex; flex-direction: column; gap: 10px; }}
    .item {{
      background: rgba(0,0,0,.22);
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 14px;
      padding: 10px 10px 10px;
    }}
    .item-top {{ display:flex; justify-content: space-between; gap: 10px; align-items:flex-start; }}
    .item-title {{ font-weight: 700; font-size: 13px; line-height: 1.2; max-height: 2.4em; overflow:hidden; }}
    .item-rank {{ font-size: 12px; color: var(--muted); }}
    .item-meta {{ margin-top: 6px; font-size: 12px; color: var(--muted); min-height: 1em; }}
    .bar {{ margin-top: 8px; height: 4px; background: rgba(255,255,255,.08); border-radius: 99px; overflow:hidden; }}
    .fill {{ height: 100%; background: var(--acc); border-radius: 99px; box-shadow: 0 0 22px color-mix(in oklab, var(--acc), transparent 40%); }}
    .empty {{ padding: 10px; color: var(--muted); font-size: 12.5px; }}
    .col-foot {{ margin-top: 12px; display:flex; gap: 10px; }}
    .link {{
      color: var(--text);
      text-decoration: none;
      border: 1px solid rgba(255,255,255,.10);
      padding: 7px 10px;
      border-radius: 10px;
      background: rgba(255,255,255,.04);
      font-size: 12.5px;
      font-weight: 700;
    }}
    .link.ghost {{ background: transparent; }}
    .link:hover {{ border-color: rgba(154,123,255,.50); }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <div class="brand"><span class="mark"></span> LocalTrendz</div>
      <div class="controls">
        <div><label>Date</label><input id="date" type="date" value="{selected_date}"/></div>
        <div><label>Country</label>
          <select id="scrapeRegion">
            <option value="{selected_scrape_country}" selected>{COUNTRY_LABELS.get(selected_scrape_country, selected_scrape_country)}</option>
          </select>
        </div>
        <button class="btn secondary" id="loginX">Login X</button>
        <span class="status" title="X session file: sessions/x.json" style="color:{x_status_color}"><span class="dot"></span>{x_status}</span>
        <button class="btn secondary" id="loginTt">Login TikTok</button>
        <span class="status" title="TikTok session file: sessions/tiktok.json" style="color:{tt_status_color}"><span class="dot"></span>{tt_status}</span>
        <button class="btn secondary" id="loginRd">Login Reddit</button>
        <span class="status" title="Reddit session file: sessions/reddit.json" style="color:{rd_status_color}"><span class="dot"></span>{rd_status}</span>
        <a class="btn secondary" href="/settings">Settings</a>
        <button class="btn" id="refresh">Run scrape</button>
      </div>
    </div>
  </div>
  <div class="wrap">
    <div class="controls" style="margin-bottom: 12px;">
      <div><label>Country filter</label>
        <select id="viewRegion">
          <option value="{selected_region}" selected>{COUNTRY_LABELS.get(selected_region, selected_region)}</option>
        </select>
      </div>
    </div>
    <div class="grid">
      {''.join(columns)}
    </div>
  </div>
  <script>
    const date = document.getElementById('date');
    const scrapeRegion = document.getElementById('scrapeRegion');
    const viewRegion = document.getElementById('viewRegion');
    const btn = document.getElementById('refresh');
    const loginX = document.getElementById('loginX');
    const loginTt = document.getElementById('loginTt');
    const loginRd = document.getElementById('loginRd');
    // Populate region dropdown with 常用国家
    const regions = [
      "US","GB","CA","AU","DE","FR","JP","IN","BR",
      // Middle East
      "AE","SA","QA","KW","OM","BH","EG","IR","IQ",
      // Southeast Asia
      "SG","MY","ID","TH","VN","PH"
    ];
    const countryLabels = {{
      "US": "United States",
      "GB": "United Kingdom",
      "CA": "Canada",
      "AU": "Australia",
      "DE": "Germany",
      "FR": "France",
      "JP": "Japan",
      "IN": "India",
      "BR": "Brazil",
      "AE": "United Arab Emirates",
      "SA": "Saudi Arabia",
      "QA": "Qatar",
      "KW": "Kuwait",
      "OM": "Oman",
      "BH": "Bahrain",
      "EG": "Egypt",
      "IR": "Iran",
      "IQ": "Iraq",
      "SG": "Singapore",
      "MY": "Malaysia",
      "ID": "Indonesia",
      "TH": "Thailand",
      "VN": "Vietnam",
      "PH": "Philippines",
    }};
    function populate(sel) {{
      for (const r of regions) {{
        if ([...sel.options].some(o => o.value === r)) continue;
        const opt = document.createElement('option');
        opt.value = r; opt.textContent = countryLabels[r] || r;
        sel.appendChild(opt);
      }}
    }}
    populate(scrapeRegion);
    populate(viewRegion);
    scrapeRegion.value = "{selected_scrape_country}";
    viewRegion.value = "{selected_region}";

    function goView() {{
      const params = new URLSearchParams();
      if (date.value) params.set('date', date.value);
      if (viewRegion.value) params.set('region', viewRegion.value);
      if (scrapeRegion.value) params.set('scrape_country', scrapeRegion.value);
      window.location.search = params.toString();
    }}
    date.addEventListener('change', goView);
    viewRegion.addEventListener('change', goView);
    // Keep scrape-country selection without reloading the page
    scrapeRegion.addEventListener('change', () => {{
      const params = new URLSearchParams(window.location.search);
      params.set('scrape_country', scrapeRegion.value || 'US');
      window.history.replaceState({{}}, '', window.location.pathname + '?' + params.toString());
    }});
    function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}
    async function pollLogin(jobId) {{
      const started = Date.now();
      while (Date.now() - started < 10 * 60 * 1000) {{
        try {{
          const res = await fetch('/api/login/status?job_id=' + encodeURIComponent(jobId));
          const data = await res.json();
          if (data.state === 'done') return data;
          if (data.state === 'error') return data;
        }} catch (e) {{}}
        await sleep(1500);
      }}
      return {{ state: 'timeout' }};
    }}

    loginX.addEventListener('click', async () => {{
      loginX.disabled = true;
      loginX.textContent = 'Opening...';
      try {{
        const res = await fetch('/api/login/x', {{ method: 'POST' }});
        const data = await res.json();
        const jobId = data.job_id;
        loginX.textContent = 'Waiting login...';
        await pollLogin(jobId);
      }} finally {{
        setTimeout(() => window.location.reload(), 800);
      }}
    }});
    loginTt.addEventListener('click', async () => {{
      loginTt.disabled = true;
      loginTt.textContent = 'Opening...';
      try {{
        const res = await fetch('/api/login/tiktok', {{ method: 'POST' }});
        const data = await res.json();
        const jobId = data.job_id;
        loginTt.textContent = 'Waiting login...';
        await pollLogin(jobId);
      }} finally {{
        setTimeout(() => window.location.reload(), 800);
      }}
    }});
    loginRd.addEventListener('click', async () => {{
      loginRd.disabled = true;
      loginRd.textContent = 'Opening...';
      try {{
        const res = await fetch('/api/login/reddit', {{ method: 'POST' }});
        const data = await res.json();
        const jobId = data.job_id;
        loginRd.textContent = 'Waiting login...';
        await pollLogin(jobId);
      }} finally {{
        setTimeout(() => window.location.reload(), 800);
      }}
    }});
    const statusEl = document.createElement('div');
    statusEl.id = 'scrapeStatus';
    statusEl.style.margin = '10px 0 0';
    statusEl.style.fontSize = '12px';
    statusEl.style.color = 'var(--muted)';
    document.querySelector('.wrap').insertBefore(statusEl, document.querySelector('.wrap').firstChild);

    let statusTimer = null;
    function renderStatus(jobs) {{
      if (!statusEl) return;
      const keys = Object.keys(jobs || {{}});
      if (!keys.length) {{
        statusEl.textContent = '';
        return;
      }}
      const parts = [];
      keys.forEach(k => {{
        const j = jobs[k] || {{}};
        const state = j.state || 'unknown';
        const msg = j.message || '';
        parts.push(k + ': ' + state + (msg ? (' - ' + msg) : ''));
      }});
      statusEl.textContent = 'Scrape status: ' + parts.join(' | ');
    }}

    function pollStatusOnce() {{
      fetch('/api/scrape/status')
        .then(r => r.json())
        .then(data => renderStatus(data.jobs))
        .catch(() => {{}});
    }}

    function startPollingStatus() {{
      if (statusTimer) window.clearInterval(statusTimer);
      pollStatusOnce();
      statusTimer = window.setInterval(pollStatusOnce, 3000);
    }}

    // 初始也拉一次，方便看到最近一次抓取结果
    startPollingStatus();

    btn.addEventListener('click', () => {{
      const payload = {{
        country: scrapeRegion.value || 'US',
        platforms: ['tiktok','x','reddit','youtube','google_trends']
      }};
      fetch('/api/scrape', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }}).then(() => {{
        startPollingStatus();
      }}).finally(() => {{
        // 给爬虫一点时间，然后带参数刷新
        setTimeout(goView, 8000);
      }});
    }});
  </script>
</body>
</html>
"""


@app.get("/api/platforms")
def platforms() -> dict[str, Any]:
    return {"platforms": list(PLATFORMS)}


@app.get("/api/latest/{platform}")
def api_latest(platform: str, date: str | None = None, region: str | None = None) -> JSONResponse:
    platform = platform.lower().strip()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform")
    # If date/region provided, strictly match that selection.
    if date or region:
        selected_date = date or (datetime.now().strftime("%Y-%m-%d"))
        selected_region = (region or "US").upper()
        chosen = _json_for_date(platform, selected_date, selected_region)
        if not chosen:
            return JSONResponse({"scraped_at": selected_date, "count": 0, "topics": []})
        return JSONResponse(_load_json(chosen))

    # Otherwise, fall back to latest file (legacy behavior).
    latest = _latest_json_for(platform)
    if not latest:
        return JSONResponse({"scraped_at": None, "count": 0, "topics": []})
    return JSONResponse(_load_json(latest))


def _run_scrape_in_background(country: str, platforms: list[str]) -> None:
    """Fire-and-forget 调用 main.py 进行抓取（在后台线程里顺序执行），并在内存中记录状态。"""
    import threading
    import subprocess
    import sys
    import time

    country_code = (country or "US").upper()
    plats = [p for p in platforms if p in PLATFORMS or p == "all"]

    def _worker() -> None:
        for p in plats:
            start_ts = time.time()
            SCRAPE_JOBS[p] = {
                "state": "running",
                "country": country_code,
                "started_at": start_ts,
                "finished_at": None,
                "exit_code": None,
                "message": "",
            }
            cmd = [sys.executable, "main.py", "--platform", p, "--country", country_code]
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(APP_ROOT),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                SCRAPE_JOBS[p]["exit_code"] = proc.returncode
                SCRAPE_JOBS[p]["finished_at"] = time.time()
                if proc.returncode == 0:
                    SCRAPE_JOBS[p]["state"] = "done"
                    SCRAPE_JOBS[p]["message"] = (proc.stdout or "").splitlines()[-1][:300] if proc.stdout else ""
                else:
                    SCRAPE_JOBS[p]["state"] = "error"
                    msg = proc.stderr or proc.stdout or ""
                    SCRAPE_JOBS[p]["message"] = msg.strip().splitlines()[-1][:300] if msg else "Exited with code {proc.returncode}"
            except Exception as e:
                SCRAPE_JOBS[p]["state"] = "error"
                SCRAPE_JOBS[p]["finished_at"] = time.time()
                SCRAPE_JOBS[p]["message"] = str(e)[:300]

    threading.Thread(target=_worker, daemon=True).start()


@app.post("/api/scrape")
def api_scrape(payload: dict[str, Any]) -> dict[str, Any]:
    """从 UI 触发抓取：指定国家，拉取 TikTok / X / Reddit / Google Trends 最新热点。"""
    country = str(payload.get("country") or "US").upper()
    platforms = payload.get("platforms") or ["tiktok", "x", "reddit", "youtube", "google_trends"]
    _run_scrape_in_background(country, platforms)
    return {"ok": True, "country": country, "platforms": platforms}


@app.get("/api/scrape/status")
def api_scrape_status() -> dict[str, Any]:
    """返回最近一次抓取任务的状态（内存中的 best-effort 信息）。"""
    return {"jobs": SCRAPE_JOBS}


@app.post("/api/login/tiktok")
def api_login_tiktok() -> dict[str, Any]:
    """
    Launch a real browser window for TikTok Creative Center login,
    then save session cookies to sessions/tiktok.json.
    """
    import threading
    import uuid

    job_id = uuid.uuid4().hex
    LOGIN_JOBS[job_id] = {"state": "running", "platform": "tiktok", "started_at": datetime.now().isoformat()}

    def _worker() -> None:
        try:
            from browser_auth import login_and_save_session
            SESSIONS_DIR.mkdir(exist_ok=True)
            ok = login_and_save_session(
                platform="tiktok",
                save_path=TIKTOK_SESSION_PATH,
                headless=False,
                timeout_s=600,
                interactive=False,
            )
            LOGIN_JOBS[job_id] = {"state": "done", "ok": bool(ok)}
        except Exception as e:
            LOGIN_JOBS[job_id] = {"state": "error", "error": str(e)}

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "job_id": job_id, "save_path": str(TIKTOK_SESSION_PATH)}


@app.post("/api/login/x")
def api_login_x() -> dict[str, Any]:
    """
    Launch a real browser window for X (Twitter) login,
    then save session cookies to sessions/x.json.
    """
    import threading
    import uuid

    job_id = uuid.uuid4().hex
    LOGIN_JOBS[job_id] = {"state": "running", "platform": "x", "started_at": datetime.now().isoformat()}

    def _worker() -> None:
        try:
            from browser_auth import login_and_save_session
            SESSIONS_DIR.mkdir(exist_ok=True)
            ok = login_and_save_session(
                platform="x",
                save_path=X_SESSION_PATH,
                headless=False,
                timeout_s=600,
                interactive=False,
            )
            LOGIN_JOBS[job_id] = {"state": "done", "ok": bool(ok)}
        except Exception as e:
            LOGIN_JOBS[job_id] = {"state": "error", "error": str(e)}

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "job_id": job_id, "save_path": str(X_SESSION_PATH)}


@app.post("/api/login/reddit")
def api_login_reddit() -> dict[str, Any]:
    """
    Launch a real browser window for Reddit login,
    then save session cookies to sessions/reddit.json.
    """
    import threading
    import uuid

    job_id = uuid.uuid4().hex
    LOGIN_JOBS[job_id] = {"state": "running", "platform": "reddit", "started_at": datetime.now().isoformat()}

    def _worker() -> None:
        try:
            from browser_auth import login_and_save_session
            SESSIONS_DIR.mkdir(exist_ok=True)
            ok = login_and_save_session(
                platform="reddit",
                save_path=REDDIT_SESSION_PATH,
                headless=False,
                timeout_s=600,
                interactive=False,
            )
            LOGIN_JOBS[job_id] = {"state": "done", "ok": bool(ok)}
        except Exception as e:
            LOGIN_JOBS[job_id] = {"state": "error", "error": str(e)}

    threading.Thread(target=_worker, daemon=True).start()
    return {"ok": True, "job_id": job_id, "save_path": str(REDDIT_SESSION_PATH)}


@app.get("/api/login/status")
def api_login_status(job_id: str) -> dict[str, Any]:
    return LOGIN_JOBS.get(job_id, {"state": "unknown"})


@app.get("/view/{platform}", response_class=HTMLResponse)
def view_platform(platform: str, date: str | None = None, region: str | None = None) -> str:
    platform = platform.lower().strip()
    if platform not in PLATFORMS:
        raise HTTPException(status_code=404, detail="Unknown platform")
    dates = _available_dates()
    selected_date = date or (dates[-1] if dates else datetime.now().strftime("%Y-%m-%d"))
    selected_region = (region or "US").upper()
    # 严格按 date+region 匹配文件；没爬过就为空。
    latest = _json_for_date(platform, selected_date, selected_region)
    if not latest:
        return f"<h2>No results for {platform.upper()} · {selected_region} · {selected_date}</h2>"
    data = _load_json(latest)
    topics = data.get("topics", [])
    rows = []
    for t in topics[:200]:
        name = (t.get("name") or "-")
        url = t.get("url") or ""
        typ = t.get("type") or ""
        rank = t.get("rank") or ""
        safe_url = str(url)
        if safe_url.startswith("/"):
            safe_url = "https://www.facebook.com" + safe_url if platform == "facebook" else safe_url
        rows.append(
            f"<tr><td>{rank}</td><td>{typ}</td><td class=\"name\">{name}</td><td><a class=\"link\" href=\"{safe_url}\" target=\"_blank\">open</a></td></tr>"
        )
    return f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{platform.upper()} results</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg0:#070812; --bg1:#0b0d18; --text:#eef2ff; --muted:rgba(238,242,255,.68);
      --stroke: rgba(255,255,255,.10); --panel: rgba(255,255,255,.055); --shadow: rgba(0,0,0,.48);
      --acc:{PLATFORM_META.get(platform, {}).get('accent', '#7c5cff')};
    }}
    body {{
      font-family: "IBM Plex Sans", ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:
        radial-gradient(900px 520px at 15% -10%, color-mix(in oklab, var(--acc), transparent 70%), transparent 60%),
        radial-gradient(780px 520px at 90% 0%, rgba(37,244,238,.12), transparent 55%),
        linear-gradient(180deg, var(--bg0), var(--bg1));
      color: var(--text);
      margin:0;
    }}
    .wrap {{ max-width: 1120px; margin:0 auto; padding: 22px 18px 46px; }}
    a {{ color: var(--text); text-decoration:none; }}
    code {{ background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08); padding: 2px 6px; border-radius: 8px; color: var(--text); }}
    .top {{
      border: 1px solid var(--stroke);
      border-radius: 18px;
      padding: 14px 14px 12px;
      background: linear-gradient(180deg, var(--panel), rgba(255,255,255,.03));
      box-shadow: 0 18px 50px var(--shadow);
      display:flex; justify-content: space-between; align-items:center; flex-wrap:wrap; gap: 10px;
    }}
    h2 {{ margin:0; font-family:"Fraunces", serif; font-size: 28px; line-height: 1.05; }}
    .meta {{ margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .controls {{ display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }}
    .btn {{
      border: 1px solid rgba(255,255,255,.14);
      padding: 7px 10px;
      border-radius: 12px;
      background: rgba(255,255,255,.06);
      font-size: 12.5px;
      font-weight: 600;
    }}
    .btn:hover {{ border-color: color-mix(in oklab, var(--acc), white 25%); box-shadow: 0 0 0 3px color-mix(in oklab, var(--acc), transparent 84%); }}
    .search {{
      min-width: 240px;
      padding: 8px 10px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,.14);
      background: rgba(0,0,0,.14);
      color: var(--text);
      outline: none;
    }}
    .search:focus {{ border-color: color-mix(in oklab, var(--acc), white 20%); box-shadow: 0 0 0 3px color-mix(in oklab, var(--acc), transparent 84%); }}
    table {{ width:100%; border-collapse: collapse; margin-top: 14px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,.08); padding: 10px 8px; text-align:left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight:600; position: sticky; top: 0; background: rgba(11,13,24,.92); backdrop-filter: blur(10px); }}
    tr:hover td {{ background: rgba(255,255,255,.03); }}
    .name {{ max-width: 560px; overflow:hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .link {{ color: var(--text); border: 1px solid rgba(255,255,255,.14); padding: 6px 9px; border-radius: 12px; background: rgba(255,255,255,.05); display:inline-block; }}
    .link:hover {{ border-color: color-mix(in oklab, var(--acc), white 25%); }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="top">
      <div>
        <h2>{PLATFORM_META.get(platform, {}).get('label', platform.upper())} hot topics</h2>
        <div class="meta">{COUNTRY_LABELS.get(selected_region, selected_region)} · {selected_date} · file <code>{latest.name}</code> · count <code>{len(topics)}</code></div>
      </div>
      <div class="controls">
        <input id="q" class="search" placeholder="Filter by name/type..." />
        <input id="date" type="date" class="btn" style="min-width: 0; padding: 6px 8px;" value="{selected_date}"/>
        <select id="region" class="btn" style="min-width: 0; padding: 6px 8px;">
          <option value="{selected_region}" selected>{COUNTRY_LABELS.get(selected_region, selected_region)}</option>
        </select>
        <a class="btn" href="/">Back</a>
        <a class="btn" href="/api/latest/{platform}?date={selected_date}&region={selected_region}">JSON</a>
      </div>
    </div>
    <table>
      <thead><tr><th>Rank</th><th>Type</th><th>Name</th><th>URL</th></tr></thead>
      <tbody>
        {''.join(rows) if rows else '<tr><td colspan=\"4\">No topics</td></tr>'}
      </tbody>
    </table>
  </div>
  <script>
    const q = document.getElementById('q');
    const rows = Array.from(document.querySelectorAll('tbody tr'));
    function apply() {{
      const needle = (q.value || '').toLowerCase().trim();
      for (const r of rows) {{
        if (!needle) {{ r.style.display = ''; continue; }}
        const txt = r.innerText.toLowerCase();
        r.style.display = txt.includes(needle) ? '' : 'none';
      }}
    }}
    q.addEventListener('input', apply);

    // Date + region filter for history navigation
    const dateEl = document.getElementById('date');
    const regionEl = document.getElementById('region');
    const regions = [
      "US","GB","CA","AU","DE","FR","JP","IN","BR",
      "AE","SA","QA","KW","OM","BH","EG","IR","IQ",
      "SG","MY","ID","TH","VN","PH"
    ];
    const countryLabels = {{
      "US": "United States",
      "GB": "United Kingdom",
      "CA": "Canada",
      "AU": "Australia",
      "DE": "Germany",
      "FR": "France",
      "JP": "Japan",
      "IN": "India",
      "BR": "Brazil",
      "AE": "United Arab Emirates",
      "SA": "Saudi Arabia",
      "QA": "Qatar",
      "KW": "Kuwait",
      "OM": "Oman",
      "BH": "Bahrain",
      "EG": "Egypt",
      "IR": "Iran",
      "IQ": "Iraq",
      "SG": "Singapore",
      "MY": "Malaysia",
      "ID": "Indonesia",
      "TH": "Thailand",
      "VN": "Vietnam",
      "PH": "Philippines",
    }};
    for (const r of regions) {{
      if ([...regionEl.options].some(o => o.value === r)) continue;
      const opt = document.createElement('option');
      opt.value = r;
      opt.textContent = countryLabels[r] || r;
      regionEl.appendChild(opt);
    }}
    regionEl.value = "{selected_region}";
    function go() {{
      const params = new URLSearchParams();
      if (dateEl.value) params.set('date', dateEl.value);
      if (regionEl.value) params.set('region', regionEl.value);
      window.location.search = params.toString();
    }}
    dateEl.addEventListener('change', go);
    regionEl.addEventListener('change', go);
  </script>
</body>
</html>
"""

