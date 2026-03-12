"""
Instagram hot topics scraper.

By default mimics a user: opens Instagram in a browser and tries to get
trending/hashtag content. Instagram often requires login for Explore; we try
and return a clear message if blocked. No API token required for browser mode.
Optional: use Apify when APIFY_TOKEN is set.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from config import (
    APIFY_TOKEN,
    DEFAULT_TRENDING_HASHTAGS,
    INSTAGRAM_RESULTS_PER_HASHTAG,
)


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_via_browser(
    hashtag: str = "viral",
    headless: bool = True,
    session_path: str | None = None,
    timeout_ms: int = 20_000,
) -> list[dict[str, Any]]:
    """
    Mimic a user opening Instagram hashtag/explore page (no API).
    If Instagram shows a login wall, returns an empty list.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    tag = (hashtag or "viral").strip().lstrip("#") or "viral"
    url = f"https://www.instagram.com/explore/tags/{tag}/"
    topics: list[dict[str, Any]] = []
    seen: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            storage_state=session_path,
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            # Wait for post links to render (or fail fast)
            try:
                page.wait_for_selector('a[href*="/p/"]', timeout=timeout_ms)
            except Exception:
                return []
            page.wait_for_timeout(1500)
            # Post links: /p/SHORTCODE/
            links = page.query_selector_all('a[href*="/p/"]')
            for link in links:
                href = link.get_attribute("href") or ""
                m = re.search(r"/p/([^/?]+)", href)
                if not m:
                    continue
                shortcode = m.group(1)
                if shortcode in seen:
                    continue
                seen.add(shortcode)
                post_url = f"https://www.instagram.com/p/{shortcode}/" if not href.startswith("http") else href
                topics.append({
                    "type": "post",
                    "name": f"Post {shortcode}",
                    "rank": len(topics) + 1,
                    "scraped_at": _today_iso(),
                    "platform": "instagram",
                    "source": "browser",
                    "hashtag": tag,
                    "url": post_url,
                    "shortcode": shortcode,
                })
                if len(topics) >= 30:
                    break
        finally:
            browser.close()

    return topics


def fetch_via_apify(
    hashtags: list[str] | None = None,
    results_per_hashtag: int | None = None,
) -> list[dict[str, Any]]:
    """Use Apify Instagram Hashtag Scraper (requires APIFY_TOKEN)."""
    if not APIFY_TOKEN:
        return []
    from apify_client import ApifyClient
    tags = [h.strip().lstrip("#") for h in (hashtags or DEFAULT_TRENDING_HASHTAGS) if h.strip()][:5]
    if not tags:
        tags = list(DEFAULT_TRENDING_HASHTAGS)
    limit = min(results_per_hashtag or INSTAGRAM_RESULTS_PER_HASHTAG, 20)
    client = ApifyClient(APIFY_TOKEN)
    run = client.actor("apify/instagram-hashtag-scraper").call(run_input={
        "hashtags": tags,
        "resultsType": "posts",
        "resultsLimit": limit,
    })
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    topics: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in items:
        url = item.get("url") or item.get("link") or ""
        if url in seen_urls:
            continue
        seen_urls.add(url)
        caption = (item.get("caption") or "")[:200] or (item.get("ownerUsername") or "post")
        topics.append({
            "type": "post",
            "name": caption,
            "rank": len(topics) + 1,
            "scraped_at": _today_iso(),
            "platform": "instagram",
            "source": "apify",
            "url": url,
            "owner": item.get("ownerUsername"),
            "likes": item.get("likesCount"),
            "comments": item.get("commentsCount"),
            "hashtags": item.get("hashtags", [])[:10],
            "raw": item,
        })
    return topics[:50]


def scrape_instagram_today(
    hashtags: list[str] | None = None,
    results_per_hashtag: int | None = None,
    use_browser: bool = True,
    session_path: Any = None,
    headless: bool = True,
) -> list[dict[str, Any]]:
    """
    Scrape Instagram hot content. By default mimics a user (browser).
    Only real scraped posts are returned. If nothing can be scraped (e.g. login wall),
    an empty list is returned unless Apify is enabled and succeeds.
    """
    if use_browser:
        first_tag = (hashtags or DEFAULT_TRENDING_HASHTAGS)[0] if (hashtags or DEFAULT_TRENDING_HASHTAGS) else "viral"
        topics = fetch_via_browser(hashtag=first_tag, headless=headless, session_path=str(session_path) if session_path else None)
        if topics:
            return topics
    if APIFY_TOKEN:
        topics = fetch_via_apify(hashtags=hashtags, results_per_hashtag=results_per_hashtag)
        if topics:
            return topics
    # No default/sample data; if nothing was scraped, return an empty list.
    return []
