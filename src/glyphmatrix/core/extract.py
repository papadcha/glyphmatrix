"""Pull the individual fonts out of a collection file.

- .ttc / .otc: the members of a TrueType/OpenType collection. Each is saved as
  a standalone font; tables are copied as they are (no re-compilation, no new
  timestamp), so the same member always gives the same bytes.
- .dfont: a Mac resource-fork file whose 'sfnt' resources are plain fonts.
  fontTools does not read these reliably, so the resource map is read here.

Nothing is written to disk by this module: callers get bytes.
"""
from __future__ import annotations

import io
import struct
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

COLLECTION_EXTENSIONS = (".ttc", ".otc", ".dfont")


def is_collection_file(path: Path) -> bool:
    """A collection by its content, not its name: a .dfont, or anything that starts
    with the 'ttcf' signature (collections exist named .ttf, e.g. PingFang_1.ttf)."""
    if path.suffix.lower() == ".dfont":
        return True
    if path.suffix.lower() in (".ttc", ".otc"):
        return True
    try:
        with path.open("rb") as fh:
            return fh.read(4) == b"ttcf"
    except OSError:
        return False


def collection_extension(path: Path) -> str:
    """The extension a collection should carry: its own if that is honest, else .ttc."""
    ext = path.suffix.lower()
    return ext if ext in COLLECTION_EXTENSIONS else ".ttc"


def _dfont_sfnts(data: bytes) -> list[bytes]:
    """The 'sfnt' resources of a .dfont, in file order."""
    if len(data) < 16:
        raise ValueError("too short for a resource fork")
    data_off, map_off, _data_len, map_len = struct.unpack(">4L", data[:16])
    rmap = data[map_off:map_off + map_len]
    if len(rmap) < 30:
        raise ValueError("resource map missing")
    type_list_off = struct.unpack(">H", rmap[24:26])[0]
    (type_count,) = struct.unpack(">h", rmap[type_list_off:type_list_off + 2])
    fonts: list[bytes] = []
    for i in range(type_count + 1):
        start = type_list_off + 2 + i * 8
        rtype, count_minus_1, ref_off = struct.unpack(">4shH", rmap[start:start + 8])
        if rtype != b"sfnt":
            continue
        for j in range(count_minus_1 + 1):
            ref = rmap[type_list_off + ref_off + j * 12:type_list_off + ref_off + (j + 1) * 12]
            (offset,) = struct.unpack(">I", ref[4:8])
            pos = data_off + (offset & 0xFFFFFF)
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            blob = data[pos + 4:pos + 4 + length]
            if len(blob) != length:
                raise ValueError("truncated sfnt resource")
            fonts.append(blob)
    return fonts


def member_count(path: Path) -> int:
    if path.suffix.lower() == ".dfont":
        return len(_dfont_sfnts(path.read_bytes()))
    collection = TTCollection(path, lazy=True)
    try:
        return len(collection.fonts)
    finally:
        collection.close()


def extract_member(path: Path, index: int) -> bytes:
    """The font number `index` of a collection, as the bytes of a standalone font."""
    if path.suffix.lower() == ".dfont":
        return _dfont_sfnts(path.read_bytes())[index]
    font = TTFont(path, fontNumber=index, lazy=True, recalcTimestamp=False)
    try:
        buffer = io.BytesIO()
        font.save(buffer)
        return buffer.getvalue()
    finally:
        font.close()


def member_extension(data: bytes) -> str:
    """'.otf' for CFF outlines, '.ttf' otherwise."""
    return ".otf" if data[:4] == b"OTTO" else ".ttf"
