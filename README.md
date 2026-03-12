# Multi-Platform Hot Topics Scraper

Scrape **today’s hot topics** from **TikTok**, **X (Twitter)**, **Instagram**, and **Facebook** and save them as JSON and CSV.

---

## No API token – mimic a user in the browser

All platforms **default to browser mode**: the script opens a real browser (Chromium), visits the same pages a user would to see hot/trending content, and extracts the data. **No login and no API key** are required for TikTok and X. Instagram and Facebook often show a login wall; the script detects that and prints a short message.

| Platform    | What you get (browser) | Login required? |
|------------|------------------------|------------------|
| **TikTok** | Trending hashtags from TikTok Creative Center | No |
| **X (Twitter)** | Trending topics from a public trends page (e.g. xtrends) | No |
| **Instagram** | Tries hashtag/explore; if blocked, shows a “login required” message | Often yes |
| **Facebook** | Tries hashtag page; if blocked, shows a “login required” message | Often yes |

**Optional:** Set `APIFY_TOKEN` in `.env` to use Apify APIs instead of (or as fallback after) the browser.

---

## Plan B (recommended for Instagram/Facebook): log in once, reuse the session

Instagram and Facebook often return `0 topics` because they hide content behind a login wall.
You can fix that by saving your login cookies once and reusing them.

1. **Login and save session (Instagram):**

```bash
python main.py --login instagram --headful --save-session sessions/instagram.json
```

2. **Login and save session (Facebook):**

```bash
python main.py --login facebook --headful --save-session sessions/facebook.json
```

3. **Reuse session when scraping:**

```bash
python main.py --platform instagram --session sessions/instagram.json
python main.py --platform facebook  --session sessions/facebook.json
```

Notes:
- The login window will stay open for up to ~5 minutes while you complete login.
- The session file is saved even if login fails (so reuse it only if scraping starts returning posts).

---

## Required info for scraping

| What you need | Required? | Notes |
|---------------|-----------|--------|
| **Nothing** | No | Default: browser mimics a user; no API token, no login. |
| **Playwright** | Yes (for browser) | Run `pip install playwright` then `playwright install chromium` once. |
| **Country** | No | `--country US` (or `GB`, `JP`, etc.) for TikTok and X. |
| **Apify token** | No | Only if you want API-based scraping instead of browser. |

---

## Setup

1. **Clone or open this project**, then create a virtual environment (recommended):

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate   # macOS/Linux
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **For “mimic user” (browser) scraping**, install a browser once:

   ```bash
   playwright install chromium
   ```

   Then run with `--method browser` (or use default `auto`). No API key needed; the script opens TikTok’s [Trend Discovery](https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en) page and extracts hot hashtags.

4. **Optional – Apify (API) scraping:**  
   Get a free [Apify](https://apify.com) account and an [API token](https://console.apify.com/account/integrations). Copy `.env.example` to `.env` and set:

   ```env
   APIFY_TOKEN=your_apify_token_here
   ```

   Then run with `--method apify` for API-based results. Without `APIFY_TOKEN`, the script uses **browser** or **sample** data.

5. （已移除）TikTok RapidAPI：当前默认使用浏览器方式抓取 TikTok Creative Center。

## Usage

- **Start local dashboard (http://localhost:8000):**

```bash
pip install -r requirements.txt
python server.py
```

- **Scrape one platform** (default: TikTok):

  ```bash
  python main.py
  python main.py --platform x
  python main.py --platform instagram
  python main.py --platform facebook
  ```

- **Scrape all platforms** and save separate files per platform:

  ```bash
  python main.py --platform all
  ```

- **Region control (Middle East / Southeast Asia)** for TikTok + X:

  ```bash
  # Middle East
  python main.py --platform tiktok --region-group ME
  python main.py --platform x     --region-group ME

  # Southeast Asia
  python main.py --platform tiktok --region-group SEA
  python main.py --platform x     --region-group SEA
  ```

  By default it scrapes up to 3 countries per group (change with `--max-countries`).

- **Filter by country/region** (TikTok and X; default `US`):

  ```bash
  python main.py --country GB
  python main.py --platform x --country JP
  ```

- **TikTok only – choose method** (default is `auto`):

  ```bash
  python main.py --method browser   # No API key; mimics user visit
  python main.py --method apify     # Uses APIFY_TOKEN
  python main.py --method sample    # Fake data only
  ```

- **Custom output directory / no save:**

  ```bash
  python main.py --output-dir ./my_results
  python main.py --no-save
  ```

Output files (under `output/` by default):

- `tiktok-hot-topics-YYYY-MM-DD.json` / `.csv`
- `x-hot-topics-YYYY-MM-DD.json` / `.csv`
- `instagram-hot-topics-YYYY-MM-DD.json` / `.csv`
- `facebook-hot-topics-YYYY-MM-DD.json` / `.csv`

## How it works (browser = mimic user, no API token)

- **TikTok:** Browser opens [Trend Discovery – Hashtags](https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en) and extracts hashtags. No login.
- **X (Twitter):** Browser opens a public trends page (e.g. xtrends.iamrohit.in) and extracts trending topic names. No login.
- **Instagram:** Browser opens `instagram.com/explore/tags/viral/`; if Instagram shows a login wall, you get a short message. No token needed.
- **Facebook:** Browser opens `facebook.com/hashtag/viral`; if Facebook shows a login wall, you get a short message. No token needed.

Optional: set `APIFY_TOKEN` to use Apify APIs as fallback (or for richer data). Saved JSON/CSV keep full Unicode; the console preview may show `?` for some characters on Windows.

## Project structure

```
Flow Scrapper/
├── main.py              # CLI (--platform tiktok | x | instagram | facebook | all)
├── scraper.py           # TikTok (Apify + browser + sample) + save_results()
├── scraper_browser.py   # TikTok browser scraper (mimics user visit)
├── scraper_x.py         # X (Twitter) trending via Apify
├── scraper_instagram.py # Instagram hashtag posts via Apify
├── scraper_facebook.py  # Facebook hashtag posts via Apify
├── config.py            # APIFY_TOKEN, country, WOEID, default hashtags
├── requirements.txt
├── .env.example
├── README.md
└── output/              # *-hot-topics-YYYY-MM-DD.json / .csv per platform
```

## License

Use for personal or educational projects. Respect each platform’s Terms of Service and applicable privacy laws when using scraped data.
