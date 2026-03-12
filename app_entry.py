from __future__ import annotations

import threading
import time
import webbrowser

import uvicorn


def main() -> None:
    # Import here so packaging doesn't eagerly import server on launcher start.
    from server import app  # noqa: WPS433

    port = 8013  # 固定端口
    url = f"http://127.0.0.1:{port}"

    def _open_browser() -> None:
        time.sleep(1.0)
        try:
            webbrowser.open(url, new=1, autoraise=True)
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()

