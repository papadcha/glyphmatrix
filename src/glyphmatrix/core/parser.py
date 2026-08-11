from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.t1Lib import T1Font
from fontTools.ttLib import TTFont

from glyphmatrix.core.panose import classify_panose

# CSS-ish label per OS/2.usWidthClass (1-9). None if usWidthClass is absent/unknown.
_WIDTH_CLASSES = {
    1: "ultra-condensed",
    2: "extra-condensed",
    3: "condensed",
    4: "semi-condensed",
    5: "normal",
    6: "semi-expanded",
    7: "expanded",
    8: "extra-expanded",
    9: "ultra-expanded",
}

# High byte of OS/2.sFamilyClass (the "IBM font class"), per the OpenType
# spec — a classification type designers embed in the font, not inferred.
# Missing classes (0, 6, 11, 13) are either "No Classification" or reserved;
# left unmapped on purpose rather than guessed.
_FAMILY_CLASSES = {
    1: "oldstyle-serif",
    2: "transitional-serif",
    3: "modern-serif",
    4: "clarendon-serif",
    5: "slab-serif",
    7: "freeform-serif",
    8: "sans-serif",
    9: "ornamental",
    10: "script",
    12: "symbolic",
    14: "miscellaneous",
}


@dataclass
class ParsedGlyph:
    glyph_name: str
    unicode_codepoint: int | None
    contour_count: int
    advance_width: int | None
    outline_hash: str


@dataclass
class ParsedFont:
    family_name: str
    foundry: str | None
    style: str | None
    weight: int | None
    width: str | None
    is_variable: bool
    axes: dict | None
    path: Path
    filename: str
    format: str
    content_hash: str
    version: str | None
    license: str | None
    glyph_count: int
    glyphs: list[ParsedGlyph]
    family_class: str | None = None
    panose_class: str | None = None
    metadata_complete: bool = True


# SFNT (TrueType/OpenType) is the only family fully parsed today. Other
# scanned formats (Type 1, legacy bitmap) still get a font_files row —
# content_hash works the same regardless of format, so duplicate detection
# and basic visibility work — but no family/style/glyph metadata.
_SFNT_FORMATS = {"ttf", "otf", "ttc", "woff", "woff2"}
_T1_FORMATS = {"pfb", "pfa"}
_BDF_FORMATS = {"bdf"}
_PCF_FORMATS = {"pcf"}
_FON_FORMATS = {"fon"}

_T1_WEIGHT_NUMERIC: dict[str, int] = {
    "thin": 100, "hairline": 100,
    "extralight": 200, "extra light": 200, "ultralight": 200, "ultra light": 200,
    "light": 300,
    "book": 400, "regular": 400, "roman": 400, "normal": 400,
    "medium": 500,
    "semibold": 600, "semi bold": 600, "demibold": 600, "demi bold": 600, "demi": 600,
    "bold": 700,
    "extrabold": 800, "extra bold": 800,
    "black": 900, "heavy": 900, "ultra": 900,
}


_T1_REGULAR_WEIGHTS = {"book", "regular", "roman", "normal"}

# X11 XLFD "Medium" means the regular/normal weight (not CSS medium = 500).
_BDF_REGULAR_WEIGHTS = _T1_REGULAR_WEIGHTS | {"medium"}

_PCF_MAGIC = 0x70636601
_PCF_PROPERTIES_TYPE = 1
_PCF_METRICS_TYPE = 4
_PCF_BYTE_MASK = 1 << 2       # bit 2 in the format word: 0=LE, 1=BE
_PCF_COMPRESSED_METRICS = 0x100


def _bdf_style(weight_str: str, slant: str) -> str:
    ws_lower = weight_str.lower()
    style = "Regular" if ws_lower in _BDF_REGULAR_WEIGHTS else (weight_str.title() or "Regular")
    if slant.upper() in ("I", "O", "RI", "RO"):
        style = (style.replace("Regular", "").strip() + " Italic").strip()
    return style or "Regular"


def _bdf_unicode_charset(registry: str, encoding: str) -> bool:
    """True if ENCODING values in this charset are valid Unicode codepoints."""
    r = registry.lower().replace("-", "")
    return r in ("iso10646", "unicode") or (r in ("iso8859",) and encoding.strip() == "1")


