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
