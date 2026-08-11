import pytest

from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.query import find_face_id
from glyphmatrix.core.smart_collections import evaluate_smart_query
from glyphmatrix.core.tags import add_tags

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def _seed(conn, tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular.ttf",
        family="Arial",
        style="Regular",
        manufacturer="Monotype",
        family_class=8 * 256 + 1,  # sans-serif
    )
    build_test_font(
        tmp_path / "Garamond-Regular.ttf",
        family="Garamond",
        style="Regular",
        manufacturer="Adobe",
        family_class=1 * 256,  # oldstyle-serif
    )
    ingest_directory(conn, tmp_path)


def test_field_term_matches(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "foundry:Monotype")

    assert [r["family"] for r in results] == ["Arial"]


def test_field_term_is_case_and_substring_tolerant(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "foundry:mono")

    assert [r["family"] for r in results] == ["Arial"]


def test_tag_term_matches_auto_classification(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "tag:sans-serif")

    assert [r["family"] for r in results] == ["Arial"]


def test_implicit_and_between_terms(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "family:Arial style:Regular")
    assert [r["family"] for r in results] == ["Arial"]

    no_match = evaluate_smart_query(conn, "family:Arial style:Bold")
    assert no_match == []


def test_or_between_groups(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "tag:sans-serif OR tag:oldstyle-serif")

    assert {r["family"] for r in results} == {"Arial", "Garamond"}


def test_or_is_case_insensitive(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "foundry:Monotype or foundry:Adobe")

    assert {r["family"] for r in results} == {"Arial", "Garamond"}


def test_bare_word_matches_family_style_foundry_or_tag(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)
    face_id = find_face_id(conn, "Garamond", "Regular")
    add_tags(conn, face_id, ["elegant"])

    assert [r["family"] for r in evaluate_smart_query(conn, "garamond")] == ["Garamond"]
    assert [r["family"] for r in evaluate_smart_query(conn, "elegant")] == ["Garamond"]


def test_weight_field_matches_numerically(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    results = evaluate_smart_query(conn, "weight:400")

    assert {r["family"] for r in results} == {"Arial", "Garamond"}


def test_weight_field_rejects_non_numeric_value(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    with pytest.raises(ValueError):
        evaluate_smart_query(conn, "weight:bold")


def test_unknown_field_raises(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    with pytest.raises(ValueError):
        evaluate_smart_query(conn, "nonsense:value")


def test_empty_query_raises():
    conn = _conn()
    with pytest.raises(ValueError):
        evaluate_smart_query(conn, "   ")


def test_no_matches_returns_empty_list(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    assert evaluate_smart_query(conn, "foundry:NoSuchFoundry") == []


def test_results_deduplicated_and_sorted(tmp_path):
    conn = _conn()
    _seed(conn, tmp_path)

    # both groups match Arial; it must appear once, sorted before Garamond
    results = evaluate_smart_query(conn, "family:Arial OR tag:sans-serif OR foundry:Adobe")

    families = [r["family"] for r in results]
    assert families == ["Arial", "Garamond"]
