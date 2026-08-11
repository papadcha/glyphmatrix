from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


_SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+(.+)$")
_PDF_BASE_FONT = re.compile(rb"/BaseFont\s+/([^\s/\[\]<>()\x00]+)")

_ZIP_DOC_EXTENSIONS = {".docx", ".dotx", ".docm", ".odt", ".odp", ".ods", ".odg"}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_STYLE_NS = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
_SVG_NS = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"


def _strip_subset(name: str) -> str:
    m = _SUBSET_PREFIX.match(name)
    return m.group(1) if m else name


def _names_from_docx(path: Path) -> set[str]:
    names: set[str] = set()
    with zipfile.ZipFile(path) as zf:
        for candidate in ("word/fontTable.xml", "word/styles.xml"):
            if candidate not in zf.namelist():
                continue
            root = ET.fromstring(zf.read(candidate))
            for el in root.iter(f"{{{_W_NS}}}font"):
                name = el.get(f"{{{_W_NS}}}name")
                if name:
                    names.add(name)
            for el in root.iter(f"{{{_W_NS}}}rFonts"):
                for attr in (
                    f"{{{_W_NS}}}ascii",
                    f"{{{_W_NS}}}hAnsi",
                    f"{{{_W_NS}}}cs",
                    f"{{{_W_NS}}}eastAsia",
                ):
                    v = el.get(attr)
                    if v:
                        names.add(v)
    return names


def _names_from_odt(path: Path) -> set[str]:
    names: set[str] = set()
    with zipfile.ZipFile(path) as zf:
        for candidate in ("content.xml", "styles.xml"):
            if candidate not in zf.namelist():
                continue
            root = ET.fromstring(zf.read(candidate))
            for el in root.iter(f"{{{_STYLE_NS}}}font-face"):
                name = el.get(f"{{{_STYLE_NS}}}name") or el.get(f"{{{_SVG_NS}}}font-family")
                if name:
                    names.add(name)
    return names


def _names_from_pdf(path: Path) -> set[str]:
    raw = path.read_bytes()
    names: set[str] = set()
    for m in _PDF_BASE_FONT.finditer(raw):
        try:
            name = _strip_subset(m.group(1).decode("latin-1", errors="replace"))
            names.add(name)
        except Exception:
            continue
    return names


def extract_font_names(doc_path: str | Path) -> set[str]:
    """Return font family names referenced in a document.

    Supported: DOCX/DOTX/DOCM (Office XML), ODT/ODP/ODS/ODG (ODF), PDF.
    For PDF, names are PostScript names (/BaseFont entries) which may differ
    from fontctl family names — matching is done case-insensitively by the
    caller (see match_library_families).
    Raises ValueError for unsupported formats.
    """
    path = Path(doc_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _names_from_pdf(path)
    if suffix in {".docx", ".dotx", ".docm"}:
        return _names_from_docx(path)
    if suffix in {".odt", ".odp", ".ods", ".odg"}:
        return _names_from_odt(path)
    raise ValueError(
        f"unsupported document format: {suffix!r} — supported: .pdf, .docx, .odt, .odp"
    )


def match_library_families(
    conn: sqlite3.Connection, doc_names: set[str]
) -> tuple[list[str], list[str]]:
    """Match document font names against library family names.

    Returns (matched, unmatched):
    - matched: library family names that correspond to at least one doc font name
    - unmatched: doc names that had no library match

    Matching is case-insensitive substring: a doc name of "Arial-BoldMT" matches
    a library family "Arial"; "Times New Roman" matches "Times New Roman".
    """
    library_rows = conn.execute(
        "SELECT name FROM families ORDER BY name COLLATE NOCASE"
    ).fetchall()
    library_names = [row["name"] for row in library_rows]

    matched: list[str] = []
    unmatched: list[str] = []

    for doc_name in sorted(doc_names):
        doc_lower = doc_name.lower()
        hit = next(
            (lib for lib in library_names if lib.lower() in doc_lower or doc_lower in lib.lower()),
            None,
        )
        if hit and hit not in matched:
            matched.append(hit)
        elif hit is None:
            unmatched.append(doc_name)

    return matched, unmatched
