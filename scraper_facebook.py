"""
Facebook hot topics scraper.

By default mimics a user: opens Facebook in a browser and tries to get
hashtag/trending content. Facebook often requires login; we try and return
a clear message if blocked. No API token required for browser mode.
Optional: use Apify when APIFY_TOKEN is set.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import (
    APIFY_TOKEN,
    DEFAULT_TRENDING_HASHTAGS,
    FACEBOOK_MAX_ITEMS_PER_HASHTAG,
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
    Mimic a user opening Facebook hashtag page (no API).
    If Facebook shows a login wall, returns an empty list.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    tag = (hashtag or "viral").strip().lstrip("#") or "viral"
    # Mobile search tends to expose more linkable results than hashtag pages.
    # Search for "#tag" (URL-encoded).
    url = f"https://m.facebook.com/search/top/?q=%23{tag}"
    topics: list[dict[str, Any]] = []

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
            # Wait for some post/story links to appear (or fail fast)
            selector = (
                'a[href*="story_fbid"], '
                'a[href*="/story.php"], '
                'a[href*="/permalink/"], '
                'a[href*="/posts/"], '
                'a[href*="/groups/"], '
                'a[href*="/watch/"]'
            )
            try:
                page.wait_for_selector(selector, timeout=timeout_ms)
            except Exception:
                return []
            page.wait_for_timeout(1500)
            # Try to find post links or story cards
            links = page.query_selector_all(selector)
            seen: set[str] = set()
            for link in links:
                href = link.get_attribute("href") or ""
                if not href or href in seen:
                    continue
                # Keep only links that look like actual content (not navigation/search tabs).
                if not (
                    "story_fbid" in href
                    or "/story.php" in href
                    or "/permalink/" in href
                    or "/posts/" in href
                    or "/watch/hashtag/" in href
                ):
                    continue
                seen.add(href)
                text = (link.inner_text() or "")[:200].strip() or "Post"
                topics.append({
                    "type": "post",
                    "name": text,
                    "rank": len(topics) + 1,
                    "scraped_at": _today_iso(),
                    "platform": "facebook",
                    "source": "browser",
                    "hashtag": tag,
                    "url": href,
                })
                if len(topics) >= 30:
                    break
        finally:
            browser.close()

    return topics


def fetch_via_apify(
    hashtags: list[str] | None = None,
    max_items_per_hashtag: int | None = None,
) -> list[dict[str, Any]]:
    """Use Apify Facebook Hashtag Search Scraper (requires APIFY_TOKEN)."""
    if not APIFY_TOKEN:
        return []
    from apify_client import ApifyClient
    tags = [h.strip().lstrip("#") for h in (hashtags or DEFAULT_TRENDING_HASHTAGS) if h.strip()][:5]
    if not tags:
        tags = list(DEFAULT_TRENDING_HASHTAGS)
    max_items = min(max_items_per_hashtag or FACEBOOK_MAX_ITEMS_PER_HASHTAG, 50)
    client = ApifyClient(APIFY_TOKEN)
    all_topics: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    rank = 0
    for hashtag in tags:
        run = client.actor("easyapi/facebook-hashtag-search-scraper").call(run_input={
            "searchQuery": hashtag,
            "maxItems": max_items,
        })
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            url = item.get("url") or item.get("postUrl") or item.get("link") or ""
            if url in seen_urls:
                continue
            seen_urls.add(url)
            rank += 1
            text = (item.get("text") or item.get("content") or item.get("message") or "")[:200] or "post"
            all_topics.append({
                "type": "post",
                "name": text,
                "rank": rank,
                "scraped_at": _today_iso(),
                "platform": "facebook",
                "source": "apify",
                "hashtag": hashtag,
                "url": url,
                "author": item.get("authorName") or item.get("userName"),
                "reactions": item.get("reactionsCount") or item.get("reactions"),
                "comments": item.get("commentsCount") or item.get("comments"),
                "shares": item.get("sharesCount") or item.get("shares"),
                "raw": item,
            })
        if rank >= 50:
            break
    return all_topics[:50]


def scrape_facebook_today(
    hashtags: list[str] | None = None,
    max_items_per_hashtag: int | None = None,
    use_browser: bool = True,
    session_path: Any = None,
    headless: bool = True,
) -> list[dict[str, Any]]:
    """
    Scrape Facebook hot content. By default mimics a user (browser).
    Only real scraped posts are returned. If nothing can be scraped (e.g. login wall),
    an empty list is returned unless Apify is enabled and succeeds.
    """
    if use_browser:
        first_tag = (hashtags or DEFAULT_TRENDING_HASHTAGS)[0] if (hashtags or DEFAULT_TRENDING_HASHTAGS) else "viral"
        topics = fetch_via_browser(hashtag=first_tag, headless=headless, session_path=str(session_path) if session_path else None)
        if topics:
            return topics
    if APIFY_TOKEN:
        topics = fetch_via_apify(hashtags=hashtags, max_items_per_hashtag=max_items_per_hashtag)
        if topics:
            return topics
    # No default/sample data; if nothing was scraped, return an empty list.
    return []
