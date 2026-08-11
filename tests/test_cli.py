import json
import shutil
from datetime import datetime, timedelta, timezone

from click.testing import CliRunner

from glyphmatrix.cli.main import fontctl
from glyphmatrix.core.database import connect

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


def test_fontctl_info_shows_available_state_by_default(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "info", "--json", "Arial"])

    payload = json.loads(result.output)
    states = {f["activation_state"] for face in payload["faces"] for f in face["files"]}
    assert states == {"available"}
    assert "[available]" in runner.invoke(
        fontctl, ["--db", str(db_path), "info", "Arial"]
    ).output


def test_fontctl_info_shows_active_state_after_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "info", "--json", "Arial"])

    payload = json.loads(result.output)
    states = {f["activation_state"] for face in payload["faces"] for f in face["files"]}
    assert states == {"active"}


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


def test_fontctl_conflicts_plain_output(tmp_path):
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    build_test_font(folder_a / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=700)
    build_test_font(folder_b / "Arial-Alt.ttf", family="Arial", style="Regular", a_glyph_size=500)
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])

    result = runner.invoke(fontctl, ["--db", str(db_path), "conflicts"])

    assert result.exit_code == 0, result.output
    assert "Arial Regular" in result.output
    assert "2 different files" in result.output


def test_fontctl_conflicts_none_found(tmp_path):
    runner, db_path = _scanned_db(tmp_path)  # Arial Regular + Bold, no conflicts

    result = runner.invoke(fontctl, ["--db", str(db_path), "conflicts"])

    assert result.exit_code == 0, result.output
    assert "no conflicts found" in result.output


def test_fontctl_activate_reports_conflict_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    build_test_font(folder_a / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=700)
    build_test_font(folder_b / "Arial-Alt.ttf", family="Arial", style="Regular", a_glyph_size=500)
    db_path = tmp_path / "library.db"
    runner = CliRunner()
    runner.invoke(fontctl, ["--db", str(db_path), "scan", str(tmp_path)])

    result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])

    assert result.exit_code == 0, result.output
    assert "activated 1 file(s) for Arial" in result.output
    assert "conflicts with already-active" in result.output


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


def test_fontctl_activate_with_duration_shows_expiry_in_info(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    activate_result = runner.invoke(
        fontctl, ["--db", str(db_path), "activate", "--for", "30m", "Arial"]
    )
    assert activate_result.exit_code == 0, activate_result.output

    info_result = runner.invoke(fontctl, ["--db", str(db_path), "info", "Arial"])
    assert "expires" in info_result.output


def test_fontctl_activate_invalid_duration_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "--for", "nonsense", "Arial"])

    assert result.exit_code != 0
    assert "invalid duration" in result.output


def test_fontctl_deactivate_expired(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "activate", "--for", "30m", "Arial"])

    conn = connect(db_path)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    conn.execute("UPDATE activations SET expires_at = ?", (past,))
    conn.commit()
    conn.close()

    result = runner.invoke(fontctl, ["--db", str(db_path), "deactivate-expired"])

    assert result.exit_code == 0, result.output
    assert "deactivated 2 file(s) for expired" in result.output


def test_fontctl_startup_reapplies_active_fonts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "startup"])

    assert result.exit_code == 0, result.output
    assert "restored 2 file(s) for restored" in result.output


def test_fontctl_startup_json_output_when_nothing_active(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "startup", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["processed"] == []


def test_fontctl_disable_then_activate_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    disable_result = runner.invoke(fontctl, ["--db", str(db_path), "disable", "Arial"])
    assert disable_result.exit_code == 0, disable_result.output
    assert "disabled 2 file(s) for Arial" in disable_result.output

    activate_result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])
    assert activate_result.exit_code == 0, activate_result.output
    assert "activated 0 file(s) for Arial" in activate_result.output
    assert "disabled" in activate_result.output


def test_fontctl_enable_allows_activation_again(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "disable", "Arial"])

    enable_result = runner.invoke(fontctl, ["--db", str(db_path), "enable", "Arial"])
    assert enable_result.exit_code == 0, enable_result.output

    activate_result = runner.invoke(fontctl, ["--db", str(db_path), "activate", "Arial"])
    assert "activated 2 file(s) for Arial" in activate_result.output


def test_fontctl_disable_unknown_family_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "disable", "Nonexistent"])

    assert result.exit_code != 0
    assert "no such family" in result.output


