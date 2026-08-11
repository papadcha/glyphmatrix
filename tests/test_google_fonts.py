from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from glyphmatrix.core.google_fonts import (
    _variant_suffix,
    download_family,
    get_catalog,
    get_family,
    search_catalog,
)

_FAKE_CATALOG = [
    {
        "family": "Roboto",
        "category": "sans-serif",
        "variants": ["regular", "italic", "700", "700italic"],
        "subsets": ["latin", "greek"],
        "files": {
            "regular": "https://fonts.gstatic.com/s/roboto/regular.ttf",
            "700": "https://fonts.gstatic.com/s/roboto/700.ttf",
        },
    },
    {
        "family": "Roboto Mono",
        "category": "monospace",
        "variants": ["regular"],
        "subsets": ["latin"],
        "files": {"regular": "https://fonts.gstatic.com/s/robotomono/regular.ttf"},
    },
    {
        "family": "Noto Serif",
        "category": "serif",
        "variants": ["regular", "700"],
        "subsets": ["latin", "greek"],
        "files": {
            "regular": "https://fonts.gstatic.com/s/notoserif/regular.ttf",
        },
    },
]


def _fake_urlopen(url_or_req, timeout=None):
    url = url_or_req.full_url if hasattr(url_or_req, "full_url") else str(url_or_req)
    if "webfonts" in url:
        body = json.dumps({"items": _FAKE_CATALOG}).encode()
    else:
        body = b"\x00\x01\x00\x00" * 256  # fake font bytes
    ctx = MagicMock()
    ctx.__enter__ = lambda s: BytesIO(body)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


@pytest.fixture(autouse=True)
def mock_http():
    with patch("glyphmatrix.core.google_fonts.urllib.request.urlopen", side_effect=_fake_urlopen):
        yield


def test_get_catalog_returns_all_families():
    items = get_catalog("fake-key")
    assert len(items) == 3
    assert items[0]["family"] == "Roboto"


def test_get_catalog_sort_param_is_passed_in_url():
    with patch("glyphmatrix.core.google_fonts.urllib.request.urlopen", side_effect=_fake_urlopen) as m:
        get_catalog("fake-key", sort="popularity")
    req = m.call_args[0][0]
    assert "sort=popularity" in req.full_url


def test_search_catalog_matches_substring_case_insensitively():
    results = search_catalog("fake-key", "roboto")
    assert len(results) == 2
    assert {r["family"] for r in results} == {"Roboto", "Roboto Mono"}


def test_search_catalog_no_match():
    results = search_catalog("fake-key", "zzznomatch")
    assert results == []


def test_get_family_exact_match_case_insensitive():
    item = get_family("fake-key", "roboto")
    assert item is not None
    assert item["family"] == "Roboto"


def test_get_family_not_found():
    item = get_family("fake-key", "Helvetica")
    assert item is None


def test_variant_suffix_standard():
    assert _variant_suffix("regular") == "Regular"
    assert _variant_suffix("italic") == "Italic"


def test_variant_suffix_weight_only():
    assert _variant_suffix("700") == "700"
    assert _variant_suffix("100") == "100"


def test_variant_suffix_weight_italic():
    assert _variant_suffix("700italic") == "700Italic"
    assert _variant_suffix("300italic") == "300Italic"


def test_download_family_creates_files(tmp_path):
    paths = download_family("fake-key", "Roboto", tmp_path)

    assert len(paths) == 2
    assert all(p.exists() for p in paths)
    names = {p.name for p in paths}
    assert "Roboto-Regular.ttf" in names
    assert "Roboto-700.ttf" in names


def test_download_family_is_idempotent(tmp_path):
    paths1 = download_family("fake-key", "Roboto", tmp_path)
    mtime1 = {p: p.stat().st_mtime for p in paths1}

    paths2 = download_family("fake-key", "Roboto", tmp_path)
    mtime2 = {p: p.stat().st_mtime for p in paths2}

    assert mtime1 == mtime2  # existing files not re-downloaded


def test_download_family_creates_dest_dir(tmp_path):
    dest = tmp_path / "new" / "subdir"
    download_family("fake-key", "Roboto", dest)
    assert dest.is_dir()


def test_download_family_unknown_family_raises():
    with pytest.raises(ValueError, match="not found in Google Fonts catalog"):
        download_family("fake-key", "Helvetica Neue", "/tmp")
