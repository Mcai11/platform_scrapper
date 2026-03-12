"""
Browser-based TikTok hot topics scraper.

Mimics a user opening TikTok's Trend Discovery page in a real browser,
then extracts trending hashtags from the page. No API key required.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from config import DEFAULT_COUNTRY, SUPPORTED_COUNTRY_CODES

# TikTok Creative Center – trending hashtags (public page). Region via query.
TREND_HASHTAG_BASE = "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en"

SESSIONS_DIR = Path(__file__).resolve().parent / "sessions"
TIKTOK_SESSION_PATH = SESSIONS_DIR / "tiktok.json"

# Map country code to label shown in the region dropdown (for browser selection)
COUNTRY_DROPDOWN_LABELS: dict[str, str] = {
    "US": "United States", "GB": "United Kingdom", "CA": "Canada",
    "AU": "Australia", "DE": "Germany", "FR": "France", "ES": "Spain",
    "IT": "Italy", "NL": "Netherlands", "PL": "Poland", "BR": "Brazil",
    "MX": "Mexico", "AR": "Argentina", "CO": "Colombia", "IN": "India",
    "JP": "Japan", "KR": "South Korea", "ID": "Indonesia", "TH": "Thailand",
    "VN": "Vietnam", "PH": "Philippines", "MY": "Malaysia", "SG": "Singapore",
    "TW": "Taiwan", "HK": "Hong Kong", "AE": "United Arab Emirates",
    "SA": "Saudi Arabia", "TR": "Turkey", "RU": "Russia", "ZA": "South Africa",
}

# Links to a specific hashtag's analytics (not the main "Hashtags" nav link)
HASHTAG_LINK_SELECTOR = 'a[href*="/creativecenter/hashtag/"]'
# Match /hashtag/NAME in path (optional query string)
HASHTAG_PATH_RE = re.compile(r"/hashtag/([^/?]+)", re.I)


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_hashtag_url(country: str) -> str:
    """Build Trend Discovery URL with optional region filter."""
    code = (country or DEFAULT_COUNTRY).strip().upper()
    if code and code in SUPPORTED_COUNTRY_CODES:
        return f"{TREND_HASHTAG_BASE}?region={code}"
    return TREND_HASHTAG_BASE


def _select_region_in_browser(page: Any, country: str, timeout_ms: int) -> bool:
    """Try to open the region dropdown and select the given country. Returns True if done."""
    code = (country or "").strip().upper()
    if not code or code not in COUNTRY_DROPDOWN_LABELS:
        return False
    label = COUNTRY_DROPDOWN_LABELS[code]
    try:
        # Open region dropdown (common patterns: "All regions", "Region", or a div with region selector)
        dropdown = page.get_by_text("All regions", exact=False).first
        dropdown.click(timeout=min(5000, timeout_ms))
        page.wait_for_timeout(800)
        # Click the option that matches our country label
        option = page.get_by_text(label, exact=True).first
        option.click(timeout=min(5000, timeout_ms))
        page.wait_for_timeout(2000)  # Let the table reload for the new region
        return True
    except Exception:
        return False


def fetch_via_browser(
    *,
    country: str = DEFAULT_COUNTRY,
    headless: bool = True,
    timeout_ms: int = 30_000,
) -> list[dict[str, Any]]:
    """
    Open TikTok's Trend Discovery page in a browser (mimics a user visit)
    and extract trending hashtags from the loaded page.

    country: ISO 3166-1 alpha-2 code (e.g. US, GB, DE). Applied via URL and dropdown.
    No API key required. Requires Playwright and Chromium:
      pip install playwright
      playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    seen: set[str] = set()
    topics: list[dict[str, Any]] = []
    url = _build_hashtag_url(country)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        # 如果存在 TikTok 登录会话，则复用 storage_state（Plan B 登录）。
        storage_state = str(TIKTOK_SESSION_PATH) if TIKTOK_SESSION_PATH.exists() else None
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            storage_state=storage_state,
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Optionally select region from dropdown (in case URL param isn’t enough)
            _select_region_in_browser(page, country, timeout_ms)
            # Wait for "See analytics" links (per-hashtag links), not the nav "Hashtags" link
            page.wait_for_selector(HASHTAG_LINK_SELECTOR, timeout=timeout_ms)
            # Short wait for any dynamic content
            page.wait_for_timeout(2000)

            # Collect all links to a specific hashtag's analytics page
            links = page.query_selector_all(HASHTAG_LINK_SELECTOR)
            for link in links:
                href = link.get_attribute("href") or ""
                parsed = urlparse(href)
                path = parsed.path or ""
                m = HASHTAG_PATH_RE.search(path)
                if not m:
                    continue
                name = unquote(m.group(1)).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                topics.append({
                    "type": "hashtag",
                    "name": name,
                    "rank": len(topics) + 1,
                    "scraped_at": _today_iso(),
                    "source": "browser",
                    "region": (country or DEFAULT_COUNTRY).strip().upper() or None,
                    "url": f"https://ads.tiktok.com{path}" if path.startswith("/") else href,
                })
        finally:
            browser.close()

    return topics
