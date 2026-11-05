"""Build minimal NE-format Windows .fon files for parser tests."""
from __future__ import annotations

import struct
from pathlib import Path


def _fnt(face: str, copyright: str, pix_width: int, pix_height: int, charset: int, weight: int) -> bytes:
    header = bytearray(0x76)
    struct.pack_into("<H", header, 0x00, 0x200)  # dfVersion 2.0
    header[6:66] = copyright.encode("latin-1")[:60].ljust(60, b"\x00")
    struct.pack_into("<HHHH", header, 0x42, 0, 9, 96, 96)  # type, points, vert/horiz res
    struct.pack_into("<H", header, 0x53, weight)
    header[0x55] = charset
    struct.pack_into("<HH", header, 0x56, pix_width, pix_height)
    struct.pack_into("<H", header, 0x5B, pix_width)
    header[0x5F] = 0x20  # first char
    header[0x60] = 0x7E  # last char
    struct.pack_into("<I", header, 0x69, len(header))  # dfFace → right after the header
    struct.pack_into("<I", header, 0x02, len(header) + len(face) + 1)
    return bytes(header) + face.encode("latin-1") + b"\x00"


def build_test_fon(
    out_path: str | Path,
    face: str = "Test Raster",
    copyright: str = "Copyright (C) Acme Type 1991-1993. All rights reserved.",
    description: str = "FONTRES 100,96,96:Test Raster 8x12",
    sizes: tuple[tuple[int, int], ...] = ((8, 12), (6, 8)),
    charset: int = 255,
    weight: int = 400,
) -> Path:
    mz = bytearray(0x40)
    mz[0:2] = b"MZ"
    ne_off = 0x40
    struct.pack_into("<I", mz, 0x3C, ne_off)

    ne = bytearray(0x40)
    ne[0:2] = b"NE"
    res_table_rel = len(ne)
    resource_table = bytearray(struct.pack("<H", 0))  # alignment shift 0
    resource_table += struct.pack("<HHI", 0x8008, len(sizes), 0)
    entries_at = len(resource_table)
    resource_table += bytes(12 * len(sizes))
    resource_table += struct.pack("<H", 0)

    nonres = bytes([len(description)]) + description.encode("latin-1") + b"\x00"
    fnts = [_fnt(face, copyright, w, h, charset, weight) for w, h in sizes]

    nonres_off = ne_off + len(ne) + len(resource_table)
    data_off = nonres_off + len(nonres)
    offset = data_off
    for i, fnt in enumerate(fnts):
        struct.pack_into("<HH", resource_table, entries_at + 12 * i, offset, len(fnt))
        offset += len(fnt)

    struct.pack_into("<H", ne, 0x20, len(nonres))
    struct.pack_into("<H", ne, 0x24, res_table_rel)
    struct.pack_into("<I", ne, 0x2C, nonres_off)

    out_path = Path(out_path)
    out_path.write_bytes(bytes(mz) + bytes(ne) + bytes(resource_table) + nonres + b"".join(fnts))
    return out_path
