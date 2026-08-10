import json
import shutil

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl

from .fakes import FakeActivationProvider
from .fontbuilder import build_test_font


def test_fontctl_scan_plain_output(tmp_path):
    (tmp_path / "font").mkdir()
    build_test_font(tmp_path / "font" / "Arial-Regular.ttf", family="Arial", style="Regular")
    db_path = tmp_path / "library.db"
    runner = CliRunner()

    result = runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "scanned 1" in result.output
    assert "added 1" in result.output
    assert db_path.exists()


def test_fontctl_scan_json_output(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    db_path = tmp_path / "library.db"
    runner = CliRunner()

    result = runner.invoke(fontctl, ["--db", str(db_path), "scan", "--json", str(tmp_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["files_scanned"] == 1
    assert payload["files_added"] == 1


def _scanned_db(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])
    return runner, db_path


def test_fontctl_list_plain_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "list"])

    assert result.exit_code == 0, result.output
    assert "Arial" in result.output
    assert "Regular" in result.output
    assert "Bold" in result.output


def test_fontctl_list_json_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 2
    assert {row["style"] for row in payload} == {"Regular", "Bold"}


def test_fontctl_list_empty_library(tmp_path):
    db_path = tmp_path / "library.db"
    runner = CliRunner()

    result = runner.invoke(fontctl, ["--db", str(db_path), "list"])

    assert result.exit_code == 0, result.output
    assert "no fonts" in result.output


def test_fontctl_info_plain_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "info", "arial"])

    assert result.exit_code == 0, result.output
    assert "Arial" in result.output
    assert "Arial-Regular.ttf" in result.output
    assert "Arial-Bold.ttf" in result.output


def test_fontctl_info_json_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "info", "--json", "Arial"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["family"] == "Arial"
    assert len(payload["faces"]) == 2


def test_fontctl_info_unknown_family_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "info", "Nonexistent"])

    assert result.exit_code != 0
    assert "no such family" in result.output


def _scanned_db_with_versions(tmp_path):
    build_test_font(
        tmp_path / "Arial-Regular-v1.ttf",
        family="Arial",
        style="Regular",
        version="1.000",
        a_glyph_size=500,
    )
    build_test_font(
        tmp_path / "Arial-Regular-v4.ttf",
        family="Arial",
        style="Regular",
        version="4.000",
        a_glyph_size=500,
        extra_glyph=True,
    )
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])
    return runner, db_path


def test_fontctl_compare_plain_output(tmp_path):
    runner, db_path = _scanned_db_with_versions(tmp_path)

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "compare", "Arial", "Regular", "1.000", "4.000"]
    )

    assert result.exit_code == 0, result.output
    assert "only in 4.000 (1): B" in result.output
    assert "unchanged: 2" in result.output


def test_fontctl_compare_json_output(tmp_path):
    runner, db_path = _scanned_db_with_versions(tmp_path)

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "compare", "--json", "Arial", "Regular", "1.000", "4.000"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["only_in_b"] == ["B"]
    assert payload["unchanged_count"] == 2


def test_fontctl_compare_unknown_version_errors(tmp_path):
    runner, db_path = _scanned_db_with_versions(tmp_path)

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "compare", "Arial", "Regular", "1.000", "9.999"]
    )

    assert result.exit_code != 0
    assert "9.999" in result.output
    assert "1.000" in result.output  # listed as an available version


def test_fontctl_validate_plain_output_clean_library(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "validate"])

    assert result.exit_code == 0, result.output
    assert "checked 2" in result.output
    assert "open issues 0" in result.output


def test_fontctl_validate_flags_and_reports_missing_file(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])
    (tmp_path / "Arial-Regular.ttf").unlink()

    result = runner.invoke(fontctl, ["--db", str(db_path), "validate"])

    assert result.exit_code == 0, result.output
    assert "new issues 1" in result.output
    assert "missing_file" in result.output


