from __future__ import annotations

import sqlite3

from glyphmatrix.core.tags import list_tags_for_face

# Buckets built from the same classification tag vocabularies that
# sFamilyClass (parser.py's _FAMILY_CLASSES) and PANOSE (panose.py) already
# auto-apply as tags — no new metadata, just grouping what's already there
# into three broad visual buckets for the classic contrast-pairing rule of
# thumb. "symbolic"/"miscellaneous"/"ornamental" are deliberately left
# unbucketed: they're not body/heading text faces in the pairing sense, and
# guessing a bucket for them would be exactly the kind of overconfident call
# this project avoids (see license classification's "Unknown" precedent).
_SERIF_TAGS = {
    "oldstyle-serif", "transitional-serif", "modern-serif", "clarendon-serif",
    "slab-serif", "freeform-serif",
    "cove", "obtuse-cove", "square-cove", "obtuse-square-cove", "square",
    "thin", "oval", "exaggerated", "triangle",
}
_SANS_TAGS = {
    "sans-serif",
    "normal-sans", "obtuse-sans", "perp-sans", "flared", "rounded",
}
_SCRIPT_TAGS = {
    "script", "hand-written",
}

# The classic pairing rule of thumb, not a hard fact: contrast reads as
# intentional (serif heading + sans body, or a script/display accent against
# a neutral sans), while two faces from the same bucket tend to read as a
# mistake rather than a deliberate choice. Script/decorative faces are
# specifically not paired against serif here — that combination isn't an
# established rule the way serif/sans or script/sans are.
_CONTRASTS = {
    "serif": {"sans"},
    "sans": {"serif", "script"},
    "script": {"sans"},
}


def _bucket_for_tags(tags: list[str]) -> str | None:
    tag_set = set(tags)
    if tag_set & _SERIF_TAGS:
        return "serif"
    if tag_set & _SANS_TAGS:
        return "sans"
    if tag_set & _SCRIPT_TAGS:
        return "script"
    return None


def _reason(source_bucket: str, candidate_bucket: str, source_weight: int | None, candidate_weight: int | None) -> str:
    reason = f"{source_bucket} ↔ {candidate_bucket} contrast"
    if source_weight is not None and candidate_weight is not None:
        reason += f"; weight {candidate_weight} vs your {source_weight}"
    return reason


def suggest_pairings(conn: sqlite3.Connection, source_face_id: int, limit: int = 5) -> dict:
    """Rule-of-thumb pairing suggestions from a face's own classification
    tags and weight — deliberately transparent (every suggestion states its
    reason) rather than a black-box score, since this is the most subjective
    feature in the codebase and the user should be able to judge the rule
    for themselves, not just trust a number."""
    source_tags = list_tags_for_face(conn, source_face_id)
    source_bucket = _bucket_for_tags(source_tags)
    if source_bucket is None:
        return {"source_bucket": None, "suggestions": []}

    source_row = conn.execute(
        "SELECT family_id, weight FROM font_faces WHERE id = ?", (source_face_id,)
    ).fetchone()
    source_family_id = source_row["family_id"]
    source_weight = source_row["weight"]

    target_buckets = _CONTRASTS[source_bucket]
    rows = conn.execute(
        """
        SELECT font_faces.id AS face_id, font_faces.family_id,
               families.name AS family, font_faces.style, font_faces.weight
        FROM font_faces
        JOIN families ON families.id = font_faces.family_id
        WHERE font_faces.family_id != ?
        """,
        (source_family_id,),
    ).fetchall()

    best_per_family: dict[int, dict] = {}
    for row in rows:
        bucket = _bucket_for_tags(list_tags_for_face(conn, row["face_id"]))
        if bucket not in target_buckets:
            continue
        weight = row["weight"]
        weight_diff = abs(weight - source_weight) if weight is not None and source_weight is not None else None
        candidate = {
            "family": row["family"],
            "style": row["style"],
            "weight": weight,
            "bucket": bucket,
            "weight_diff": weight_diff,
        }
        current = best_per_family.get(row["family_id"])
        if current is None or (weight_diff is not None and (current["weight_diff"] is None or weight_diff > current["weight_diff"])):
            best_per_family[row["family_id"]] = candidate

    ranked = sorted(
        best_per_family.values(),
        key=lambda c: (c["weight_diff"] is None, -(c["weight_diff"] or 0), c["family"]),
    )[:limit]

    for candidate in ranked:
        candidate["reason"] = _reason(source_bucket, candidate["bucket"], source_weight, candidate["weight"])

    return {"source_bucket": source_bucket, "suggestions": ranked}
