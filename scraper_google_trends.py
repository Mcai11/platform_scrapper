"""
Google Trends daily/trending searches scraper.

Uses https://trends.google.com/trending?geo=<COUNTRY> (daily URL may redirect here).
Trend items are rendered as buttons; we collect button labels and filter out UI chrome.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from config import DEFAULT_COUNTRY


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# UI button labels to exclude when collecting trend names
_GOOGLE_TRENDS_SKIP = frozenset({
    "main menu", "trends", "home", "explore", "trending now", "google apps",
    "sign in", "export", "search trends", "relevance", "more info",
    "select row", "select location", "select period", "select category",
    "select trend status", "select sort criteria", "search volume", "started",
    "all categories", "all trends", "rss feed", "copy to clipboard", "download csv",
    "united states", "past 24 hours", "by relevance",
    "location_on", "calendar_month", "category", "grid_3x3", "sort",
    "arrow_back_ios_new", "arrow_forward_ios", "ios_share", "search", "info",
})


def _is_ui_label(text: str) -> bool:
    if not text or len(text) > 120:
        return True
    lower = text.lower().strip()
    if lower in _GOOGLE_TRENDS_SKIP:
        return True
    for skip in _GOOGLE_TRENDS_SKIP:
        if skip in lower and len(lower) < 80:
            return True
    if lower.startswith("see ") and "additional" in lower:
        return True
    if re.match(r"^\+\s*\d+\s*more$", lower):
        return True
    if re.match(r"^(past \d+ (hours?|days?)|(\d+ (hour|day)s? ago))$", lower):
        return True
    if "select" in lower and ("location" in lower or "period" in lower or "category" in lower or "trend" in lower or "sort" in lower):
        return True
    # Icon/material names (single token with underscores)
    if re.match(r"^[a-z0-9_]+$", lower) and "_" in lower and len(lower) < 25:
        return True
    return False


def scrape_google_trends_daily(
    country: str = DEFAULT_COUNTRY,
    headless: bool = True,
    timeout_ms: int = 35_000,
) -> list[dict[str, Any]]:
    """
    Scrape Google Trends trending searches for a country.

    Uses https://trends.google.com/trending?geo=<COUNTRY> (or daily URL which redirects).
    Collects trend names from button elements and filters out UI labels.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    country_code = (country or DEFAULT_COUNTRY).strip().upper()
    # Daily URL may redirect to /trending; use trending directly for stability
    url = f"https://trends.google.com/trending?geo={country_code}&hl=en-US"

    topics: list[dict[str, Any]] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Wait for trend content (buttons with trend names)
            page.wait_for_timeout(5000)

            # Collect all buttons and filter to trend-like names
            buttons = page.query_selector_all("button, [role='button']")
            for el in buttons:
                if len(topics) >= 50:
                    break
                text = (el.inner_text() or "").strip()
                if _is_ui_label(text):
                    continue
                # Normalize and dedupe
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                topics.append(
                    {
                        "type": "search",
                        "name": text[:200],
                        "platform": "google_trends",
                        "scraped_at": _today_iso(),
                        "country": country_code,
                        "url": None,
                        "searches_text": None,
                    }
                )
        finally:
            browser.close()

    return topics