def _parse_bdf(path: Path, content_hash: str) -> ParsedFont:
    text = path.read_text(encoding="latin-1", errors="replace")
    lines = text.splitlines()

    props: dict[str, str] = {}
    in_props = False
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("STARTPROPERTIES"):
            in_props = True
        elif line == "ENDPROPERTIES":
            in_props = False
        elif in_props:
            parts = line.split(None, 1)
            if len(parts) == 2:
                props[parts[0]] = parts[1].strip().strip('"')
        elif line.startswith("CHARS "):
            i += 1
            break
        i += 1

    family_name = props.get("FAMILY_NAME") or path.stem
    foundry = props.get("FOUNDRY")
    weight_str = props.get("WEIGHT_NAME") or ""
    slant = props.get("SLANT") or "R"
    registry = props.get("CHARSET_REGISTRY") or ""
    enc_val = props.get("CHARSET_ENCODING") or ""
    version = props.get("FONT_VERSION") or props.get("FONT_NAME")
    license_text = props.get("COPYRIGHT")
    weight_num = _T1_WEIGHT_NUMERIC.get(weight_str.lower())
    style = _bdf_style(weight_str, slant)
    use_cp = _bdf_unicode_charset(registry, enc_val)

    glyphs: list[ParsedGlyph] = []
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("STARTCHAR "):
            glyph_name = line[len("STARTCHAR "):]
            encoding: int | None = None
            dwidth: int | None = None
            bitmap_lines: list[str] = []
            in_bitmap = False
            i += 1
            while i < len(lines):
                gl = lines[i].strip()
                if gl == "ENDCHAR":
                    i += 1
                    break
                elif gl.startswith("ENCODING "):
                    encoding = int(gl.split()[1])
                elif gl.startswith("DWIDTH "):
                    dwidth = int(gl.split()[1])
                elif gl == "BITMAP":
                    in_bitmap = True
                elif in_bitmap:
                    bitmap_lines.append(gl)
                i += 1

            bitmap_bytes = bytes.fromhex("".join(bitmap_lines)) if bitmap_lines else b""
            outline_hash = hashlib.sha256(bitmap_bytes).hexdigest()
            codepoint = encoding if (use_cp and encoding is not None and encoding >= 0) else None
            glyphs.append(
                ParsedGlyph(
                    glyph_name=glyph_name,
                    unicode_codepoint=codepoint,
                    contour_count=0,
                    advance_width=dwidth,
                    outline_hash=outline_hash,
                )
            )
        else:
            i += 1

    return ParsedFont(
        family_name=family_name,
        foundry=foundry,
        style=style,
        weight=weight_num,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format="bdf",
        content_hash=content_hash,
        version=version,
        license=license_text,
        glyph_count=len(glyphs),
        glyphs=glyphs,
        metadata_complete=True,
    )


def _pcf_read_props(data: bytes, toffset: int) -> dict[str, str | int]:
    """Parse the PROPERTIES table from a PCF file, returning a dict of property name→value."""
    fmt_word = struct.unpack_from("<I", data, toffset)[0]
    bo = ">" if (fmt_word & _PCF_BYTE_MASK) else "<"
    off = toffset + 4
    nprops = struct.unpack_from(f"{bo}I", data, off)[0]
    off += 4
    prop_entries: list[tuple[int, int, int]] = []
    for _ in range(nprops):
        name_off = struct.unpack_from(f"{bo}I", data, off)[0]; off += 4
        is_string = data[off]; off += 1
        value = struct.unpack_from(f"{bo}i", data, off)[0]; off += 4
        prop_entries.append((name_off, is_string, value))
    # Pad the props array to a 4-byte boundary
    off += (4 - (nprops * 9) % 4) % 4
    string_size = struct.unpack_from(f"{bo}I", data, off)[0]
    off += 4
    strings_start = off

    def cstr(start: int) -> str:
        end = data.index(b"\x00", start)
        return data[start:end].decode("latin-1", errors="replace")

    result: dict[str, str | int] = {}
    for name_off, is_string, value in prop_entries:
        name = cstr(strings_start + name_off)
        result[name] = cstr(strings_start + value) if is_string else value
    return result