def test_fontctl_validate_json_output(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])
    (tmp_path / "Arial-Regular.ttf").write_bytes(b"garbage")

    result = runner.invoke(fontctl, ["--db", str(db_path), "validate", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["issues_opened"] == 1
    assert payload["open_issues"][0]["issue_type"] == "corrupt"


def test_fontctl_duplicates_plain_output(tmp_path):
    original = tmp_path / "Arial-Regular.ttf"
    build_test_font(original, family="Arial", style="Regular")
    shutil.copy(original, tmp_path / "Arial-Regular-copy.ttf")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])

    result = runner.invoke(fontctl, ["--db", str(db_path), "duplicates"])

    assert result.exit_code == 0, result.output
    assert "2 copies" in result.output
    assert "Arial-Regular.ttf" in result.output
    assert "Arial-Regular-copy.ttf" in result.output


def test_fontctl_duplicates_none_found(tmp_path):
    runner, db_path = _scanned_db(tmp_path)  # Arial Regular + Bold, no dupes

    result = runner.invoke(fontctl, ["--db", str(db_path), "duplicates"])

    assert result.exit_code == 0, result.output
    assert "no duplicate files found" in result.output


def test_fontctl_duplicates_json_output(tmp_path):
    original = tmp_path / "Arial-Regular.ttf"
    build_test_font(original, family="Arial", style="Regular")
    shutil.copy(original, tmp_path / "Arial-Regular-copy.ttf")
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])

    result = runner.invoke(fontctl, ["--db", str(db_path), "duplicates", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert len(payload[0]["files"]) == 2


def test_fontctl_activate_plain_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])

    assert result.exit_code == 0, result.output
    assert "activated 2 file(s) for Arial" in result.output


def test_fontctl_activate_json_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "--json", "Arial"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["processed"]) == 2
    assert payload["errors"] == []


def test_fontctl_activate_unknown_family_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "Nonexistent"])

    assert result.exit_code != 0
    assert "no such family" in result.output


def test_fontctl_deactivate_plain_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "deactivate", "Arial"])

    assert result.exit_code == 0, result.output
    assert "deactivated 2 file(s) for Arial" in result.output


def test_fontctl_tag_add_and_list_for_face(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    add_result = runner.invoke(
        fontctl, ["--db", str(db_path), "tag", "add", "Arial", "Regular", "sans", "grotesque"]
    )
    assert add_result.exit_code == 0, add_result.output
    assert "sans, grotesque" in add_result.output

    list_result = runner.invoke(fontctl, ["--db", str(db_path), "tag", "list", "Arial", "Regular"])
    assert list_result.exit_code == 0, list_result.output
    assert "sans" in list_result.output
    assert "grotesque" in list_result.output


def test_fontctl_tag_add_unknown_face_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "tag", "add", "Nope", "Regular", "sans"])

    assert result.exit_code != 0
    assert "no such face" in result.output


def test_fontctl_tag_remove(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "tag", "add", "Arial", "Regular", "sans"])

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "tag", "remove", "Arial", "Regular", "sans"]
    )

    assert result.exit_code == 0, result.output
    assert "removed tag 'sans'" in result.output


def test_fontctl_tag_list_all(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "tag", "add", "Arial", "Regular", "sans"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "tag", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [{"name": "sans", "face_count": 1}]


def test_fontctl_tag_find(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "tag", "add", "Arial", "Regular", "sans"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "tag", "find", "sans"])

    assert result.exit_code == 0, result.output
    assert "Arial Regular" in result.output


def test_fontctl_collection_create_add_show(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    create_result = runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Favorites"])
    assert create_result.exit_code == 0, create_result.output

    add_result = runner.invoke(
        fontctl, ["--db", str(db_path), "collection", "add", "Favorites", "Arial", "Regular"]
    )
    assert add_result.exit_code == 0, add_result.output
    assert "added Arial Regular to 'Favorites'" in add_result.output

    show_result = runner.invoke(fontctl, ["--db", str(db_path), "collection", "show", "Favorites"])
    assert show_result.exit_code == 0, show_result.output
    assert "Arial Regular" in show_result.output


def test_fontctl_collection_create_duplicate_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Favorites"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Favorites"])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_fontctl_collection_list(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Favorites"])
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "add", "Favorites", "Arial", "Regular"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "collection", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [{"name": "Favorites", "parent_name": None, "face_count": 1}]


def test_fontctl_collection_remove(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Favorites"])
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "add", "Favorites", "Arial", "Regular"])

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "collection", "remove", "Favorites", "Arial", "Regular"]
    )

    assert result.exit_code == 0, result.output
    assert "removed Arial Regular from 'Favorites'" in result.output
