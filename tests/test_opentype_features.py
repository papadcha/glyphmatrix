from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.opentype_features import list_features
from glyphmatrix.core.query import find_face_id, find_first_font_file_for_face

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _ingested_font_file(conn, tmp_path, **kwargs):
    build_test_font(tmp_path / "test.ttf", **kwargs)
    ingest_directory(conn, tmp_path)
    face_id = find_face_id(conn, kwargs.get("family", "Test Sans"), kwargs.get("style", "Regular"))
    return find_first_font_file_for_face(conn, face_id)


def test_no_features_when_no_gsub_gpos(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(conn, tmp_path)

    assert list_features(font_file["path"]) == []


def test_lists_gsub_feature(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(
        conn, tmp_path, extra_glyph=True,
        opentype_features="feature smcp { sub A by B; } smcp;",
    )

    result = list_features(font_file["path"])

    assert result == [{"tag": "smcp", "name": "Small Capitals", "tables": ["GSUB"]}]


def test_lists_gpos_feature(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(
        conn, tmp_path, extra_glyph=True,
        opentype_features="feature kern { pos A B -20; } kern;",
    )

    result = list_features(font_file["path"])

    assert result == [{"tag": "kern", "name": "Kerning", "tables": ["GPOS"]}]


def test_feature_in_both_tables_merges_into_one_row(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(
        conn, tmp_path, extra_glyph=True,
        opentype_features=(
            "feature locl { sub A by B; } locl;\n"
            "feature locl { pos A B -10; } locl;\n"
        ),
    )

    result = list_features(font_file["path"])

    assert result == [{"tag": "locl", "name": "Localized Forms", "tables": ["GPOS", "GSUB"]}]


def test_stylistic_set_and_character_variant_names(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(
        conn, tmp_path, extra_glyph=True,
        opentype_features=(
            "feature ss03 { sub A by B; } ss03;\n"
            "feature cv07 { sub B by A; } cv07;\n"
        ),
    )

    result = list_features(font_file["path"])

    names = {row["tag"]: row["name"] for row in result}
    assert names == {"ss03": "Stylistic Set 3", "cv07": "Character Variant 7"}


def test_unrecognized_tag_falls_back_to_raw_tag(tmp_path):
    conn = _conn()
    font_file = _ingested_font_file(
        conn, tmp_path, extra_glyph=True,
        opentype_features="feature zzzz { sub A by B; } zzzz;",
    )

    result = list_features(font_file["path"])

    assert result == [{"tag": "zzzz", "name": "zzzz", "tables": ["GSUB"]}]
