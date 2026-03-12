"""
TikTok hot topics scraper for today.

Uses Apify's TikTok Trends Scraper when APIFY_TOKEN is set;
otherwise returns sample/placeholder data for testing.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import (
    APIFY_TOKEN,
    DEFAULT_COUNTRY,
    OUTPUT_DIR,
    RESULTS_PER_PAGE,
)


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_sample_topics() -> list[dict[str, Any]]:
    """Return sample hot topics when no API key is configured."""
    return [
        {
            "type": "hashtag",
            "name": "fyp",
            "rank": 1,
            "note": "Sample – set APIFY_TOKEN for real data",
        },
        {
            "type": "hashtag",
            "name": "viral",
            "rank": 2,
            "note": "Sample – set APIFY_TOKEN for real data",
        },
        {
            "type": "hashtag",
            "name": "trending",
            "rank": 3,
            "note": "Sample – set APIFY_TOKEN for real data",
        },
        {
            "type": "hashtag",
            "name": "foryou",
            "rank": 4,
            "note": "Sample – set APIFY_TOKEN for real data",
        },
        {
            "type": "hashtag",
            "name": "foryoupage",
            "rank": 5,
            "note": "Sample – set APIFY_TOKEN for real data",
        },
    ]


def fetch_via_apify(country: str = DEFAULT_COUNTRY) -> list[dict[str, Any]]:
    """
    Fetch TikTok hot topics using Apify TikTok Trends Scraper.
    Requires APIFY_TOKEN in environment or .env.
    """
    if not APIFY_TOKEN:
        return []

    from apify_client import ApifyClient

    client = ApifyClient(APIFY_TOKEN)
    run_input = {
        "resultsPerPage": RESULTS_PER_PAGE,
        "adsCountryCode": country,
        "adsSoundsCountryCode": country,
        "adsRankType": "popular",
        "adsCreatorsCountryCode": country,
        "adsSortCreatorsBy": "follower",
        "adsVideosCountryCode": country,
        "adsSortVideosBy": "vv",
    }

    run = client.actor("clockworks/tiktok-trends-scraper").call(
        run_input=run_input
    )
    dataset_id = run["defaultDatasetId"]
    items = list(client.dataset(dataset_id).iterate_items())

    # Normalize into a unified "hot topics" list (hashtags, sounds, creators, videos)
    topics: list[dict[str, Any]] = []
    rank = 0
    for item in items:
        rank += 1
        topic: dict[str, Any] = {
            "scraped_at": _today_iso(),
            "rank": rank,
            "raw": item,
            "region": country.strip().upper() if country else None,
        }
        if "hashtagName" in item:
            topic["type"] = "hashtag"
            topic["name"] = item.get("hashtagName", "")
            topic["publish_count"] = item.get("publishCount")
            topic["video_views"] = item.get("videoViews")
        elif "soundName" in item or "soundTitle" in item:
            topic["type"] = "sound"
            topic["name"] = item.get("soundName") or item.get("soundTitle", "")
            topic["author"] = item.get("authorName")
        elif "authorName" in item and "followerCount" in item:
            topic["type"] = "creator"
            topic["name"] = item.get("authorName", "")
            topic["followers"] = item.get("followerCount")
        elif "title" in item or "videoTitle" in item:
            topic["type"] = "video"
            topic["name"] = item.get("title") or item.get("videoTitle", "")
            topic["views"] = item.get("playCount") or item.get("videoViews")
            topic["likes"] = item.get("likeCount") or item.get("likes")
        else:
            topic["type"] = "unknown"
            topic["name"] = str(item.get("id", item))[:80]
        topics.append(topic)
    return topics


def fetch_via_browser(**kwargs: Any) -> list[dict[str, Any]]:
    """Delegate to browser module (mimics a user visiting the site)."""
    from scraper_browser import fetch_via_browser as _fetch
    return _fetch(**kwargs)


def scrape_today(
    country: str = DEFAULT_COUNTRY,
    method: str = "auto",
) -> list[dict[str, Any]]:
    """
    Scrape TikTok hot topics for today.

    method:
      - "auto"   : browser -> apify
      - "browser": 浏览器模拟用户访问 TikTok Creative Center
      - "apify"  : 使用 Apify API（需要 APIFY_TOKEN）
      - "sample" : 不抓取，返回空列表
    Only real scraped results are returned. If nothing can be scraped, an empty list is returned.
    """
    if method == "sample":
        return []
    if method == "apify":
        return fetch_via_apify(country=country)
    if method == "browser":
        return fetch_via_browser(country=country)
    # auto: 浏览器优先，其次 Apify
    topics = fetch_via_browser(country=country)
    if not topics and APIFY_TOKEN:
        topics = fetch_via_apify(country=country)
    return topics


def save_results(
    topics: list[dict[str, Any]],
    *,
    output_dir: Path | None = None,
    json_name: str | None = None,
    csv_name: str | None = None,
    platform: str = "tiktok",
    region: str | None = None,
) -> tuple[Path | None, Path | None]:
    """
    Save scraped topics to JSON and optionally CSV in output_dir.
    platform: prefix for default filenames (tiktok, x, instagram, facebook).
    Returns (json_path, csv_path); either can be None if not written.
    """
    out = output_dir or OUTPUT_DIR
    date_str = _today_iso()
    suffix = f"-{region}" if region else ""
    json_name = json_name or f"{platform}-hot-topics-{date_str}{suffix}.json"
    csv_name = csv_name or f"{platform}-hot-topics-{date_str}{suffix}.csv"

    payload = {
        "scraped_at": date_str,
        "count": len(topics),
        "topics": topics,
    }
    json_path = out / json_name
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    csv_path = None
    if topics:
        import csv
        csv_path = out / csv_name
        keys = set()
        for t in topics:
            keys.update(
                k for k in t
                if k != "raw" and not isinstance(t.get(k), (dict, list))
            )
        fieldnames = ["rank", "type", "name", "scraped_at"] + sorted(
            keys - {"rank", "type", "name", "scraped_at"}
        )
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for row in topics:
                w.writerow({k: row.get(k, "") for k in fieldnames})
    return json_path, csv_path
