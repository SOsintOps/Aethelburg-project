"""Bulk downloads into `<data folder>/downloads/<source>/<version>/`.

Each completed release has a `manifest.json` (url, sha256, extracted file); a release that is
already complete is never downloaded again. Interrupted downloads resume from the `.part` file
when the server honours HTTP Range, and restart from zero otherwise.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config.settings import get_settings
from src.core.logging import get_logger
from src.datasources.catalog import SOURCES, USER_AGENT, Release, latest_release
from src.services.db_service import DatabaseService

log = get_logger(__name__)

ProgressCallback = Callable[[int, int | None], None]  # (bytes done, total bytes or None)
_CHUNK = 1024 * 1024


def release_dir(release: Release) -> Path:
    return get_settings().paths.downloads_dir / release.source / release.version


def local_releases(source: str) -> list[dict[str, Any]]:
    """Completed releases of `source` on disk, newest first."""
    base = get_settings().paths.downloads_dir / source
    if not base.is_dir():
        return []
    found = []
    for manifest in base.glob("*/manifest.json"):
        try:
            found.append(json.loads(manifest.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(found, key=lambda m: m["version"], reverse=True)


def latest_local_file(source: str) -> Path | None:
    """Data file (extracted CSV/TXT) of the newest completed release, if any."""
    for manifest in local_releases(source):
        path = Path(manifest["data_file"])
        if path.exists():
            return path
    return None


def download_source(
    source: str,
    release: Release | None = None,
    progress: ProgressCallback | None = None,
    db: DatabaseService | None = None,
) -> dict[str, Any]:
    """Download and unpack the latest (or given) release of `source`; no-op if already complete."""
    release = release or latest_release(source)
    target = release_dir(release)
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if Path(manifest["data_file"]).exists():
            return {**manifest, "status": "already-downloaded"}

    target.mkdir(parents=True, exist_ok=True)
    archive = target / release.filename
    sha256 = _download(release.url, archive, progress)
    data_file = _extract(archive, SOURCES[source].extract_pattern, target)

    manifest = {
        "source": source,
        "version": release.version,
        "url": release.url,
        "file": str(archive),
        "sha256": sha256,
        "bytes": archive.stat().st_size,
        "data_file": str(data_file),
        "downloaded_at": datetime.now(UTC).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if data_file != archive:
        archive.unlink()  # the extracted file is what the importers read; keep disk use down
        manifest["file_removed"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    (db or DatabaseService()).register_data_source(
        source_name=SOURCES[source].title,
        source_type=source,
        source_version=release.version,
        source_url=release.url,
        file_hash=sha256,
        notes=f"Downloaded to {data_file}",
    )
    log.info("download_complete", source=source, version=release.version, bytes=manifest["bytes"])
    return {**manifest, "status": "downloaded"}


def _download(url: str, dest: Path, progress: ProgressCallback | None) -> str:
    part = dest.with_name(dest.name + ".part")
    done = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if done:
        headers["Range"] = f"bytes={done}-"

    with httpx.Client(timeout=httpx.Timeout(60.0, read=300.0), follow_redirects=True) as client:
        with client.stream("GET", url, headers=headers) as resp:
            if done and resp.status_code == 200:
                done = 0  # server ignored Range: start again
            elif resp.status_code not in (200, 206):
                raise RuntimeError(f"Download failed: HTTP {resp.status_code} for {url}")
            length = resp.headers.get("Content-Length")
            total = done + int(length) if length else None
            with part.open("ab" if done else "wb") as fh:
                for chunk in resp.iter_bytes(_CHUNK):
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)

    if total is not None and part.stat().st_size != total:
        raise RuntimeError(f"Download incomplete ({part.stat().st_size} of {total} bytes); run it again to resume")
    part.replace(dest)
    return _sha256(dest)


def _extract(archive: Path, pattern: str | None, target: Path) -> Path:
    if pattern is None or not zipfile.is_zipfile(archive):
        return archive
    with zipfile.ZipFile(archive) as zf:
        members = [m for m in zf.namelist() if fnmatch.fnmatch(m, pattern) or fnmatch.fnmatch(Path(m).name, pattern)]
        if not members:
            raise RuntimeError(f"{archive.name}: no file matching {pattern!r} (contents: {zf.namelist()[:10]})")
        member = members[0]
        out = target / Path(member).name
        with zf.open(member) as src, out.open("wb") as dst:
            shutil.copyfileobj(src, dst, _CHUNK)
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()
