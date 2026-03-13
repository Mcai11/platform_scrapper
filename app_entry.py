from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
import webbrowser

import uvicorn


def _free_port_windows(port: int) -> None:
    """If something is already listening on `port`, kill that process (Windows)."""
    try:
        # Use shell so netstat is found when exe has minimal PATH; no encoding to use OS default
        out = subprocess.run(
            "netstat -ano",
            shell=True,
            capture_output=True,
            timeout=10,
        )
        if out.returncode != 0:
            return
        stdout = (out.stdout or b"").decode("utf-8", errors="replace")
        my_pid = os.getpid()
        # Match line like "  TCP    127.0.0.1:8013    ... LISTENING    42864"
        pattern = re.compile(rf":{port}\s+\S+\s+LISTENING\s+(\d+)")
        pids_to_kill = []
        for line in stdout.splitlines():
            m = pattern.search(line)
            if m:
                pid = int(m.group(1))
                if pid != my_pid and pid > 0:
                    pids_to_kill.append(pid)
        for pid in pids_to_kill:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                pass
        if pids_to_kill:
            time.sleep(1.0)
    except Exception:
        pass


def main() -> None:
    # Import here so packaging doesn't eagerly import server on launcher start.
    from server import app  # noqa: WPS433

    port = 8013  # 固定端口
    url = f"http://127.0.0.1:{port}"

    if sys.platform == "win32":
        _free_port_windows(port)

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

