"""A specimen list PDF for a folder: one row per font with its name and a
sample line set in that font, many fonts per A4 page, grouped by folder.

Works straight from the folder (no library DB). Rendering goes through
Pillow/FreeType, which opens old or slightly broken fonts that stricter
renderers reject; pages are raster at 200 dpi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

from glyphmatrix.core.scanner import is_skipped

FONT_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc", ".fon", ".pfb", ".pfa", ".bdf", ".pcf", ".woff", ".woff2"}
DEFAULT_SAMPLE = "The quick brown fox jumps over the lazy dog 0123456789"

DPI = 200
PAGE_W, PAGE_H = 1654, 2339  # A4 at 200 dpi
MARGIN = 120
HEADER_H = 110
FOOTER_H = 70
ROW_H = 128
HEADING_H = 96
LABEL_SIZE = 22
# Samples are sized by the ink they actually put on the page, not by the
# nominal font size: fonts drawn small in their em box are scaled up, and a
# font too wide to fit at a readable height loses words instead of shrinking.
TARGET_GLYPH = 38  # px at 200 dpi: median height of the sample's characters
MIN_GLYPH = 30     # never smaller than this; drop words instead
MAX_INK = 88       # the whole line (tallest mark to lowest) must still fit the row
SAMPLE_SLOT = 80  # vertical room for the sample inside a row

_INK = 17
_LABEL = 100
_RULE = 205
_UI_CANDIDATES = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
_UI_BOLD_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)
_VERSION_DIR = re.compile(r"^(v\d|©\d|No Version$)")


@dataclass
class SpecimenEntry:
    path: Path
    label: str
    group: str
    sample: str | None  # None: cannot be previewed
    note: str = ""
    encoding: str = ""  # Pillow/FreeType charmap: "" (Unicode) or "symb" (MS Symbol)


def _ui(size: int, bold: bool = False):
    for candidate in (_UI_BOLD_CANDIDATES if bold else ()) + _UI_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _group_for(rel: Path) -> str:
    """Section heading: the folders above the family, for an organized
    Vendor/[Series/]Family/Version/file layout; otherwise the file's folder."""
    parts = rel.parts[:-1]
    if len(parts) >= 2 and _VERSION_DIR.match(parts[-1]):
        parts = parts[:-2]
    return " / ".join(parts)


# Letters whose drawings are this many times wider than tall are word-art
# ("b" = "5th grade"): a pangram is meaningless there, show the pictures.
WORD_ART_RATIO = 2.2


