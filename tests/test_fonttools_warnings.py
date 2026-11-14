import logging
import subprocess
import sys

from fontTools.ttLib import TTFont

from glyphmatrix.core.parser import quiet_fonttools

from .fontbuilder import build_test_font


def _noisy_font(path):
    """A font whose head.created predates 1970, so fontTools logs "'created'
    timestamp seems very low" when it decompiles the head table."""
    build_test_font(path)
    font = TTFont(path)
    font["head"].created = 1
    font.save(path)
    return path


# Run in a fresh interpreter: inside pytest, the logging plugin's handler
# swallows records, so a leak to stderr would go unnoticed in-process.
_SCRIPT = """
import sys
from pathlib import Path
{body}
"""


def _stderr_of(body: str, *args) -> str:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(body=body), *map(str, args)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stderr


def test_noisy_font_does_warn_without_suppression(tmp_path):
    path = _noisy_font(tmp_path / "noisy.ttf")

    stderr = _stderr_of(
        "from fontTools.ttLib import TTFont\n"
        "with TTFont(sys.argv[1], lazy=True) as f: f['head']",
        path,
    )

    assert "timestamp seems very low" in stderr


def test_font_commands_do_not_leak_fonttools_warnings_to_stderr(tmp_path):
    path = _noisy_font(tmp_path / "noisy.ttf")

    stderr = _stderr_of(
        "from glyphmatrix.core.parser import parse_font_file\n"
        "from glyphmatrix.core.opentype_features import list_features\n"
        "from glyphmatrix.core.specimen import collect\n"
        "parse_font_file(sys.argv[1])\n"
        "list_features(sys.argv[1])\n"
        "collect(Path(sys.argv[1]).parent)",
        path,
    )

    assert stderr == ""


def test_quiet_fonttools_restores_previous_level():
    logger = logging.getLogger("fontTools")
    original = logger.level
    logger.setLevel(logging.INFO)
    try:
        with quiet_fonttools():
            assert logger.level == logging.ERROR
        assert logger.level == logging.INFO
    finally:
        logger.setLevel(original)


def test_quiet_fonttools_restores_level_on_exception():
    logger = logging.getLogger("fontTools")
    original = logger.level
    try:
        with quiet_fonttools():
            raise ValueError
    except ValueError:
        pass
    assert logger.level == original


def _broken_name_table_font(path):
    """A font whose name table header is garbage: fontTools logs one ERROR
    per name record (count 0xFFFF), 65535 lines without collapsing."""
    build_test_font(path)
    offset = TTFont(path).reader.tables["name"].offset
    data = bytearray(path.read_bytes())
    data[offset:offset + 6] = b"\xff" * 6
    path.write_bytes(bytes(data))
    return path


def test_repeated_fonttools_errors_collapse_to_one_line(tmp_path):
    path = _broken_name_table_font(tmp_path / "broken.ttf")

    stderr = _stderr_of(
        "from glyphmatrix.core.parser import parse_font_file\n"
        "try: parse_font_file(sys.argv[1])\n"
        "except Exception: pass",
        path,
    )

    lines = stderr.splitlines()
    assert len(lines) <= 3, lines[:5]
    assert any("skipping malformed name record" in line and "more like it" in line for line in lines)


def test_quiet_fonttools_passes_each_distinct_error_once_with_count(caplog):
    log = logging.getLogger("fontTools.ttLib.tables._n_a_m_e")
    with caplog.at_level(logging.ERROR):
        with quiet_fonttools():
            for i in range(500):
                log.error("skipping malformed name record #%d", i)
            log.error("something else")
            log.warning("hidden warning")

    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["skipping malformed name record #0 (and 499 more like it)", "something else"]


def test_quiet_fonttools_restores_handlers_and_propagation():
    logger = logging.getLogger("fontTools")
    handlers, propagate = list(logger.handlers), logger.propagate

    with quiet_fonttools():
        pass

    assert logger.handlers == handlers and logger.propagate == propagate


def test_quiet_fonttools_names_the_file_in_a_passed_on_error(caplog):
    log = logging.getLogger("fontTools.ttLib.tables._n_a_m_e")
    with caplog.at_level(logging.ERROR):
        with quiet_fonttools("ABRACADA.TTF"):
            log.error("'name' table stringOffset incorrect. Expected: 342; Actual: 398")

    assert [r.getMessage() for r in caplog.records] == [
        "ABRACADA.TTF: 'name' table stringOffset incorrect. Expected: 342; Actual: 398"
    ]


def test_quiet_fonttools_names_the_file_once_for_a_collapsed_error(caplog):
    log = logging.getLogger("fontTools.ttLib.tables._n_a_m_e")
    with caplog.at_level(logging.ERROR):
        with quiet_fonttools("broken.ttf"):
            for i in range(50):
                log.error("skipping malformed name record #%d", i)

    assert [r.getMessage() for r in caplog.records] == [
        "broken.ttf: skipping malformed name record #0 (and 49 more like it)"
    ]


def test_quiet_fonttools_without_a_label_leaves_messages_unchanged(caplog):
    log = logging.getLogger("fontTools.ttLib.tables._n_a_m_e")
    with caplog.at_level(logging.ERROR):
        with quiet_fonttools():
            log.error("something else")

    assert [r.getMessage() for r in caplog.records] == ["something else"]


def test_parse_font_file_names_the_broken_file_in_the_error(tmp_path):
    path = _broken_name_table_font(tmp_path / "broken-name.ttf")

    stderr = _stderr_of(
        "from glyphmatrix.core.parser import parse_font_file\n"
        "try: parse_font_file(sys.argv[1])\n"
        "except Exception: pass",
        path,
    )

    assert "broken-name.ttf" in stderr
