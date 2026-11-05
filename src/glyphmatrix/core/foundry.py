"""Resolve a font's foundry when nameID 8 (Manufacturer) is empty.

Many real-world fonts leave nameID 8 blank. Resolution order, most to least
reliable:

1. nameID 8 (Manufacturer) — what the font says about itself.
2. OS/2.achVendID mapped to a name — the vendor ID registered with Microsoft.
   Only well-known IDs are mapped; unknown IDs are not guessed from.
3. The holder named in the copyright string (nameID 0) — last resort, since
   copyright can name a commissioner or a later owner rather than the maker.

Returns the foundry name and which signal it came from, so callers can show
how trustworthy the value is.
"""
from __future__ import annotations

import re

# Vendor IDs are case-sensitive 4-byte tags ("MONO" != "Mono").
VENDOR_IDS: dict[str, str] = {
    "1ASC": "Ascender",
    "ADBE": "Adobe",
    "APPL": "Apple",
    "B&H ": "Bigelow & Holmes",
    "BITS": "Bitstream",
    "DAMA": "Dalton Maag",
    "DYNA": "DynaComware",
    "FTH ": "Font House",
    "GOOG": "Google",
    "Glyf": "Glyph Systems",
    "H&FJ": "Hoefler & Co.",
    "ITC ": "ITC",
    "LINO": "Linotype",
    "MONO": "Monotype",
    "MS  ": "Microsoft",
    "MSFT": "Microsoft",
    "TPTC": "Test Pilot Collective",
    "URW ": "URW",
    "ULA ": "Underware",
}

# Tool defaults and placeholders that say nothing about who made the font.
_PLACEHOLDER_VENDOR_IDS = {"", "????", "NONE", "UKWN", "PfEd", "XXXX", "\x00\x00\x00\x00"}

_COMPANY_SUFFIX = re.compile(
    r"[,\s]+(Inc|Incorporated|Ltd|Limited|Corp|Corporation|Co|Company|GmbH|AG|LLC|plc|S\.A|"
    r"Limited Partnership)\.?$",
    re.IGNORECASE,
)
_COPYRIGHT_MARK = re.compile(r"(?:copyright|copr\.?|\(c\)|©)", re.IGNORECASE)
_YEARS = re.compile(r"\b(?:19|20)\d{2}\b(?:\s*(?:[-–,/]|,?\s*and)\s*(?:(?:19|20)\d{2}|\d{2})\b)*")


def holder_from_copyright(copyright_text: str | None) -> str | None:
    """Pull the copyright holder's name out of a nameID 0 string, or None."""
    if not copyright_text:
        return None
    text = copyright_text.strip()
    match = _COPYRIGHT_MARK.search(text)
    if not match:
        return None
    rest = text[match.end():]
    # Strip any further copyright marks, years and "by" before the name.
    while True:
        stripped = _COPYRIGHT_MARK.sub("", rest, count=1) if _COPYRIGHT_MARK.match(rest.lstrip()) else rest
        stripped = stripped.lstrip(" .:,")
        stripped = _YEARS.sub("", stripped, count=1) if _YEARS.match(stripped) else stripped
        stripped = re.sub(r"^\s*(?:by)\s+", "", stripped, flags=re.IGNORECASE).lstrip(" .:,")
        if stripped == rest:
            break
        rest = stripped
    # The name runs until a sentence break, bracket, year or "All rights".
    name = re.split(r"\s*(?:[;(\[]|\.\s|\.$|\.(?=\d)|,\s*All rights|\s+All rights|\s+(?:19|20)\d{2}\b)",
                    rest, maxsplit=1)[0]
    name = _COMPANY_SUFFIX.sub("", name.strip(" .,")).strip(" .,")
    if not name or not name[0].isalpha() or len(name) > 60:
        return None
    return name


def resolve_foundry(
    manufacturer: str | None,
    vendor_id: str | None,
    copyright_text: str | None,
) -> tuple[str | None, str | None]:
    """Return (foundry, source), source being 'manufacturer', 'vendor_id',
    'copyright' or None when nothing usable was found."""
    if manufacturer and manufacturer.strip():
        return manufacturer.strip(), "manufacturer"
    if vendor_id is not None and vendor_id not in _PLACEHOLDER_VENDOR_IDS:
        name = VENDOR_IDS.get(vendor_id)
        if name:
            return name, "vendor_id"
    holder = holder_from_copyright(copyright_text)
    if holder:
        return holder, "copyright"
    return None, None
