"""Configuration for multi-platform hot topics scrapers."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Apify token (optional – all platforms use browser/mimic-user by default; use this only for API mode)
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "").strip()

#
# (RapidAPI TikTok integration removed; browser scraping is default.)

# Output directory for today's results
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Default country for trends (ISO 3166-1 alpha-2)
DEFAULT_COUNTRY = "US"

# Results per category when using Apify (TikTok)
RESULTS_PER_PAGE = 100

# Country/region codes supported for filtering (ISO 3166-1 alpha-2).
SUPPORTED_COUNTRY_CODES = frozenset({
    "US", "GB", "CA", "AU", "DE", "FR", "ES", "IT", "NL", "PL",
    "BR", "MX", "AR", "CO", "IN", "JP", "KR", "ID", "TH", "VN",
    "PH", "MY", "SG", "TW", "HK", "AE", "SA", "TR", "RU", "ZA",
})

# Region groups for one-click scraping.
REGION_GROUPS: dict[str, list[str]] = {
    # Middle East
    "ME": ["AE", "SA", "QA", "KW", "OM", "BH", "JO", "LB", "EG"],
    # Southeast Asia
    "SEA": ["SG", "MY", "ID", "TH", "VN", "PH"],
}

# X (Twitter) trending: country code -> WOEID (Where On Earth ID)
# 1 = Worldwide, 23424977 = US, 23424975 = UK, etc.
X_WOEID_BY_COUNTRY = {
    "US": 23424977, "GB": 23424975, "CA": 23424775, "AU": 23424748,
    "DE": 23424829, "FR": 23424819, "ES": 23424950, "IT": 23424853,
    "JP": 23424856, "IN": 23424848, "BR": 23424768, "MX": 23424900,
    "KR": 23424868, "ID": 23424846, "NL": 23424909, "PL": 23424923,
    "TR": 23424969, "SA": 23424938, "AE": 23424738, "ZA": 23424942,
}

# X trends (no-login) country pages on twitter-trending.com
X_TWITTER_TRENDING_SLUG_BY_COUNTRY: dict[str, str] = {
    "AE": "u-arab-emirates",
    "SA": "saudi-arabia",
    "QA": "qatar",
    "KW": "kuwait",
    "OM": "oman",
    "BH": "bahrain",
    "EG": "egypt",
    "JO": "jordan",
    "LB": "lebanon",
    "SG": "singapore",
    "MY": "malaysia",
    "ID": "indonesia",
    "TH": "thailand",
    "VN": "vietnam",
    "PH": "philippines",
    "US": "united-states",
    "GB": "united-kingdom",
}

# Default hashtags to scrape for "hot" content (Instagram, Facebook)
DEFAULT_TRENDING_HASHTAGS = ["viral", "trending", "explore", "fyp", "today"]

# Instagram: max posts/reels per hashtag when scraping
INSTAGRAM_RESULTS_PER_HASHTAG = 15

# Facebook: max posts per hashtag when scraping
FACEBOOK_MAX_ITEMS_PER_HASHTAG = 20
