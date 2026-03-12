"""
Reddit hot topics scraper.

Uses old.reddit.com/r/popular for stable HTML structure (div.thing, a.title).
Falls back to new Reddit with session if old Reddit fails.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import DEFAULT_COUNTRY


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


APP_ROOT = Path(__file__).resolve().parent
SESSIONS_DIR = APP_ROOT / "sessions"
REDDIT_SESSION_PATH = SESSIONS_DIR / "reddit.json"


def _parse_score(score_text: str) -> int | None:
    if not score_text:
        return None
    score_text = score_text.strip().replace(",", "").upper()
    mult = 1
    if score_text.endswith("K"):
        mult = 1000
        score_text = score_text[:-1]
    elif score_text.endswith("M"):
        mult = 1_000_000
        score_text = score_text[:-1]
    m = re.search(r"([\d.]+)", score_text)
    if m:
        try:
            return int(float(m.group(1)) * mult)
        except (ValueError, TypeError):
            pass
    return None


def _fetch_reddit_popular_json(
    country_code: str,
    limit: int = 50,
    timeout_s: int = 20,
) -> list[dict[str, Any]]:
    """
    Fetch r/popular via Reddit's public JSON endpoint.

    This is usually more stable than HTML scraping and avoids headless browser detection.
    """
    cc = (country_code or DEFAULT_COUNTRY).strip().upper()
    # geo_filter supports many ISO-3166 alpha-2 codes and controls the country variant of /r/popular.
    # Use it for ALL countries including US to make behavior consistent with the UI filter.
    qs = urllib.parse.urlencode({"limit": int(limit), "geo_filter": cc})
    url = f"https://www.reddit.com/r/popular.json?{qs}"
    headers = {
        # Reddit requires a meaningful UA; generic/python UAs get blocked.
        "User-Agent": "FlowScrapper/1.0 (Windows; +https://example.invalid)",
        "Accept": "application/json,text/plain,*/*",
    }

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            children = ((data or {}).get("data") or {}).get("children") or []
            out: list[dict[str, Any]] = []
            for c in children:
                d = (c or {}).get("data") or {}
                title = (d.get("title") or "").strip()
                if not title:
                    continue
                subreddit = (d.get("subreddit_name_prefixed") or "").strip() or None
                score = d.get("score")
                try:
                    score = int(score) if score is not None else None
                except Exception:
                    score = None
                permalink = d.get("permalink") or ""
                post_url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else (permalink or None)
                out.append(
                    {
                        "type": subreddit or "post",
                        "name": title[:200],
                        "platform": "reddit",
                        "scraped_at": _today_iso(),
                        "country": cc,
                        "url": post_url,
                        "subreddit": subreddit,
                        "score": score,
                    }
                )
                if len(out) >= limit:
                    break
            return out
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            # simple backoff
            time.sleep(1.0 + attempt * 1.5)
            continue

    # If JSON endpoint is blocked too, fall back to browser scraping.
    return []


def scrape_reddit_today(
    country: str = DEFAULT_COUNTRY,
    headless: bool = True,
    timeout_ms: int = 30_000,
) -> list[dict[str, Any]]:
    """
    Scrape Reddit hot posts.

    Strategy:
    1. Prefer old.reddit.com/r/popular (stable HTML: div.thing, a.title).
    2. If that fails or returns nothing, try new Reddit with session.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    country_code = (country or DEFAULT_COUNTRY).strip().upper()
    old_reddit_url = "https://old.reddit.com/r/popular/"
    new_reddit_url = "https://www.reddit.com/r/popular/"

    topics: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Strategy 0: Reddit JSON endpoint (most stable)
    try:
        topics = _fetch_reddit_popular_json(
            country_code=country_code,
            limit=50,
            timeout_s=max(10, int(timeout_ms / 1000)),
        )
        if topics:
            return topics
    except Exception:
        # Never crash; just fall back to browser strategy.
        topics = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        storage_state = str(REDDIT_SESSION_PATH) if REDDIT_SESSION_PATH.exists() else None
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
            # ---- Strategy 1: old.reddit.com (stable HTML) ----
            try:
                page.goto(old_reddit_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_selector("div.thing", timeout=15_000)
                page.wait_for_timeout(1500)

                things = page.query_selector_all("div.thing")
                for post in things:
                    # Skip promoted / ads
                    if "promoted" in (post.get_attribute("class") or ""):
                        continue
                    title_el = post.query_selector("a.title")
                    if not title_el:
                        continue
                    title = (title_el.inner_text() or "").strip()
                    if not title or title in seen:
                        continue
                    seen.add(title)

                    href = title_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        href = f"https://old.reddit.com{href}"

                    subreddit_el = post.query_selector("a.subreddit")
                    subreddit = (subreddit_el.inner_text() or "").strip() if subreddit_el else ""
                    if subreddit and not subreddit.startswith("r/"):
                        subreddit = f"r/{subreddit.lstrip('/')}"

                    score_el = post.query_selector("div.score.unvoted, span.score")
                    score = None
                    if score_el:
                        score = _parse_score(score_el.inner_text() or "")

                    topics.append(
                        {
                            "type": subreddit or "post",
                            "name": title[:200],
                            "platform": "reddit",
                            "scraped_at": _today_iso(),
                            "country": country_code,
                            "url": href,
                            "subreddit": subreddit or None,
                            "score": score,
                        }
                    )
                    if len(topics) >= 50:
                        break
            except Exception:
                topics.clear()
                seen.clear()

            # ---- Strategy 2: new Reddit (if old returned nothing and we have session) ----
            if not topics and storage_state:
                try:
                    page.goto(new_reddit_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_selector("h3", timeout=15_000)
                    page.wait_for_timeout(2000)

                    posts = page.query_selector_all("div[data-testid='post-container'], article[data-testid='post-container']")
                    if not posts:
                        posts = page.query_selector_all("article")
                    for post in posts:
                        title_el = post.query_selector("h3")
                        if not title_el:
                            continue
                        title = (title_el.inner_text() or "").strip()
                        if not title or title in seen:
                            continue
                        seen.add(title)

                        subreddit_el = post.query_selector("a[data-click-id='subreddit']")
                        subreddit = (subreddit_el.inner_text() or "").strip() if subreddit_el else ""
                        if subreddit and not subreddit.startswith("r/"):
                            subreddit = f"r/{subreddit.lstrip('/')}"

                        score_el = post.query_selector(
                            "div[data-click-id='score'] span, span[aria-label*='upvote']"
                        )
                        score = None
                        if score_el:
                            raw = score_el.get_attribute("aria-label") or score_el.inner_text() or ""
                            m = re.search(r"([\d,]+)", raw)
                            if m:
                                try:
                                    score = int(m.group(1).replace(",", ""))
                                except ValueError:
                                    pass

                        link_el = post.query_selector("a[data-click-id='body'], a[data-click-id='comments']")
                        href = (link_el.get_attribute("href") or "") if link_el else ""
                        if href.startswith("/"):
                            href = f"https://www.reddit.com{href}"

                        topics.append(
                            {
                                "type": subreddit or "post",
                                "name": title[:200],
                                "platform": "reddit",
                                "scraped_at": _today_iso(),
                                "country": country_code,
                                "url": href,
                                "subreddit": subreddit or None,
                                "score": score,
                            }
                        )
                        if len(topics) >= 50:
                            break
                except Exception:
                    pass
        finally:
            browser.close()

    return topics
