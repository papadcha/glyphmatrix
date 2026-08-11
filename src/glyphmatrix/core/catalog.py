from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from glyphmatrix.core.licenses import classify_license
from glyphmatrix.core.query import get_family_detail
from glyphmatrix.core.renderer import DEFAULT_TEXT
from glyphmatrix.core.tags import list_tags_for_face

PAGE_W = 1200
MARGIN = 60
GUTTER = 16
HEADER_H = 120
PREVIEW_SIZE = 28
WATERFALL_SIZES = (14, 20, 28, 40)

_GRAY_BG = "#f0f0f0"
_DIVIDER = "#cccccc"
_LABEL_COLOR = "#555555"
_BLACK = "#111111"

_UI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/gsfonts/NimbusSans-Regular.otf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def _ui_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _UI_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _text_h(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]


def _first_loadable_file(face: dict) -> str | None:
    for f in face["files"]:
        try:
            ImageFont.truetype(f["path"], 12)
            return f["path"]
        except (OSError, IOError):
            continue
    return None


def _render_family_page(
    conn: sqlite3.Connection, family_name: str, preview_text: str
) -> Image.Image:
    detail = get_family_detail(conn, family_name)
    if detail is None:
        raise ValueError(f"family not found: {family_name!r}")

    ui_sm = _ui_font(13)
    ui_md = _ui_font(17)
    ui_lg = _ui_font(36)
    measuring = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    # — collect face rows (metadata + preview image) —
    face_rows: list[dict] = []
    for face in detail["faces"]:
        face_id_row = conn.execute(
            """
            SELECT font_faces.id FROM font_faces
            JOIN families ON families.id = font_faces.family_id
            WHERE families.name = ? COLLATE NOCASE AND font_faces.style = ? COLLATE NOCASE
            ORDER BY font_faces.id
            """,
            (family_name, face["style"] or ""),
        ).fetchone()
        tags = list_tags_for_face(conn, face_id_row["id"]) if face_id_row else []
        license_cat = classify_license(face["files"][0]["license"]) if face["files"] else None
        font_path = _first_loadable_file(face)

        preview_img: Image.Image | None = None
        if font_path:
            try:
                pf = ImageFont.truetype(font_path, PREVIEW_SIZE)
                bb = measuring.textbbox((0, 0), preview_text, font=pf)
                pw = min(bb[2] - bb[0] + 2 * GUTTER, PAGE_W - MARGIN * 2 - 180)
                ph = bb[3] - bb[1] + 2 * GUTTER
                preview_img = Image.new("RGB", (pw, ph), "white")
                ImageDraw.Draw(preview_img).text(
                    (GUTTER - bb[0], GUTTER - bb[1]), preview_text, font=pf, fill=_BLACK
                )
            except (OSError, IOError, Exception):
                preview_img = None

        face_rows.append(
            {
                "style": face["style"] or "Regular",
                "weight": face["weight"],
                "width": face["width"],
                "license": license_cat,
                "tags": tags,
                "preview": preview_img,
            }
        )

    # — waterfall from first loadable file —
    waterfall_img: Image.Image | None = None
    for face in detail["faces"]:
        font_path = _first_loadable_file(face)
        if font_path:
            try:
                lines = []
                max_w = 0
                total_h = GUTTER
                for sz in WATERFALL_SIZES:
                    wf = ImageFont.truetype(font_path, sz)
                    bb = measuring.textbbox((0, 0), preview_text, font=wf)
                    lh = bb[3] - bb[1]
                    lines.append((wf, bb, lh))
                    max_w = max(max_w, bb[2] - bb[0])
                    total_h += lh + GUTTER
                ww = min(max_w + 2 * GUTTER, PAGE_W - MARGIN * 2)
                waterfall_img = Image.new("RGB", (ww, total_h), "white")
                wd = ImageDraw.Draw(waterfall_img)
                y = GUTTER
                for wf, bb, lh in lines:
                    wd.text((GUTTER - bb[0], y - bb[1]), preview_text, font=wf, fill=_BLACK)
                    y += lh + GUTTER
            except (OSError, IOError, Exception):
                waterfall_img = None
            break

    # — compute total page height —
    face_block_h = 0
    for row in face_rows:
        face_block_h += _text_h(measuring, row["style"], ui_md) + GUTTER
        if row["preview"]:
            face_block_h += row["preview"].height + GUTTER

    waterfall_h = (waterfall_img.height + GUTTER * 2) if waterfall_img else 0
    meta_h = _text_h(measuring, "X", ui_sm) + GUTTER * 2

    page_h = (
        HEADER_H
        + GUTTER
        + meta_h
        + GUTTER
        + face_block_h
        + GUTTER
        + waterfall_h
        + MARGIN
    )

    # — draw the page —
    page = Image.new("RGB", (PAGE_W, max(page_h, 400)), "white")
    draw = ImageDraw.Draw(page)

    # header bar
    draw.rectangle([(0, 0), (PAGE_W, HEADER_H)], fill=_GRAY_BG)
    draw.text((MARGIN, HEADER_H // 2 - 22), family_name, font=ui_lg, fill=_BLACK)
    if detail["foundry"]:
        fw = measuring.textbbox((0, 0), detail["foundry"], font=ui_sm)[2]
        draw.text(
            (PAGE_W - MARGIN - fw, HEADER_H // 2 - 8),
            detail["foundry"],
            font=ui_sm,
            fill=_LABEL_COLOR,
        )

    # metadata line
    y = HEADER_H + GUTTER
    face_count = len(detail["faces"])
    meta_parts = [f"{face_count} face(s)"]
    all_licenses = {
        classify_license(f["license"])
        for face in detail["faces"]
        for f in face["files"]
        if classify_license(f["license"])
    }
    if all_licenses:
        meta_parts.append("  •  ".join(sorted(all_licenses)))
    draw.text((MARGIN, y), "  •  ".join(meta_parts), font=ui_sm, fill=_LABEL_COLOR)
    y += _text_h(drawing := draw, "X", ui_sm) + GUTTER * 2

    # divider
    draw.line([(MARGIN, y), (PAGE_W - MARGIN, y)], fill=_DIVIDER, width=1)
    y += GUTTER

    # face rows
    for row in face_rows:
        label = row["style"]
        if row["weight"]:
            label += f"  {row['weight']}"
        draw.text((MARGIN, y), label, font=ui_md, fill=_LABEL_COLOR)
        y += _text_h(draw, label, ui_md) + GUTTER // 2
        if row["preview"]:
            page.paste(row["preview"], (MARGIN, y))
            y += row["preview"].height + GUTTER

    if face_rows:
        draw.line([(MARGIN, y), (PAGE_W - MARGIN, y)], fill=_DIVIDER, width=1)
        y += GUTTER

    # waterfall
    if waterfall_img:
        draw.text((MARGIN, y), "Waterfall", font=ui_sm, fill=_LABEL_COLOR)
        y += _text_h(draw, "Waterfall", ui_sm) + GUTTER // 2
        page.paste(waterfall_img, (MARGIN, y))

    return page


def export_catalog(
    conn: sqlite3.Connection,
    output_path: str | Path,
    preview_text: str = DEFAULT_TEXT,
    families: list[str] | None = None,
) -> Path:
    """Export a PDF specimen catalog — one page per family.

    families: if given, only those families are included (in that order);
    otherwise all families in the library are included, alphabetically.
    Families not in the library are silently skipped.
    """
    if families is None:
        rows = conn.execute(
            "SELECT name FROM families ORDER BY name COLLATE NOCASE"
        ).fetchall()
        families = [row["name"] for row in rows]

    pages: list[Image.Image] = []
    for name in families:
        try:
            page = _render_family_page(conn, name, preview_text)
            pages.append(page)
        except (ValueError, Exception):
            continue

    if not pages:
        raise ValueError("no families to export")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(
        out,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=150,
    )
    return out
