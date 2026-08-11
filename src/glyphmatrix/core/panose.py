from __future__ import annotations

# PANOSE byte 1 (bFamilyType) — top-level kind. 0 (Any) and 1 (No Fit) are
# intentionally unmapped: no signal, same treatment as sFamilyClass's
# unmapped reserved classes in parser.py.
_FAMILY_KIND = {
    3: "hand-written",
    4: "decorative",
    5: "symbolic",
}

# PANOSE byte 2 (bSerifStyle) — only meaningful when bFamilyType == 2 (Latin
# Text), the common case for body/display fonts. Hand-written/decorative/
# symbol kinds (3-5) use a different byte-2 table each; not decoded here —
# narrower, more curated data per kind, out of scope for now (same call as
# license classification: ship the well-understood common case honestly
# rather than guess at the rest).
_SERIF_STYLE = {
    2: "cove",
    3: "obtuse-cove",
    4: "square-cove",
    5: "obtuse-square-cove",
    6: "square",
    7: "thin",
    8: "oval",
    9: "exaggerated",
    10: "triangle",
    11: "normal-sans",
    12: "obtuse-sans",
    13: "perp-sans",
    14: "flared",
    15: "rounded",
}

_LATIN_TEXT = 2


def classify_panose(panose_bytes: tuple[int, ...]) -> str | None:
    """One fine-grained tag from a font's own embedded 10-byte PANOSE vector
    (bFamilyType, bSerifStyle, ...) — finer than sFamilyClass's ~10 broad
    buckets, e.g. distinguishing "normal-sans" from "flared" or "rounded"
    within what sFamilyClass would just call "sans-serif". All-zero (or
    missing) PANOSE is common in real fonts — many never set it — so None
    means "no signal", not "not a text face"."""
    if not panose_bytes or not any(panose_bytes):
        return None
    family_type = panose_bytes[0]
    if family_type == _LATIN_TEXT and len(panose_bytes) > 1:
        return _SERIF_STYLE.get(panose_bytes[1])
    return _FAMILY_KIND.get(family_type)
