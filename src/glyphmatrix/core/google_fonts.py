from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

_API_BASE = "https://www.googleapis.com/webfonts/v1/webfonts"

# variant strings as returned by the API ("regular", "italic", "700", "700italic")
# mapped to a friendlier filename suffix
_VARIANT_SUFFIX: dict[str, str] = {
    "regular": "Regular",
    "italic": "Italic",
}


def _variant_suffix(variant: str) -> str:
    if variant in _VARIANT_SUFFIX:
        return _VARIANT_SUFFIX[variant]
    # e.g. "700" -> "700", "700italic" -> "700Italic"
    if variant.endswith("italic"):
        return variant[:-6] + "Italic"
    return variant


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "glyphmatrix/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"Google Fonts API error {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error: {exc.reason}") from exc


def get_catalog(api_key: str, sort: str = "alpha") -> list[dict]:
    """Return all font families from the Google Fonts catalog.

    sort: 'alpha' (default), 'popularity', 'date', 'trending', 'style'
    Each item: family, category, variants, subsets, files.
    """
    url = f"{_API_BASE}?key={api_key}&sort={sort}"
    data = _get(url)
    return data.get("items", [])


def search_catalog(api_key: str, term: str, sort: str = "alpha") -> list[dict]:
    """Case-insensitive substring match on family name."""
    term_lower = term.lower()
    return [f for f in get_catalog(api_key, sort=sort) if term_lower in f["family"].lower()]


def get_family(api_key: str, family_name: str) -> dict | None:
    """Return the catalog entry for an exact family name (case-insensitive),
    or None if not found."""
    name_lower = family_name.lower()
    for item in get_catalog(api_key):
        if item["family"].lower() == name_lower:
            return item
    return None


def download_family(api_key: str, family_name: str, dest_dir: str | Path) -> list[Path]:
    """Download all font files for a family to dest_dir.

    Returns the list of downloaded file paths. dest_dir is created if needed.
    Skips files that already exist at the destination (idempotent).
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    item = get_family(api_key, family_name)
    if item is None:
        raise ValueError(f"family {family_name!r} not found in Google Fonts catalog")

    downloaded: list[Path] = []
    safe_name = item["family"].replace(" ", "")

    for variant, url in item.get("files", {}).items():
        ext = Path(url).suffix or ".ttf"
        filename = f"{safe_name}-{_variant_suffix(variant)}{ext}"
        dest_path = dest / filename

        if dest_path.exists():
            downloaded.append(dest_path)
            continue

        req = urllib.request.Request(url, headers={"User-Agent": "glyphmatrix/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest_path.write_bytes(resp.read())
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to download {url}: {exc.reason}") from exc

        downloaded.append(dest_path)

    return downloaded
