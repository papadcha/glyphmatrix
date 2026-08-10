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