def _pcf_glyph_count(data: bytes, toffset: int) -> int:
    """Return glyph count from the METRICS table."""
    fmt_word = struct.unpack_from("<I", data, toffset)[0]
    bo = ">" if (fmt_word & _PCF_BYTE_MASK) else "<"
    compressed = bool(fmt_word & _PCF_COMPRESSED_METRICS)
    off = toffset + 4
    if compressed:
        return struct.unpack_from(f"{bo}H", data, off)[0]
    return struct.unpack_from(f"{bo}I", data, off)[0]


def _parse_pcf(path: Path, content_hash: str) -> ParsedFont:
    data = path.read_bytes()
    magic, ntables = struct.unpack_from("<II", data, 0)
    if magic != _PCF_MAGIC:
        raise ValueError(f"not a PCF file: {magic:#010x}")

    tables: dict[int, tuple[int, int, int]] = {}
    for i in range(ntables):
        ttype, tformat, tsize, toffset = struct.unpack_from("<IIII", data, 8 + i * 16)
        tables[ttype] = (tformat, tsize, toffset)

    props: dict[str, str | int] = {}
    if _PCF_PROPERTIES_TYPE in tables:
        props = _pcf_read_props(data, tables[_PCF_PROPERTIES_TYPE][2])

    glyph_count = 0
    if _PCF_METRICS_TYPE in tables:
        glyph_count = _pcf_glyph_count(data, tables[_PCF_METRICS_TYPE][2])

    family_name = str(props.get("FAMILY_NAME") or path.stem)
    foundry = str(props["FOUNDRY"]) if "FOUNDRY" in props else None
    weight_str = str(props.get("WEIGHT_NAME") or "")
    slant = str(props.get("SLANT") or "R")
    version = str(props["FONT_VERSION"]) if "FONT_VERSION" in props else None
    license_text = str(props["COPYRIGHT"]) if "COPYRIGHT" in props else None
    weight_num = _T1_WEIGHT_NUMERIC.get(weight_str.lower())
    style = _bdf_style(weight_str, slant)

    return ParsedFont(
        family_name=family_name,
        foundry=foundry,
        style=style,
        weight=weight_num,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format="pcf",
        content_hash=content_hash,
        version=version,
        license=license_text,
        glyph_count=glyph_count,
        glyphs=[],  # BITMAPS table parsing is a separate project; count is from METRICS
        metadata_complete=True,
    )


def _t1_style(family: str, fullname: str | None, weight_str: str, italic_angle: float) -> str:
    style = ""
    if fullname:
        style = fullname.replace(family, "").strip(" -")
    if not style:
        ws_lower = weight_str.lower()
        style = "Regular" if ws_lower in _T1_REGULAR_WEIGHTS else (weight_str or "Regular")
    if italic_angle and "italic" not in style.lower():
        style = (style + " Italic").strip()
    return style or "Regular"


def _t1_advance_width(glyph) -> int | None:
    try:
        glyph.decompile()
        prog = glyph.program
        for i, tok in enumerate(prog):
            if tok == "hsbw" and i >= 2:
                return int(prog[i - 1])
            if tok == "sbw" and i >= 4:
                return int(prog[i - 2])
    except Exception:
        pass
    return None


def _parse_type1_glyphs(t1font: T1Font) -> tuple[list[ParsedGlyph], int]:
    enc = t1font.font.get("Encoding", [])
    reverse_enc: dict[str, int] = {}
    if isinstance(enc, list):
        for idx, name in enumerate(enc):
            if name and name != ".notdef" and name not in reverse_enc:
                reverse_enc[name] = idx

    glyphs: list[ParsedGlyph] = []
    glyph_set = t1font.getGlyphSet()
    for glyph_name, glyph_obj in glyph_set.items():
        try:
            pen = RecordingPen()
            glyph_obj.draw(pen)
            contour_count = sum(1 for op, _ in pen.value if op == "moveTo")
            outline_hash = hashlib.sha256(repr(pen.value).encode()).hexdigest()
            advance = _t1_advance_width(glyph_obj)
            codepoint = reverse_enc.get(glyph_name)
        except Exception:
            continue
        glyphs.append(
            ParsedGlyph(
                glyph_name=glyph_name,
                unicode_codepoint=codepoint,
                contour_count=contour_count,
                advance_width=advance,
                outline_hash=outline_hash,
            )
        )
    return glyphs, len(glyph_set)


