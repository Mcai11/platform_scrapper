"""
Playwright login helper (Plan B).

Opens a real browser so the user can log in, then saves storage state (cookies)
to a JSON file for later reuse by scrapers.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


LOGIN_URLS = {
    "instagram": "https://www.instagram.com/accounts/login/",
    "facebook": "https://www.facebook.com/login/",
    "tiktok": "https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en",
    "x": "https://x.com/login",
    "reddit": "https://www.reddit.com/login",
}

# Cookie names that typically indicate an authenticated session.
AUTH_COOKIES = {
    "instagram": {"sessionid"},
    "facebook": {"c_user"},
    # TikTok Creative Center 登录 cookie 名不固定，这里不强依赖，只保存 storage_state 供后续复用。
    "tiktok": set(),
    # X / Twitter 常见登录 cookie
    "x": {"auth_token"},
    # Reddit 登录 cookie（名字可能略有变化，这里做 best-effort 检测）
    "reddit": {"reddit_session"},
}


def login_and_save_session(
    *,
    platform: str,
    save_path: Path,
    headless: bool = False,
    timeout_s: int = 300,
    interactive: bool = True,
) -> bool:
    """
    Launch a browser, navigate to the platform login page, and wait until we
    detect an auth cookie (or timeout). Then write Playwright storage state.

    Returns True if an auth cookie was detected, else False (still saves state).
    """
    platform = platform.strip().lower()
    if platform not in LOGIN_URLS:
        raise ValueError(f"Unsupported platform: {platform}")

    # Prefer a bundled browsers directory (for portable builds) so end users
    # do not need a separate `playwright install` step.
    bundled = Path(__file__).resolve().parent / "ms-playwright"
    if bundled.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(bundled))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Playwright is not installed. Run: pip install playwright") from e

    url = LOGIN_URLS[platform]
    expected = AUTH_COOKIES.get(platform, set())

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    detected = False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if interactive and not headless:
                print(f"[{platform}] Browser opened for login: {url}")
                print(f"[{platform}] After you finish login, come back here and press Enter to save the session.")
                try:
                    _ = sys.stdin.readline()
                except Exception:
                    pass
            else:
                # Give user time to complete login manually.
                end = time.time() + timeout_s
                while time.time() < end:
                    cookies = context.cookies()
                    names = {c.get('name') for c in cookies}
                    if expected and (expected & names):
                        detected = True
                        break
                    time.sleep(2)

            cookies = context.cookies()
            names = {c.get('name') for c in cookies}
            if expected and (expected & names):
                detected = True
        finally:
            context.storage_state(path=str(save_path))
            browser.close()

    return detected

