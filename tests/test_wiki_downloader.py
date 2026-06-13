"""Tests for GearCity Wiki downloader."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gearcity_optimizer.importers.wiki_downloader import (
    build_export_urls,
    download_wiki_pages,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wiki"


def test_build_export_urls_from_chassis_page():
    """Export URLs should include encoded page id and correct do parameter."""
    url = "https://wiki.gearcity.info/doku.php?id=gamemanual:gm_chassis_design"
    exports = build_export_urls(url)

    assert exports["export_raw"] == (
        "https://wiki.gearcity.info/doku.php?do=export_raw&id=gamemanual%3Agm_chassis_design"
    )
    assert exports["export_xhtmlbody"] == (
        "https://wiki.gearcity.info/doku.php?do=export_xhtmlbody&id=gamemanual%3Agm_chassis_design"
    )


def test_downloader_skips_existing_files_when_not_forced(tmp_path: Path):
    """Downloader should not refetch when cached files exist and force=False."""
    urls_file = FIXTURES / "test_urls.json"
    html_dir = tmp_path / "wiki_html"
    raw_dir = tmp_path / "wiki_raw"
    text_dir = tmp_path / "wiki_text"
    html_dir.mkdir()
    raw_dir.mkdir()
    text_dir.mkdir()

    cached_html = html_dir / "test_page.html"
    cached_html.write_text("<html>cached</html>", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.text = "<html>fresh</html>"
    mock_response.raise_for_status = MagicMock()

    with patch("gearcity_optimizer.importers.wiki_downloader.requests.Session") as session_cls:
        session = session_cls.return_value
        session.get.return_value = mock_response

        results = download_wiki_pages(
            urls_file=urls_file,
            html_output_dir=html_dir,
            raw_output_dir=raw_dir,
            text_output_dir=text_dir,
            force=False,
            delay_seconds=0,
            manifest_path=tmp_path / "manifest.json",
        )

    assert cached_html.read_text(encoding="utf-8") == "<html>cached</html>"
    assert results[0]["skipped"] == ["html"]
    html_calls = [
        call.args[0]
        for call in session.get.call_args_list
        if call.args[0].endswith("gm_chassis_design")
        and "do=" not in call.args[0]
    ]
    assert html_calls == []


def test_downloader_redownloads_when_forced(tmp_path: Path):
    """Downloader should refetch when force=True."""
    urls_file = FIXTURES / "test_urls.json"
    html_dir = tmp_path / "wiki_html"
    raw_dir = tmp_path / "wiki_raw"
    text_dir = tmp_path / "wiki_text"
    html_dir.mkdir()
    raw_dir.mkdir()
    text_dir.mkdir()

    cached_html = html_dir / "test_page.html"
    cached_html.write_text("<html>cached</html>", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.text = "<html>fresh</html>"
    mock_response.raise_for_status = MagicMock()

    with patch("gearcity_optimizer.importers.wiki_downloader.requests.Session") as session_cls:
        session = session_cls.return_value
        session.get.return_value = mock_response

        download_wiki_pages(
            urls_file=urls_file,
            html_output_dir=html_dir,
            raw_output_dir=raw_dir,
            text_output_dir=text_dir,
            force=True,
            delay_seconds=0,
            manifest_path=tmp_path / "manifest.json",
        )

    assert cached_html.read_text(encoding="utf-8") == "<html>fresh</html>"