def _parse_type1(path: Path, content_hash: str) -> ParsedFont:
    t1 = T1Font(str(path))
    t1.parse()
    fi = t1.font.get("FontInfo", {})

    family_name = fi.get("FamilyName") or path.stem
    full_name = fi.get("FullName")
    weight_str = fi.get("Weight") or ""
    italic_angle = fi.get("ItalicAngle") or 0
    style = _t1_style(family_name, full_name, weight_str, italic_angle)
    weight_num = _T1_WEIGHT_NUMERIC.get(weight_str.lower())
    version = fi.get("version") or fi.get("Version")
    if version:
        version = version.split(";")[0].strip()
    license_text = fi.get("Notice")

    glyphs, total = _parse_type1_glyphs(t1)

    return ParsedFont(
        family_name=family_name,
        foundry=None,
        style=style,
        weight=weight_num,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format=path.suffix.lower().lstrip("."),
        content_hash=content_hash,
        version=version,
        license=license_text,
        glyph_count=total,
        glyphs=glyphs,
        metadata_complete=True,
    )


_FON_NE_MAGIC = b"NE"
_FON_RT_FONT = 0x8008  # NE standard resource type for FONT


def _fon_style(weight: int, italic: bool) -> str:
    if weight >= 700:
        base = "Bold"
    elif weight >= 500:
        base = "Medium"
    elif 0 < weight < 400:
        base = "Light"
    else:
        base = "Regular"
    if italic:
        return (base.replace("Regular", "").strip() + " Italic").strip() or "Italic"
    return base


def _fnt_info(data: bytes, fnt_off: int) -> dict:
    italic = bool(data[fnt_off + 0x50])
    weight = struct.unpack_from("<H", data, fnt_off + 0x53)[0]
    first_char = data[fnt_off + 0x5F]
    last_char = data[fnt_off + 0x60]
    copyright = (
        data[fnt_off + 6 : fnt_off + 66].split(b"\x00")[0]
        .decode("latin-1", errors="replace")
        .strip()
    )
    dfFace = struct.unpack_from("<I", data, fnt_off + 0x69)[0]
    face_end = data.index(b"\x00", fnt_off + dfFace)
    face = data[fnt_off + dfFace : face_end].decode("latin-1", errors="replace")
    return {
        "face": face,
        "weight": weight,
        "italic": italic,
        "glyph_count": max(0, last_char - first_char + 1),
        "copyright": copyright or None,
    }


def _parse_fon(path: Path, content_hash: str) -> ParsedFont:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("not an MZ executable")
    ne_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[ne_off : ne_off + 2] != _FON_NE_MAGIC:
        raise ValueError("not an NE executable — PE FON not supported")

    res_tab_rel = struct.unpack_from("<H", data, ne_off + 0x24)[0]
    off = ne_off + res_tab_rel
    align_shift = struct.unpack_from("<H", data, off)[0]
    off += 2

    fnt_offsets: list[int] = []
    while True:
        rtype = struct.unpack_from("<H", data, off)[0]
        if rtype == 0:
            break
        rcount = struct.unpack_from("<H", data, off + 2)[0]
        off += 8
        for _ in range(rcount):
            roff, rlen = struct.unpack_from("<HH", data, off)
            off += 12
            if rtype == _FON_RT_FONT:
                fnt_offsets.append(roff << align_shift)

    if not fnt_offsets:
        raise ValueError("no FONT resources in FON file")

    infos = [_fnt_info(data, fo) for fo in fnt_offsets]
    first = infos[0]
    # Use the longest non-empty copyright string across all embedded sizes.
    license_text = max(
        (i["copyright"] for i in infos if i["copyright"]), key=len, default=None
    )
    glyph_count = max(i["glyph_count"] for i in infos)

    return ParsedFont(
        family_name=first["face"] or path.stem,
        foundry=None,
        style=_fon_style(first["weight"], first["italic"]),
        weight=first["weight"] or None,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format="fon",
        content_hash=content_hash,
        version=None,
        license=license_text,
        glyph_count=glyph_count,
        glyphs=[],
        metadata_complete=True,
    )


