from __future__ import annotations

import sqlite3

# Substring signatures checked against the raw license text (name table
# nameID 13). Fonts don't embed a structured license enum, just free text
# (or nothing at all) — keyword matching, same "cheap, not NLP" spirit as
# search/smart collections.
#
# Deliberately NOT included: "All Rights Reserved" as a signal for
# Commercial/Proprietary. Caught on real-hardware testing with DejaVu Sans
# (Bitstream Vera license) — that phrase is standard copyright-ownership
# boilerplate that shows up in plenty of fully permissive licenses too
# ("Copyright (c) ... All Rights Reserved" followed by a broad grant of
# rights). It's a copyright assertion, not a usage restriction — matching
# on it produced a confident, wrong answer for a genuinely free font.
# "Unknown" is the honest fallback when nothing more specific matches.
_LICENSE_SIGNATURES: list[tuple[str, str]] = [
    ("sil open font license", "OFL-1.1"),
    ("apache license", "Apache-2.0"),
    ("ubuntu font licence", "Ubuntu Font License"),
    ("gnu lesser general public license", "LGPL"),
    ("gnu general public license", "GPL"),
    ("mit license", "MIT"),
    ("creative commons", "Creative Commons"),
    ("freeware", "Freeware"),
    ("shareware", "Shareware"),
]


def classify_license(license_text: str | None) -> str | None:
    """None = no license text at all; 'Unknown' = text present but not
    recognized; otherwise the matched category name."""
    if not license_text or not license_text.strip():
        return None
    lowered = license_text.lower()
    for signature, category in _LICENSE_SIGNATURES:
        if signature in lowered:
            return category
    return "Unknown"


def list_license_conflicts(conn: sqlite3.Connection) -> list[dict]:
    """Faces (family+style) whose files disagree on license category —
    e.g. one file under "Arial Regular" classifies as OFL-1.1, another as
    Commercial/Proprietary. Worth a human look: could be a legitimate
    dual-licensed font, or an accidentally mixed-in mismatched file."""
    rows = conn.execute(
        """
        SELECT font_faces.id AS font_face_id, families.name AS family, font_faces.style,
               font_files.path, font_files.license
        FROM font_files
        JOIN font_faces ON font_faces.id = font_files.font_face_id
        JOIN families ON families.id = font_faces.family_id
        ORDER BY families.name COLLATE NOCASE, font_faces.style, font_files.path
        """
    ).fetchall()

    groups: dict[int, list[dict]] = {}
    for row in rows:
        entry = dict(row)
        entry["license_category"] = classify_license(entry["license"])
        groups.setdefault(row["font_face_id"], []).append(entry)

    conflicts = []
    for files in groups.values():
        categories = {f["license_category"] for f in files}
        if len(categories) > 1:
            conflicts.append(
                {
                    "family": files[0]["family"],
                    "style": files[0]["style"],
                    "files": [
                        {"path": f["path"], "license_category": f["license_category"]}
                        for f in files
                    ],
                }
            )
    return conflicts
