from __future__ import annotations

import sqlite3

import fontTools.unicodedata as ucd

# Codepoints shared across scripts (digits, punctuation) or combining marks
# that inherit their script from the base character they attach to. Real
# script identities, not gaps — kept distinct from named scripts like "Grek".
_GENERIC_SCRIPT_NAMES = {
    "Zyyy": "Common",
    "Zinh": "Inherited",
    "Zzzz": "Unknown",
}


def _script_name(code: str) -> str:
    return _GENERIC_SCRIPT_NAMES.get(code) or ucd.script_name(code) or code


def script_breakdown(conn: sqlite3.Connection, font_file_id: int) -> list[dict]:
    """Groups this file's mapped glyphs (those with a Unicode codepoint) by
    Unicode script, via fontTools' bundled Unicode Character Database — the
    same "objective metadata, not guessed" approach as sFamilyClass tagging.
    Glyphs without a codepoint (ligatures, unmapped presentation forms) have
    no script and are excluded, same as glyph_summary's mapped_count."""
    rows = conn.execute(
        "SELECT unicode_codepoint FROM font_glyphs "
        "WHERE font_file_id = ? AND unicode_codepoint IS NOT NULL",
        (font_file_id,),
    ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        code = ucd.script(chr(row["unicode_codepoint"]))
        counts[code] = counts.get(code, 0) + 1

    return sorted(
        (
            {"script": code, "name": _script_name(code), "glyph_count": count}
            for code, count in counts.items()
        ),
        key=lambda r: r["glyph_count"],
        reverse=True,
    )


def resolve_script_query(query: str) -> str:
    """Accepts either an ISO 15924 script code (e.g. "Grek") or the script's
    English name (e.g. "Greek", case-insensitive). Raises ValueError if the
    query doesn't match a real Unicode script — deliberately not a fuzzy
    match, since a language name like "Vietnamese" would silently resolve to
    nothing useful (Vietnamese is written in the Latin script, not its own
    script) and a wrong confident answer is worse than a clear error here."""
    generic_by_name = {name.lower(): code for code, name in _GENERIC_SCRIPT_NAMES.items()}
    if query.lower() in generic_by_name:
        return generic_by_name[query.lower()]
    if len(query) == 4 and query.title() in ucd.Scripts.NAMES:
        return query.title()
    try:
        return ucd.script_code(query)
    except KeyError:
        raise ValueError(
            f"unrecognized script: {query!r} (use an ISO 15924 code like 'Grek' "
            "or a script name like 'Greek' — not a language name)"
        )


def check_script(conn: sqlite3.Connection, font_file_id: int, query: str) -> dict:
    code = resolve_script_query(query)
    breakdown = script_breakdown(conn, font_file_id)
    match = next((r for r in breakdown if r["script"] == code), None)
    glyph_count = match["glyph_count"] if match else 0
    return {
        "script": code,
        "name": _script_name(code),
        "supported": glyph_count > 0,
        "glyph_count": glyph_count,
    }