def _parse_unsupported(path: Path, content_hash: str) -> ParsedFont:
    return ParsedFont(
        family_name=path.stem,
        foundry=None,
        style=None,
        weight=None,
        width=None,
        is_variable=False,
        axes=None,
        path=path,
        filename=path.name,
        format=path.suffix.lower().lstrip("."),
        content_hash=content_hash,
        version=None,
        license=None,
        glyph_count=0,
        glyphs=[],
        metadata_complete=False,
    )


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_glyphs(font: TTFont) -> list[ParsedGlyph]:
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"].metrics if "hmtx" in font else {}
    reverse_cmap: dict[str, set[int]] = font["cmap"].buildReversed() if "cmap" in font else {}

    glyphs = []
    for glyph_name in font.getGlyphOrder():
        pen = RecordingPen()
        glyph_set[glyph_name].draw(pen)
        contour_count = sum(1 for op, _ in pen.value if op == "moveTo")
        outline_hash = hashlib.sha256(repr(pen.value).encode("utf-8")).hexdigest()
        advance_width = hmtx[glyph_name][0] if glyph_name in hmtx else None
        codepoints = reverse_cmap.get(glyph_name)
        unicode_codepoint = min(codepoints) if codepoints else None
        glyphs.append(
            ParsedGlyph(
                glyph_name=glyph_name,
                unicode_codepoint=unicode_codepoint,
                contour_count=contour_count,
                advance_width=advance_width,
                outline_hash=outline_hash,
            )
        )
    return glyphs


def parse_font_file(path: str | Path) -> ParsedFont:
    path = Path(path)
    content_hash = _hash_file(path)
    fmt = path.suffix.lower().lstrip(".")

    if fmt in _T1_FORMATS:
        return _parse_type1(path, content_hash)
    if fmt in _BDF_FORMATS:
        return _parse_bdf(path, content_hash)
    if fmt in _PCF_FORMATS:
        return _parse_pcf(path, content_hash)
    if fmt in _FON_FORMATS:
        return _parse_fon(path, content_hash)
    if fmt not in _SFNT_FORMATS:
        return _parse_unsupported(path, content_hash)

    with TTFont(path, lazy=True) as font:
        name_table = font["name"]
        family_name = name_table.getBestFamilyName() or path.stem
        foundry = name_table.getDebugName(8)  # nameID 8: Manufacturer
        style = name_table.getBestSubFamilyName()
        version = name_table.getDebugName(5)
        license_desc = name_table.getDebugName(13)

        weight = None
        width = None
        family_class = None
        panose_class = None
        if "OS/2" in font:
            os2 = font["OS/2"]
            weight = getattr(os2, "usWeightClass", None)
            width = _WIDTH_CLASSES.get(getattr(os2, "usWidthClass", None))
            class_id = getattr(os2, "sFamilyClass", 0) >> 8
            family_class = _FAMILY_CLASSES.get(class_id)
            panose = getattr(os2, "panose", None)
            if panose is not None:
                panose_bytes = (
                    panose.bFamilyType, panose.bSerifStyle, panose.bWeight,
                    panose.bProportion, panose.bContrast, panose.bStrokeVariation,
                    panose.bArmStyle, panose.bLetterForm, panose.bMidline, panose.bXHeight,
                )
                panose_class = classify_panose(panose_bytes)

        is_variable = "fvar" in font
        axes = None
        if is_variable:
            axes = {axis.axisTag: [axis.minValue, axis.maxValue] for axis in font["fvar"].axes}

        glyphs = _parse_glyphs(font)

    return ParsedFont(
        family_name=family_name,
        foundry=foundry,
        style=style,
        weight=weight,
        width=width,
        is_variable=is_variable,
        axes=axes,
        path=path,
        filename=path.name,
        format=fmt,
        content_hash=content_hash,
        version=version,
        license=license_desc,
        glyph_count=len(glyphs),
        glyphs=glyphs,
        family_class=family_class,
        panose_class=panose_class,
    )
