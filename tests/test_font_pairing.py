from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.font_pairing import suggest_pairings
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id

from .fontbuilder import build_test_font

# sFamilyClass byte packs high byte = class id, per parser.py's _FAMILY_CLASSES
_SANS = 8 * 256      # sans-serif
_SERIF = 1 * 256     # oldstyle-serif
_SCRIPT = 10 * 256   # script


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _face_id(conn, family, style):
    return find_face_id(conn, family, style)


def test_suggests_serif_for_sans_source(tmp_path):
    build_test_font(tmp_path / "a.ttf", family="Body Sans", style="Regular", family_class=_SANS, weight=400)
    build_test_font(tmp_path / "b.ttf", family="Heading Serif", style="Bold", family_class=_SERIF, weight=700)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Body Sans", "Regular"))

    assert result["source_bucket"] == "sans"
    assert len(result["suggestions"]) == 1
    suggestion = result["suggestions"][0]
    assert suggestion["family"] == "Heading Serif"
    assert suggestion["bucket"] == "serif"
    assert "contrast" in suggestion["reason"]


def test_suggests_sans_for_script_source(tmp_path):
    build_test_font(tmp_path / "a.ttf", family="Fancy Script", style="Regular", family_class=_SCRIPT, weight=400)
    build_test_font(tmp_path / "b.ttf", family="Neutral Sans", style="Regular", family_class=_SANS, weight=400)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Fancy Script", "Regular"))

    assert result["source_bucket"] == "script"
    assert [s["family"] for s in result["suggestions"]] == ["Neutral Sans"]


def test_script_does_not_pair_with_serif(tmp_path):
    build_test_font(tmp_path / "a.ttf", family="Fancy Script", style="Regular", family_class=_SCRIPT, weight=400)
    build_test_font(tmp_path / "b.ttf", family="Old Serif", style="Regular", family_class=_SERIF, weight=400)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Fancy Script", "Regular"))

    assert result["suggestions"] == []


def test_no_bucket_when_source_unclassified(tmp_path):
    build_test_font(tmp_path / "a.ttf", family="Mystery", style="Regular")  # no family_class
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Mystery", "Regular"))

    assert result == {"source_bucket": None, "suggestions": []}


def test_excludes_same_family_from_suggestions(tmp_path):
    build_test_font(tmp_path / "a.ttf", family="Body Sans", style="Regular", family_class=_SANS, weight=400)
    build_test_font(tmp_path / "b.ttf", family="Body Sans", style="Bold", family_class=_SERIF, weight=700)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Body Sans", "Regular"))

    assert result["suggestions"] == []  # only contrasting candidate is its own family


def test_ranks_by_largest_weight_contrast_and_limits(tmp_path):
    build_test_font(tmp_path / "src.ttf", family="Body Sans", style="Regular", family_class=_SANS, weight=400)
    build_test_font(tmp_path / "close.ttf", family="Close Serif", style="Regular", family_class=_SERIF, weight=450)
    build_test_font(tmp_path / "far.ttf", family="Far Serif", style="Black", family_class=_SERIF, weight=900)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Body Sans", "Regular"), limit=1)

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["family"] == "Far Serif"


def test_one_suggestion_per_family_picks_best_weight_contrast(tmp_path):
    build_test_font(tmp_path / "src.ttf", family="Body Sans", style="Regular", family_class=_SANS, weight=400)
    build_test_font(tmp_path / "serif_reg.ttf", family="A Serif", style="Regular", family_class=_SERIF, weight=420)
    build_test_font(tmp_path / "serif_black.ttf", family="A Serif", style="Black", family_class=_SERIF, weight=900)
    conn = _conn()
    ingest_directory(conn, tmp_path)

    result = suggest_pairings(conn, _face_id(conn, "Body Sans", "Regular"))

    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["style"] == "Black"