def _set_up_activation_set(runner, db_path):
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "create", "Body Text"])
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "add", "Body Text", "Arial", "Regular"])
    runner.invoke(fontctl, ["--db", str(db_path), "collection", "add", "Body Text", "Arial", "Bold"])


def test_fontctl_set_activate_plain_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    _set_up_activation_set(runner, db_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "set", "activate", "Body Text"])

    assert result.exit_code == 0, result.output
    assert "activated 2 file(s) for Body Text" in result.output


def test_fontctl_set_deactivate_plain_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    _set_up_activation_set(runner, db_path)
    runner.invoke(fontctl, ["--db", str(db_path), "set", "activate", "Body Text"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "set", "deactivate", "Body Text"])

    assert result.exit_code == 0, result.output
    assert "deactivated 2 file(s) for Body Text" in result.output


def test_fontctl_set_activate_json_output(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)
    _set_up_activation_set(runner, db_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "set", "activate", "--json", "Body Text"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["label"] == "Body Text"
    assert len(payload["processed"]) == 2


def test_fontctl_set_activate_unknown_set_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "glyphmatrix.core.activation_service.get_provider", lambda: FakeActivationProvider()
    )
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "set", "activate", "Nonexistent"])

    assert result.exit_code != 0
    assert "no such set" in result.output


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


def test_fontctl_preview_writes_png(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    out_path = tmp_path / "out.png"

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "preview", "Arial", "Regular", "-o", str(out_path)]
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()
    assert str(out_path) in result.output


def test_fontctl_preview_waterfall(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    out_path = tmp_path / "waterfall.png"

    result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "preview", "Arial", "Regular", "--waterfall", "-o", str(out_path)],
    )

    assert result.exit_code == 0, result.output
    assert out_path.exists()


def test_fontctl_preview_json_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    out_path = tmp_path / "out.png"

    result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "preview", "--json", "Arial", "Regular", "-o", str(out_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["output"] == str(out_path)


def test_fontctl_preview_unknown_face_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "preview", "Nope", "Regular"])

    assert result.exit_code != 0
    assert "no such face" in result.output


def test_fontctl_package_create_add_show(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    create_result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "package", "create", "Adobe Font Folio 11", "--vendor", "Adobe"],
    )
    assert create_result.exit_code == 0, create_result.output

    add_result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "package", "add", "Adobe Font Folio 11", "Arial", "Regular"],
    )
    assert add_result.exit_code == 0, add_result.output
    assert "added Arial Regular to 'Adobe Font Folio 11'" in add_result.output

    show_result = runner.invoke(
        fontctl, ["--db", str(db_path), "package", "show", "Adobe Font Folio 11"]
    )
    assert show_result.exit_code == 0, show_result.output
    assert "Arial Regular" in show_result.output


def test_fontctl_package_create_duplicate_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "package", "create", "Adobe Font Folio 11"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "package", "create", "Adobe Font Folio 11"])

    assert result.exit_code != 0
    assert "already exists" in result.output


def test_fontctl_package_list(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(
        fontctl,
        ["--db", str(db_path), "package", "create", "Adobe Font Folio 11", "--vendor", "Adobe"],
    )
    runner.invoke(
        fontctl, ["--db", str(db_path), "package", "add", "Adobe Font Folio 11", "Arial", "Regular"]
    )

    result = runner.invoke(fontctl, ["--db", str(db_path), "package", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [
        {"name": "Adobe Font Folio 11", "vendor": "Adobe", "file_count": 1, "document_count": 0}
    ]


def test_fontctl_package_remove(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "package", "create", "Adobe Font Folio 11"])
    runner.invoke(
        fontctl, ["--db", str(db_path), "package", "add", "Adobe Font Folio 11", "Arial", "Regular"]
    )

    result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "package", "remove", "Adobe Font Folio 11", "Arial", "Regular"],
    )

    assert result.exit_code == 0, result.output
    assert "removed Arial Regular from 'Adobe Font Folio 11'" in result.output


def test_fontctl_package_doc_add_list_remove(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "package", "create", "Adobe Font Folio 11"])
    doc_path = tmp_path / "readme.pdf"
    doc_path.write_text("fake pdf content")

    add_result = runner.invoke(
        fontctl,
        [
            "--db", str(db_path), "package", "doc-add", "Adobe Font Folio 11", str(doc_path),
            "--description", "Install guide",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    show_result = runner.invoke(
        fontctl, ["--db", str(db_path), "package", "show", "Adobe Font Folio 11"]
    )
    assert "Install guide" in show_result.output
    assert str(doc_path) in show_result.output

    remove_result = runner.invoke(
        fontctl,
        ["--db", str(db_path), "package", "doc-remove", "Adobe Font Folio 11", str(doc_path)],
    )
    assert remove_result.exit_code == 0, remove_result.output
    assert "removed document" in remove_result.output


def test_fontctl_package_add_unknown_package_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(
        fontctl, ["--db", str(db_path), "package", "add", "Nonexistent", "Arial", "Regular"]
    )

    assert result.exit_code != 0
    assert "no such package" in result.output


def test_fontctl_search_plain_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "search", "aria"])

    assert result.exit_code == 0, result.output
    assert "Arial" in result.output


