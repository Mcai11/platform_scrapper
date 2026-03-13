from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO = "Mcai11/platform_scrapper"
GITHUB_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"

# Expected asset name (zip contains the app exe + resources).
ASSET_ZIP_PREFIX = "platform_scrapper-"
ASSET_ZIP_SUFFIX = ".zip"


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int | None = None


def _app_dir() -> Path:
    # Portable: app folder is relative to launcher location
    return Path(sys.executable).resolve().parent / "app"


def _version_file(app_dir: Path) -> Path:
    return app_dir / "version.json"


def _read_local_version(app_dir: Path) -> str | None:
    try:
        p = _version_file(app_dir)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        v = str(data.get("version") or "").strip()
        return v or None
    except Exception:
        return None


def _http_get_json(url: str, timeout_s: int = 15) -> dict[str, Any]:
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests not available in launcher") from e

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "platform_scrapper-launcher",
    }
    r = requests.get(url, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def _http_download(url: str, dst: Path, timeout_s: int = 60) -> None:
    try:
        import requests
    except Exception as e:
        raise RuntimeError("requests not available in launcher") from e

    headers = {"User-Agent": "platform_scrapper-launcher"}
    with requests.get(url, headers=headers, timeout=timeout_s, stream=True) as r:
        r.raise_for_status()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _find_zip_asset(release: dict[str, Any]) -> tuple[str, ReleaseAsset] | None:
    tag = str(release.get("tag_name") or "").strip()
    assets = release.get("assets") or []
    for a in assets:
        name = str(a.get("name") or "")
        if name.startswith(ASSET_ZIP_PREFIX) and name.endswith(ASSET_ZIP_SUFFIX):
            return tag, ReleaseAsset(
                name=name,
                url=str(a.get("browser_download_url") or ""),
                size=int(a.get("size") or 0) or None,
            )
    return None


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)


def _atomic_replace_dir(src_dir: Path, dst_dir: Path) -> None:
    # Windows-friendly: rename dst->dst.old, then move src->dst
    parent = dst_dir.parent
    tmp_old = parent / f"{dst_dir.name}.old"
    if tmp_old.exists():
        shutil.rmtree(tmp_old, ignore_errors=True)
    if dst_dir.exists():
        dst_dir.replace(tmp_old)
    src_dir.replace(dst_dir)
    shutil.rmtree(tmp_old, ignore_errors=True)


def _launch_app(app_dir: Path) -> None:
    exe = app_dir / "platform_scrapper.exe"
    if not exe.exists():
        # dev fallback: run python entry
        os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve().parent / "app_entry.py")])
    os.execv(str(exe), [str(exe)])


def main() -> None:
    app_dir = _app_dir()

    # Fast path for portable builds: if packed app already exists locally,
    # launch it directly without doing any network / update checks.
    exe = app_dir / "platform_scrapper.exe"
    if exe.exists():
        _launch_app(app_dir)
        return

    base_dir = Path(sys.executable).resolve().parent

    # If no app installed yet, force update/install.
    local_v = _read_local_version(app_dir)

    try:
        release = _http_get_json(GITHUB_API_LATEST)
        found = _find_zip_asset(release)
    except Exception:
        found = None

    if not found:
        # Can't reach updates; run existing app if present.
        if app_dir.exists():
            _launch_app(app_dir)
        print("No app installed and cannot fetch release metadata.")
        time.sleep(3)
        return

    tag, asset = found
    remote_v = tag.lstrip("v").strip() or tag

    # If same version, launch.
    if local_v and local_v == remote_v and app_dir.exists():
        _launch_app(app_dir)

    # Download & install update.
    with tempfile.TemporaryDirectory(prefix="platform_scrapper_update_") as td:
        td_path = Path(td)
        zip_path = td_path / asset.name
        _http_download(asset.url, zip_path)

        extracted = td_path / "extracted"
        _extract_zip(zip_path, extracted)

        # Expect zip contains an "app" folder (portable layout)
        new_app_dir = extracted / "app"
        if not new_app_dir.exists():
            # Allow zip to directly contain files of app dir
            new_app_dir = extracted

        # Ensure version.json exists
        (_version_file(new_app_dir)).write_text(json.dumps({"version": remote_v}, ensure_ascii=False), encoding="utf-8")

        _atomic_replace_dir(new_app_dir, app_dir)

    _launch_app(app_dir)


if __name__ == "__main__":
    main()

