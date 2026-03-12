"""
CLI to scrape hot topics from TikTok, X (Twitter), Reddit, YouTube, and Google Trends.

Plan B (login once, reuse session):
  - Use --login tiktok/x/reddit with --save-session to store cookies.
  - Use saved sessions automatically in browser-based scrapers where applicable.
"""
import argparse
import sys
from pathlib import Path

from config import OUTPUT_DIR
from scraper import save_results, scrape_today
from config import REGION_GROUPS


def _name_for_display(t: dict) -> str:
    s = (t.get("name") or t.get("raw", {}).get("hashtagName") or "-")[:50]
    # Avoid Windows console encoding errors with non-ASCII
    return s.encode("ascii", "replace").decode("ascii")


def run_platform(
    platform: str,
    args: argparse.Namespace,
) -> list[dict]:
    """Run the scraper for one platform; return list of topics."""
    # Expand region groups into a list of countries (only meaningful for tiktok/x).
    countries: list[str] = []
    if getattr(args, "region_group", None):
        countries = REGION_GROUPS.get(args.region_group.upper(), [])
    if not countries:
        countries = [args.country] if args.country else []
    max_countries = getattr(args, "max_countries", None) or 5
    countries = countries[: max_countries]

    if platform == "tiktok":
        all_topics: list[dict] = []
        for c in countries[:20]:
            topics = scrape_today(country=c, method=args.method)
            for t in topics:
                t.setdefault("region", c.upper())
            all_topics.extend(topics)
        # Re-rank merged list
        for i, t in enumerate(all_topics, start=1):
            t["rank"] = i
        return all_topics
    if platform == "x":
        from scraper_x import scrape_x_today
        all_topics: list[dict] = []
        for c in countries[:20]:
            topics = scrape_x_today(country=c)
            for t in topics:
                t.setdefault("region", c.upper())
            all_topics.extend(topics)
        for i, t in enumerate(all_topics, start=1):
            t["rank"] = i
        return all_topics
    if platform == "reddit":
        from scraper_reddit import scrape_reddit_today
        country = args.country or "US"
        topics = scrape_reddit_today(country=country)
        for i, t in enumerate(topics, start=1):
            t["rank"] = i
        return topics
    if platform == "google_trends":
        from scraper_google_trends import scrape_google_trends_daily

        country = args.country or "US"
        topics = scrape_google_trends_daily(country=country)
        for i, t in enumerate(topics, start=1):
            t["rank"] = i
        return topics
    if platform == "youtube":
        from scraper_youtube import scrape_youtube_trending

        country = args.country or "US"
        topics = scrape_youtube_trending(country=country, max_results=25)
        for i, t in enumerate(topics, start=1):
            t["rank"] = i
        return topics
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape hot topics from TikTok, X (Twitter), Reddit, YouTube, and Google Trends."
    )
    parser.add_argument(
        "--login",
        choices=["tiktok", "x", "reddit"],
        help="Open a real browser for login (TikTok/X/Reddit), then save session cookies (use with --save-session).",
    )
    parser.add_argument(
        "--save-session",
        type=Path,
        help="Where to write Playwright storage state (cookies) after login (e.g. sessions/ig.json).",
    )
    # Deprecated: generic --session path was only used for Facebook/Instagram, which are no longer supported.
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show the browser window (recommended for login).",
    )
    parser.add_argument(
        "--login-timeout",
        type=int,
        default=300,
        help="Seconds to wait for login in non-interactive mode (default: 300).",
    )
    parser.add_argument(
        "--non-interactive-login",
        action="store_true",
        help="Do not wait for Enter; just poll cookies until --login-timeout.",
    )
    parser.add_argument(
        "--platform",
        "-p",
        choices=["tiktok", "x", "reddit", "youtube", "google_trends", "all"],
        default="tiktok",
        help="Platform to scrape (default: tiktok). Use 'all' to run all supported platforms.",
    )
    parser.add_argument(
        "--region-group",
        choices=["ME", "SEA"],
        help="Region group (ME=Middle East, SEA=Southeast Asia). Applies to TikTok and X; expands into multiple countries and merges results.",
    )
    parser.add_argument(
        "--max-countries",
        type=int,
        default=3,
        help="When using --region-group, limit how many countries to scrape (default: 3).",
    )
    parser.add_argument(
        "--method",
        "-m",
        choices=["auto", "browser", "apify", "sample"],
        default="auto",
        help="TikTok only: auto | browser | apify | sample",
    )
    parser.add_argument(
        "--country",
        "-c",
        default="US",
        metavar="CODE",
        help="Country/region for TikTok and X (default: US). Ignored if --region-group is set.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Only print to console, do not write files",
    )
    parser.add_argument(
        "--json",
        metavar="FILE",
        help="Custom JSON output filename (single platform only)",
    )
    parser.add_argument(
        "--csv",
        metavar="FILE",
        help="Custom CSV output filename (single platform only)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Login flow (Plan B)
    if args.login:
        if not args.save_session:
            print("Error: --login requires --save-session PATH")
            return 2
        from browser_auth import login_and_save_session
        args.save_session.parent.mkdir(parents=True, exist_ok=True)
        if not args.headful and not args.non_interactive_login:
            print("Tip: add --headful for manual login (recommended).")
        ok = login_and_save_session(
            platform=args.login,
            save_path=args.save_session,
            headless=not args.headful,
            timeout_s=args.login_timeout,
            interactive=not args.non_interactive_login,
        )
        print(f"Saved session: {args.save_session}")
        if not ok:
            print("Login was NOT detected (auth cookie missing). If you completed login, try again with --headful and press Enter after login.")
        return 0 if ok else 1

    platforms = ["tiktok", "x", "reddit", "youtube", "google_trends"] if args.platform == "all" else [args.platform]

    for platform in platforms:
        print(f"\n--- {platform.upper()} ---")
        print("Fetching hot topics...")
        if args.country and args.country.upper() != "US" and platform in ("tiktok", "x"):
            print(f"Region: {args.country.upper()}")
        topics = run_platform(platform, args)
        print(f"Got {len(topics)} topics.")
        for t in topics[:25]:
            rank = t.get("rank", "?")
            typ = t.get("type", "?")
            name = _name_for_display(t)
            print(f"  {rank}. [{typ}] {name}")
        if len(topics) > 25:
            print(f"  ... and {len(topics) - 25} more")

        # Always overwrite same-day JSON; CSV is written only when topics exist.
        if not args.no_save:
            json_path, csv_path = save_results(
                topics,
                output_dir=args.output_dir,
                json_name=args.json if len(platforms) == 1 else None,
                csv_name=args.csv if len(platforms) == 1 else None,
                platform=platform,
                # 对所有平台按国家拆文件（包括 US），让 UI 的 country filter 严格匹配：
                # 没爬过的国家就没有对应文件，UI 显示为空。
                region=(args.region_group.upper() if args.region_group else (args.country or "").upper() or None),
            )
            if json_path:
                print(f"Saved: {json_path}")
            if csv_path:
                print(f"Saved: {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
