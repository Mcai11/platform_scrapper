from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def scrape_youtube_trending(
    country: str = "US",
    max_results: int = 25,
    timeout_s: int = 25,
) -> list[dict[str, Any]]:
    """
    Fetch YouTube trending videos using YouTube Data API v3.

    Endpoint:
      GET https://www.googleapis.com/youtube/v3/videos?chart=mostPopular&regionCode=US

    Requirements:
      - env var: YOUTUBE_API_KEY

    Returns [] on any failure (no sample data).
    """
    api_key = (os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        return []

    cc = (country or "US").strip().upper()
    max_results = int(max(1, min(50, max_results)))

    try:
        import requests
    except Exception:
        return []

    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": cc,
        "maxResults": max_results,
        "key": api_key,
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout_s)
        if resp.status_code != 200:
            return []
        data = resp.json() or {}
        items = data.get("items") or []
        topics: list[dict[str, Any]] = []
        for item in items:
            snippet = (item or {}).get("snippet") or {}
            stats = (item or {}).get("statistics") or {}
            vid = (item or {}).get("id") or ""
            title = (snippet.get("title") or "").strip()
            if not title:
                continue
            channel = (snippet.get("channelTitle") or "").strip() or None
            views = stats.get("viewCount")
            likes = stats.get("likeCount")
            try:
                views_i = int(views) if views is not None else None
            except Exception:
                views_i = None
            try:
                likes_i = int(likes) if likes is not None else None
            except Exception:
                likes_i = None
            url_video = f"https://www.youtube.com/watch?v={vid}" if vid else None

            topics.append(
                {
                    "type": "video",
                    "name": title[:200],
                    "platform": "youtube",
                    "scraped_at": _today_iso(),
                    "country": cc,
                    "region": cc,
                    "url": url_video,
                    "channel": channel,
                    "views": views_i,
                    "likes": likes_i,
                }
            )
            if len(topics) >= 50:
                break
        return topics
    except Exception:
        return []