def _word_art_letters(font: TTFont, cmap: dict) -> str | None:
    """The letters of a word-art font (each letter draws a whole word or
    phrase), or None for an ordinary font."""
    try:
        glyph_set = font.getGlyphSet()
        hmtx = font["hmtx"]
    except Exception:
        return None
    ratios, letters = [], []
    for ch in "abcdefghijklmnopqrstuvwxyz":
        name = cmap.get(ord(ch))
        if name is None:
            continue
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[name].draw(pen)
        except Exception:
            continue
        if pen.bounds is None:
            continue
        height = pen.bounds[3] - pen.bounds[1]
        if height <= 0:
            continue
        ratios.append(hmtx[name][0] / height)
        letters.append(ch)
    if len(ratios) < 5:
        return None
    ratios.sort()
    return "".join(letters) if ratios[len(ratios) // 2] >= WORD_ART_RATIO else None


def _describe(path: Path, sample_text: str) -> tuple[str, str | None, str, str]:
    """(label, sample to draw or None, note, FreeType encoding)."""
    if path.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"}:
        return path.stem, None, f"no preview for {path.suffix.lower()} files", ""
    try:
        font = TTFont(path, lazy=True, fontNumber=0)
    except Exception as exc:
        return path.stem, None, f"unreadable: {exc}", ""
    with font:
        names = font["name"]
        family = (names.getBestFamilyName() or path.stem).strip()
        style = (names.getBestSubFamilyName() or "Regular").strip()
        if style.casefold() in (family.casefold(), "normal"):
            style = "Regular"
        cmap = font.getBestCmap() or {}
        word_art = _word_art_letters(font, cmap) if cmap else None
        symbol = {}
        if not cmap and "cmap" in font:
            # Old dingbat fonts map their pictures only through the Microsoft
            # Symbol charmap (3,0), at U+F020-F0FF.
            for table in font["cmap"].tables:
                if table.platformID == 3 and table.platEncID == 0:
                    symbol.update(table.cmap)
    label = family if style == "Regular" else f"{family} {style}"
    if symbol:
        own = [chr(c) for c in sorted(symbol) if (c & 0xFF) > 0x20][:40]
        return label, "".join(own) or None, "symbol font", "symb"
    if word_art:
        return label, word_art, "word-art font", ""
    wanted = [c for c in sample_text if not c.isspace()]
    covered = sum(1 for c in wanted if ord(c) in cmap)
    if wanted and covered / len(wanted) >= 0.6:
        return label, sample_text, "", ""
    # Dingbat or non-Latin font: show what it does contain (private-use
    # pictures included).
    own = [
        chr(c) for c in sorted(cmap)
        if c > 0x20 and (chr(c).isprintable() or 0xE000 <= c <= 0xF8FF)
    ][:40]
    if not own:
        return label, None, "no printable characters", ""
    return label, "".join(own), "shows the font's own characters", ""


def collect(root: str | Path, sample_text: str = DEFAULT_SAMPLE) -> list[SpecimenEntry]:
    root = Path(root)
    files = sorted(
        (
            p for p in root.rglob("*")
            if p.suffix.lower() in FONT_SUFFIXES and not is_skipped(p, root) and p.is_file()
        ),
        key=lambda p: str(p.relative_to(root)).casefold(),
    )
    entries = []
    for path in files:
        label, sample, note, encoding = _describe(path, sample_text)
        entries.append(
            SpecimenEntry(path, label, _group_for(path.relative_to(root)), sample, note, encoding)
        )
    return entries


def _median_glyph_height(font, text: str) -> float:
    heights = sorted(
        box[3] - box[1]
        for box in (font.getbbox(c) for c in set(text) if not c.isspace())
        if box[3] > box[1]
    )
    return heights[len(heights) // 2] if heights else 0


def _fit_font(path: Path, text: str, width: int, encoding: str = "", pictures: bool = False):
    """(font, text) sized by the median character height (so one huge capital
    or a font drawn small in its em box doesn't skew it), capped so the whole
    line fits the row, reduced towards MIN_GLYPH if too wide, then whole words
    (or, for one long word, characters) dropped from the end.
    pictures: the sample is the font's own symbols or word-art; use the
    largest size the row allows and show fewer of them instead of shrinking.
    (None, text) if FreeType can't open the font."""
    try:
        probe = ImageFont.truetype(str(path), 100, encoding=encoding)
        box = probe.getbbox(text)
    except OSError:
        return None, text
    median = _median_glyph_height(probe, text) or max(box[3] - box[1], 1)
    ink = max(box[3] - box[1], 1)
    ceiling = min(220, round(100 * MAX_INK / ink))
    if pictures:
        size = floor = max(8, ceiling)
    else:
        size = max(8, min(ceiling, round(100 * TARGET_GLYPH / median)))
        floor = max(8, min(size, round(100 * MIN_GLYPH / median)))
    font = ImageFont.truetype(str(path), size, encoding=encoding)
    while font.getlength(text) > width and size > floor:
        size = max(floor, int(size * 0.92))
        font = ImageFont.truetype(str(path), size, encoding=encoding)
    return font, _clip_words(text, font, width)


def _clip_words(text: str, font, width: int) -> str:
    words = text.split(" ")
    while len(words) > 1 and font.getlength(" ".join(words)) > width:
        words.pop()
    return _clip(" ".join(words), font, width)


def _clip(text: str, font, width: int) -> str:
    while text and font.getlength(text) > width:
        text = text[:-1]
    return text


def render(entries: list[SpecimenEntry], output: str | Path, title: str) -> tuple[Path, int]:
    """Lay entries out on A4 pages and save a PDF. Returns (path, pages)."""
    label_font = _ui(LABEL_SIZE)
    note_font = _ui(LABEL_SIZE - 2)
    heading_font = _ui(30, bold=True)
    header_font = _ui(26, bold=True)
    footer_font = _ui(20)
    content_w = PAGE_W - 2 * MARGIN
    bottom = PAGE_H - MARGIN - FOOTER_H

    pages: list[Image.Image] = []
    page = draw = None
    y = 0
    current_group = None

    def new_page():
        nonlocal page, draw, y
        page = Image.new("L", (PAGE_W, PAGE_H), 255)
        draw = ImageDraw.Draw(page)
        draw.text((MARGIN, MARGIN), _clip(title, header_font, content_w), font=header_font, fill=_INK)
        draw.line([(MARGIN, MARGIN + 52), (PAGE_W - MARGIN, MARGIN + 52)], fill=_INK, width=2)
        pages.append(page)
        y = MARGIN + HEADER_H

    new_page()
    for entry in entries:
        heading = entry.group != current_group
        needed = ROW_H + (HEADING_H if heading and entry.group else 0)
        if y + needed > bottom:
            new_page()
            heading = True  # repeat the section name on a new page
        if heading and entry.group:
            y += 24
            draw.text((MARGIN, y), _clip(entry.group, heading_font, content_w), font=heading_font, fill=_INK)
            y += HEADING_H - 24
        current_group = entry.group

        draw.text((MARGIN, y), _clip(entry.label, label_font, content_w), font=label_font, fill=_LABEL)
        sample_top = y + 34
        font, sample = (
            _fit_font(entry.path, entry.sample, content_w, entry.encoding, pictures=bool(entry.note))
            if entry.sample
            else (None, "")
        )
        if font is not None:
            try:
                box = font.getbbox(sample)
                top = sample_top + max(0, (SAMPLE_SLOT - (box[3] - box[1])) // 2) - box[1]
                draw.text((MARGIN, top), sample, font=font, fill=_INK)
            except Exception:
                font = None
                entry.note = entry.note or "could not draw this font"
        if font is None:
            draw.text((MARGIN, sample_top + 14), f"({entry.note or 'no preview'})", font=note_font, fill=_LABEL)
        elif entry.note:
            note_w = note_font.getlength(entry.note)
            draw.text((PAGE_W - MARGIN - note_w, y), entry.note, font=note_font, fill=_LABEL)
        y += ROW_H
        draw.line([(MARGIN, y - 10), (PAGE_W - MARGIN, y - 10)], fill=_RULE, width=1)

    total = len(pages)
    for number, img in enumerate(pages, start=1):
        d = ImageDraw.Draw(img)
        footer = f"{len(entries)} fonts  ·  page {number} of {total}"
        w = footer_font.getlength(footer)
        d.text((PAGE_W - MARGIN - w, PAGE_H - MARGIN - 20), footer, font=footer_font, fill=_LABEL)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(output, "PDF", save_all=True, append_images=pages[1:], resolution=DPI)
    return output, total


def export_specimen(
    root: str | Path, output: str | Path, sample_text: str = DEFAULT_SAMPLE, title: str | None = None
) -> tuple[Path, int, int]:
    """Returns (pdf path, font count, page count)."""
    root = Path(root)
    entries = collect(root, sample_text)
    if not entries:
        raise ValueError(f"no font files under {root}")
    path, pages = render(entries, output, title or root.name)
    return path, len(entries), pages
