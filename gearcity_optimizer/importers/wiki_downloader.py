"""Download and cache GearCity Wiki pages from a fixed URL list."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

USER_AGENT = (
    "gearcity-optimizer/0.1 personal research tool; downloads only configured URLs"
)
TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
BACKOFF_SECONDS = (1, 2, 4)


def project_root_from_module() -> Path:
    """Return the project root directory."""
    return Path(__file__).resolve().parent.parent.parent


def build_export_urls(url: str) -> dict[str, str]:
    """
    Build DokuWiki export URLs from a normal page URL.

    Example input:
        https://wiki.gearcity.info/doku.php?id=gamemanual:gm_chassis_design

    Produces export_raw and export_xhtmlbody URLs with encoded page id.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    page_id = query.get("id", [None])[0]
    if not page_id:
        raise ValueError(f"Could not extract page id from URL: {url}")

    base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    return {
        "export_raw": f"{base}?{urlencode({'do': 'export_raw', 'id': page_id})}",
        "export_xhtmlbody": (
            f"{base}?{urlencode({'do': 'export_xhtmlbody', 'id': page_id})}"
        ),
    }


def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_with_retries(
    session: requests.Session,
    url: str,
) -> tuple[str | None, list[str]]:
    """Fetch a URL with retries and exponential backoff."""
    errors: list[str] = []

    for attempt in range(MAX_RETRIES):
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text, errors
        except requests.RequestException as exc:
            errors.append(f"Attempt {attempt + 1}: {exc}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(BACKOFF_SECONDS[attempt])

    return None, errors


def _download_to_file(
    session: requests.Session,
    url: str,
    output_path: Path,
    force: bool,
) -> tuple[bool, list[str]]:
    """
    Download content to a file if missing or force=True.

    Returns:
        (downloaded, errors) where downloaded is True if a new file was written.
    """
    if output_path.exists() and not force:
        return False, []

    content, errors = _fetch_with_retries(session, url)
    if content is None:
        return False, errors

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return True, errors


def _load_url_list(urls_file: Path) -> list[dict[str, str]]:
    """Load wiki URL definitions from JSON."""
    with urls_file.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def download_wiki_pages(
    urls_file: str | Path = "sources/wiki_urls.json",
    html_output_dir: str | Path = "sources/wiki_html",
    raw_output_dir: str | Path = "sources/wiki_raw",
    text_output_dir: str | Path = "sources/wiki_text",
    force: bool = False,
    delay_seconds: float = 1.0,
    manifest_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """
    Download configured GearCity Wiki pages and cache them locally.

    Only downloads explicit URLs from the JSON file. Does not crawl.
    """
    root = project_root_from_module()
    urls_path = Path(urls_file)
    if not urls_path.is_absolute():
        urls_path = root / urls_path

    html_dir = Path(html_output_dir)
    raw_dir = Path(raw_output_dir)
    text_dir = Path(text_output_dir)
    if not html_dir.is_absolute():
        html_dir = root / html_dir
    if not raw_dir.is_absolute():
        raw_dir = root / raw_dir
    if not text_dir.is_absolute():
        text_dir = root / text_dir

    for directory in (html_dir, raw_dir, text_dir):
        directory.mkdir(parents=True, exist_ok=True)

    if manifest_path is None:
        manifest_file = root / "generated/raw_parsed/wiki_download_manifest.json"
    else:
        manifest_file = Path(manifest_path)
        if not manifest_file.is_absolute():
            manifest_file = root / manifest_file
    manifest_file.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    entries = _load_url_list(urls_path)
    results: list[dict[str, Any]] = []

    for index, entry in enumerate(entries):
        name = entry["name"]
        url = entry["url"]

        html_path = html_dir / f"{name}.html"
        raw_path = raw_dir / f"{name}.txt"
        xhtml_path = text_dir / f"{name}.html"

        metadata: dict[str, Any] = {
            "name": name,
            "url": url,
            "purpose": entry.get("purpose", ""),
            "html_path": str(html_path),
            "raw_path": str(raw_path),
            "xhtmlbody_path": str(xhtml_path),
            "downloaded": False,
            "skipped": [],
            "errors": [],
            "sha256": None,
        }

        html_downloaded, html_errors = _download_to_file(
            session, url, html_path, force
        )
        if html_errors:
            metadata["errors"].extend([f"html: {err}" for err in html_errors])
        if html_downloaded:
            metadata["downloaded"] = True
        elif html_path.exists():
            metadata["skipped"].append("html")

        if index > 0 or html_downloaded:
            time.sleep(delay_seconds)

        try:
            export_urls = build_export_urls(url)
        except ValueError as exc:
            metadata["errors"].append(str(exc))
            export_urls = {}

        if export_urls:
            raw_downloaded, raw_errors = _download_to_file(
                session, export_urls["export_raw"], raw_path, force
            )
            if raw_errors:
                metadata["errors"].extend([f"export_raw: {err}" for err in raw_errors])
            if raw_downloaded:
                metadata["downloaded"] = True
            elif raw_path.exists():
                metadata["skipped"].append("export_raw")
            else:
                metadata["errors"].append("export_raw: download failed")

            time.sleep(delay_seconds)

            xhtml_downloaded, xhtml_errors = _download_to_file(
                session,
                export_urls["export_xhtmlbody"],
                xhtml_path,
                force,
            )
            if xhtml_errors:
                metadata["errors"].extend(
                    [f"export_xhtmlbody: {err}" for err in xhtml_errors]
                )
            if xhtml_downloaded:
                metadata["downloaded"] = True
            elif xhtml_path.exists():
                metadata["skipped"].append("export_xhtmlbody")
            else:
                metadata["errors"].append("export_xhtmlbody: download failed")

        if html_path.exists():
            metadata["sha256"] = _sha256_file(html_path)

        results.append(metadata)

        if index < len(entries) - 1:
            time.sleep(delay_seconds)

    manifest = {
        "user_agent": USER_AGENT,
        "urls_file": str(urls_path),
        "pages": results,
    }
    manifest_file.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return results
