from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn


def _pick_port(preferred: list[int]) -> int:
    for port in preferred:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    # fall back to ephemeral
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> None:
    # Import here so packaging doesn't eagerly import server on launcher start.
    from server import app  # noqa: WPS433

    port = _pick_port([8013, 8012, 8011, 8010, 8020])
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

