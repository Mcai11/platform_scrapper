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


def _log_line(msg: str) -> None:
    """Best-effort append to sessions/login-debug.log for troubleshooting."""
    try:
        # In frozen builds, __file__ points into the temp _MEI folder.
        # Always prefer a stable location next to the exe.
        base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        sessions_dir = base / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        log_path = sessions_dir / "login-debug.log"
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        # Logging must never break login flow.
        return


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

    _log_line(f"start login platform={platform}, save_path={save_path}, headless={headless}, interactive={interactive}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        _log_line(f"ImportError playwright: {e}")
        raise RuntimeError("Playwright is not installed. Run: pip install playwright") from e

    url = LOGIN_URLS[platform]
    expected = AUTH_COOKIES.get(platform, set())

    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    detected = False
    try:
        with sync_playwright() as p:
            _log_line("sync_playwright() entered")
            # Use system Microsoft Edge so we don't have to ship Chromium.
            browser = None
            launch_errors: list[str] = []
            try:
                _log_line("trying launch chromium(channel=msedge)")
                browser = p.chromium.launch(headless=headless, channel="msedge")
                _log_line("launch ok: chromium(channel=msedge)")
            except Exception as e:
                msg = f"chromium(channel=msedge): {e}"
                launch_errors.append(msg)
                _log_line(f"launch failed: {msg}")

            if browser is None:
                raise RuntimeError("Edge launch failed: " + " | ".join(launch_errors))

            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            page = context.new_page()
            try:
                _log_line(f"goto {url}")
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                _log_line("page.goto() ok")
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
                            _log_line(f"detected auth cookies: {expected & names}")
                            break
                        time.sleep(2)

                cookies = context.cookies()
                names = {c.get('name') for c in cookies}
                if expected and (expected & names):
                    detected = True
                    _log_line(f"detected auth cookies at end: {expected & names}")
            finally:
                try:
                    context.storage_state(path=str(save_path))
                    _log_line(f"storage_state saved to {save_path}")
                except Exception as e:
                    _log_line(f"storage_state error: {e}")
                browser.close()
                _log_line("browser.close() called")
    except Exception as e:
        _log_line(f"EXCEPTION in login_and_save_session: {e}")
        raise

    return detected

