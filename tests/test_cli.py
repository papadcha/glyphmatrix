import json

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl

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
