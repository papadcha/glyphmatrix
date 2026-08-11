from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory
from glyphmatrix.core.licenses import classify_license, list_license_conflicts

from .fontbuilder import build_test_font


def _conn():
    conn = connect(":memory:")
    init_schema(conn)
    return conn


def test_classify_license_recognizes_ofl():
    text = "This Font Software is licensed under the SIL Open Font License, Version 1.1."
    assert classify_license(text) == "OFL-1.1"


def test_classify_license_recognizes_apache():
    assert classify_license("Licensed under the Apache License, Version 2.0") == "Apache-2.0"


def test_classify_license_recognizes_mit():
    assert classify_license("Permission granted under the MIT License") == "MIT"


def test_classify_license_is_case_insensitive():
    assert classify_license("sil OPEN font LICENSE") == "OFL-1.1"


def test_classify_license_unrecognized_text_is_unknown():
    assert classify_license("Some proprietary text nobody has seen before") == "Unknown"


def test_classify_license_none_when_empty():
    assert classify_license(None) is None
    assert classify_license("") is None
    assert classify_license("   ") is None


def test_classify_license_does_not_mistake_copyright_boilerplate_for_proprietary():
    """Regression test for a real false positive found via real-hardware
    testing with DejaVu Sans: its Bitstream Vera license contains
    "Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved." as
    standard copyright-ownership boilerplate, immediately followed by a
    broad permissive grant ("Permission is hereby granted, free of
    charge..."). A naive "All Rights Reserved" -> Commercial/Proprietary
    rule confidently mis-classified a genuinely free font — worse than
    just returning Unknown."""
    text = (
        'Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved. Bitstream Vera is '
        'a trademark of Bitstream, Inc.\n\n'
        'Permission is hereby granted, free of charge, to any person obtaining a copy '
        'of the fonts accompanying this license to reproduce and distribute the Font '
        'Software, including without limitation the rights to use, copy, merge, '
        'publish, distribute, and/or sell copies of the Font Software.'
    )
    assert classify_license(text) == "Unknown"


def test_list_license_conflicts_flags_disagreeing_files(tmp_path):
    folder_a = tmp_path / "a"
    folder_a.mkdir()
    folder_b = tmp_path / "b"
    folder_b.mkdir()
    build_test_font(
        folder_a / "Arial-Regular.ttf", family="Arial", style="Regular", a_glyph_size=700
    )
    build_test_font(
        folder_b / "Arial-Alt.ttf", family="Arial", style="Regular", a_glyph_size=500
    )
    conn = _conn()
    ingest_directory(conn, tmp_path)
    # fontbuilder doesn't set a license nameID, so both currently classify
    # as None (no license info) — force a real disagreement directly, the
    # way a real mixed-license pair would actually differ.
    conn.execute("UPDATE font_files SET license = ? WHERE path LIKE '%Arial-Regular%'",
                 ("SIL Open Font License",))
    conn.execute("UPDATE font_files SET license = ? WHERE path LIKE '%Arial-Alt%'",
                 ("Apache License, Version 2.0",))
    conn.commit()

    conflicts = list_license_conflicts(conn)

    assert len(conflicts) == 1
    assert conflicts[0]["family"] == "Arial"
    categories = {f["license_category"] for f in conflicts[0]["files"]}
    assert categories == {"OFL-1.1", "Apache-2.0"}


def test_list_license_conflicts_ignores_faces_with_consistent_license(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    build_test_font(tmp_path / "Arial-Bold.ttf", family="Arial", style="Bold")
    conn = _conn()
    ingest_directory(conn, tmp_path)

    assert list_license_conflicts(conn) == []


def test_list_license_conflicts_empty_library():
    conn = _conn()
    assert list_license_conflicts(conn) == []