def test_fontctl_search_no_matches(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "search", "nonexistent"])

    assert result.exit_code == 0, result.output
    assert "no matches" in result.output


def test_fontctl_search_json_output(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "search", "--json", "aria"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 2  # Arial Regular + Bold


def test_fontctl_favorite_add_list_remove(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    add_result = runner.invoke(fontctl, ["--db", str(db_path), "favorite", "Arial", "Regular"])
    assert add_result.exit_code == 0, add_result.output
    assert "favorited Arial Regular" in add_result.output

    list_result = runner.invoke(fontctl, ["--db", str(db_path), "favorites"])
    assert list_result.exit_code == 0, list_result.output
    assert "Arial Regular" in list_result.output

    remove_result = runner.invoke(fontctl, ["--db", str(db_path), "unfavorite", "Arial", "Regular"])
    assert remove_result.exit_code == 0, remove_result.output
    assert "unfavorited Arial Regular" in remove_result.output

    empty_result = runner.invoke(fontctl, ["--db", str(db_path), "favorites"])
    assert "no favorites yet" in empty_result.output


def test_fontctl_favorite_unknown_face_errors(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "favorite", "Nope", "Regular"])

    assert result.exit_code != 0
    assert "no such face" in result.output


def test_fontctl_unfavorite_when_not_favorited(tmp_path):
    runner, db_path = _scanned_db(tmp_path)

    result = runner.invoke(fontctl, ["--db", str(db_path), "unfavorite", "Arial", "Regular"])

    assert result.exit_code == 0, result.output
    assert "was not a favorite" in result.output


def test_fontctl_favorites_visible_via_collection_show(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    runner.invoke(fontctl, ["--db", str(db_path), "favorite", "Arial", "Regular"])

    result = runner.invoke(fontctl, ["--db", str(db_path), "collection", "show", "Favorites"])

    assert result.exit_code == 0, result.output
    assert "Arial Regular" in result.output


def test_fontctl_backup_creates_file(tmp_path):
    runner, db_path = _scanned_db(tmp_path)
    backup_path = tmp_path / "backup.db"

    result = runner.invoke(fontctl, ["--db", str(db_path), "backup", str(backup_path)])

    assert result.exit_code == 0, result.output
    assert backup_path.exists()


def test_fontctl_restore_with_yes_flag(tmp_path):
    runner, db_path_a = _scanned_db(tmp_path)
    backup_path = tmp_path / "backup.db"
    runner.invoke(fontctl, ["--db", str(db_path_a), "backup", str(backup_path)])

    other_db_path = tmp_path / "other.db"
    result = runner.invoke(
        fontctl, ["--db", str(other_db_path), "restore", "--yes", str(backup_path)]
    )

    assert result.exit_code == 0, result.output
    list_result = runner.invoke(fontctl, ["--db", str(other_db_path), "list"])
    assert "Arial" in list_result.output


def test_fontctl_restore_prompts_and_accepts(tmp_path):
    runner, db_path_a = _scanned_db(tmp_path)
    backup_path = tmp_path / "backup.db"
    runner.invoke(fontctl, ["--db", str(db_path_a), "backup", str(backup_path)])

    other_db_path = tmp_path / "other.db"
    result = runner.invoke(
        fontctl, ["--db", str(other_db_path), "restore", str(backup_path)], input="y\n"
    )

    assert result.exit_code == 0, result.output
    assert "restored" in result.output


def test_fontctl_restore_aborts_when_declined(tmp_path):
    runner, db_path_a = _scanned_db(tmp_path)
    backup_path = tmp_path / "backup.db"
    runner.invoke(fontctl, ["--db", str(db_path_a), "backup", str(backup_path)])

    other_db_path = tmp_path / "other.db"
    result = runner.invoke(
        fontctl, ["--db", str(other_db_path), "restore", str(backup_path)], input="n\n"
    )

    assert result.exit_code != 0
