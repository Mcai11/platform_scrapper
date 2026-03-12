"""
X (Twitter) trending topics scraper.

Priority order:
- Official global trending JSON: https://x.com/i/jf/global-trending/home (requires login/session)
- Fallback: twitter-trending.com country page
- Fallback 2: xtrends.iamrohit.in worldwide page
Optional: use Apify when APIFY_TOKEN is set.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from config import (
    APIFY_TOKEN,
    DEFAULT_COUNTRY,
    X_TWITTER_TRENDING_SLUG_BY_COUNTRY,
    X_WOEID_BY_COUNTRY,
)

# Base paths for sessions (Plan B login reuse)
APP_ROOT = Path(__file__).resolve().parent
SESSIONS_DIR = APP_ROOT / "sessions"
X_SESSION_PATH = SESSIONS_DIR / "x.json"


# Public X/Twitter trends page (no login) – worldwide; supports /united-states etc.
X_TRENDS_BASE = "https://xtrends.iamrohit.in/"
# Alternative: twitter-trending.com worldwide
X_TRENDS_ALT = "https://www.twitter-trending.com/worldwide/en"
X_TRENDS_ALT_BASE = "https://www.twitter-trending.com"


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_via_browser(
    country: str = DEFAULT_COUNTRY,
    headless: bool = True,
    timeout_ms: int = 25_000,
) -> list[dict[str, Any]]:
    """
    Mimic a user visiting X/Twitter trends.

    - If an X session file exists (sessions/x.json, created via login helper),
      we first try to call the official global trending JSON endpoint:
        https://x.com/i/jf/global-trending/home
    - If that fails or no session exists, we fall back to public helper sites
      (twitter-trending.com / xtrends.iamrohit.in) without login.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    topics: list[dict[str, Any]] = []
    seen: set[str] = set()

    country_code = (country or DEFAULT_COUNTRY).strip().upper()
    slug = X_TWITTER_TRENDING_SLUG_BY_COUNTRY.get(country_code)
    country_url = f"{X_TRENDS_ALT_BASE}/{slug}/en" if slug else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # If there is a saved X session, reuse it so we look more like a real user.
        storage_state = str(X_SESSION_PATH) if X_SESSION_PATH.exists() else None
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            storage_state=storage_state,
        )
        page = context.new_page()
        try:
            # 1) If we have a logged-in X session, try the official global trending JSON endpoint first.
            if storage_state:
                try:
                    import json

                    page.goto(
                        "https://x.com/i/jf/global-trending/home",
                        wait_until="networkidle",
                        timeout=timeout_ms,
                    )
                    body_text = page.text_content("body") or ""
                    data = json.loads(body_text)

                    def _walk(obj: Any) -> None:
                        if isinstance(obj, dict):
                            # Heuristic: entries that look like a trend
                            name = obj.get("name") or obj.get("trendName") or obj.get("searchTerm")
                            if isinstance(name, str):
                                clean = name.strip()
                                if clean and clean not in seen:
                                    seen.add(clean)
                                    search_url = "https://x.com/search?q=" + quote(clean)
                                    topics.append(
                                        {
                                            "type": "trend",
                                            "name": clean[:200],
                                            "rank": len(topics) + 1,
                                            "scraped_at": _today_iso(),
                                            "platform": "x",
                                            "source": "x-global-trending",
                                            "url": search_url,
                                            "region": country_code,
                                        }
                                    )
                                    if len(topics) >= 50:
                                        return
                            for v in obj.values():
                                if len(topics) >= 50:
                                    return
                                _walk(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                if len(topics) >= 50:
                                    return
                                _walk(item)

                    _walk(data)
                    if topics:
                        return topics
                except Exception:
                    # If official JSON fails (e.g. anti-bot), fall through to public helpers.
                    topics.clear()
                    seen.clear()

            # Prefer country-specific twitter-trending.com pages when available (better region control).
            if country_url:
                for _attempt in (1, 2):
                    try:
                        page.goto(country_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
                        page.wait_for_selector('a[href*="/redirect?s="]', timeout=min(timeout_ms, 12_000))
                        page.wait_for_timeout(600)
                        anchors = page.query_selector_all('a[href*="/redirect?s="]')
                        for a in anchors:
                            href = a.get_attribute("href") or ""
                            if "s=" not in href:
                                continue
                            try:
                                name = unquote(href.split("s=", 1)[1].split("&", 1)[0].replace("+", " "))
                            except Exception:
                                continue
                            name = (name or "").strip()
                            if not name or name in seen:
                                continue
                            seen.add(name)
                            topics.append({
                                "type": "trend",
                                "name": name[:200],
                                "rank": len(topics) + 1,
                                "scraped_at": _today_iso(),
                                "platform": "x",
                                "source": "browser",
                                "url": href,
                                "region": country_code,
                            })
                            if len(topics) >= 50:
                                break
                        if topics:
                            return topics
                    except Exception:
                        continue

            page.goto(X_TRENDS_BASE, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(3000)
            # xtrends: links like <a href="https://twitter.com/search?q=...">Trend Name</a>
            links = page.query_selector_all('a[href*="twitter.com/search"]')
            for link in links:
                name = (link.inner_text() or "").strip()
                if not name or name in seen or len(name) < 2:
                    continue
                if "tweet" in name.lower() or "under" in name.lower():
                    continue
                seen.add(name)
                href = link.get_attribute("href") or ""
                topics.append({
                    "type": "trend",
                    "name": name[:200],
                    "rank": len(topics) + 1,
                    "scraped_at": _today_iso(),
                    "platform": "x",
                    "source": "browser",
                    "url": href,
                    "region": country_code or None,
                })
                if len(topics) >= 50:
                    break
            # Fallback: try twitter-trending.com for "Day" trends
            if len(topics) < 5:
                page.goto(X_TRENDS_ALT, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2000)
                for a in page.query_selector_all('a[href*="/redirect?s="]'):
                    try:
                        href = a.get_attribute("href") or ""
                        if "s=" in href:
                            name = unquote(href.split("s=", 1)[1].split("&", 1)[0].replace("+", " "))
                            if name and name not in seen and len(name) > 1:
                                seen.add(name)
                                topics.append({
                                    "type": "trend",
                                    "name": name[:200],
                                    "rank": len(topics) + 1,
                                    "scraped_at": _today_iso(),
                                    "platform": "x",
                                    "source": "browser",
                                    "url": href,
                                    "region": country_code or None,
                                })
                                if len(topics) >= 50:
                                    break
                    except Exception:
                        continue
        finally:
            browser.close()

    return topics


def fetch_via_apify(country: str = DEFAULT_COUNTRY) -> list[dict[str, Any]]:
    """Use Apify X Trending Topics Scraper (requires APIFY_TOKEN)."""
    if not APIFY_TOKEN:
        return []
    from apify_client import ApifyClient
    woeid = X_WOEID_BY_COUNTRY.get((country or DEFAULT_COUNTRY).strip().upper(), 1)
    client = ApifyClient(APIFY_TOKEN)
    run = client.actor("consummate_mandala/x-trending-topics-scraper").call(run_input={
        "urls": [{"url": "https://x.com/explore/tabs/trending"}],
        "locations": [woeid],
        "maxResults": 50,
        "useResidentialProxy": False,
    })
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    topics: list[dict[str, Any]] = []
    for i, item in enumerate(items, start=1):
        name = (item.get("trendName") or item.get("name") or str(item.get("url", "")))[:200]
        topics.append({
            "type": "trend",
            "name": name,
            "rank": i,
            "scraped_at": _today_iso(),
            "platform": "x",
            "source": "apify",
            "region": (country or DEFAULT_COUNTRY).strip().upper() or None,
            "url": item.get("url"),
            "category": item.get("category"),
            "tweet_volume": item.get("tweetVolume"),
            "raw": item,
        })
    return topics


def scrape_x_today(country: str = DEFAULT_COUNTRY, use_browser: bool = True) -> list[dict[str, Any]]:
    """
    Scrape X (Twitter) trending topics for today.
    By default mimics a user (browser, no login). Set use_browser=False and APIFY_TOKEN to use Apify.
    """
    if use_browser:
        topics = fetch_via_browser(country=country)
        if topics:
            return topics
    if APIFY_TOKEN:
        topics = fetch_via_apify(country=country)
        if topics:
            return topics
    # No default/sample data; if nothing was scraped, return an empty list.
    return []
