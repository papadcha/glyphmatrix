from glyphmatrix.core.backup import backup_database, restore_database
from glyphmatrix.core.database import connect, init_schema
from glyphmatrix.core.ingest import ingest_directory

from .fontbuilder import build_test_font


def test_backup_database_copies_data(tmp_path):
    build_test_font(tmp_path / "Arial-Regular.ttf", family="Arial", style="Regular")
    live = connect(tmp_path / "live.db")
    init_schema(live)
    ingest_directory(live, tmp_path)

    backup_path = tmp_path / "backup.db"
    result = backup_database(live, backup_path)

    assert result == backup_path
    assert backup_path.exists()

    check = connect(backup_path)
    families = check.execute("SELECT name FROM families").fetchall()
    assert [f["name"] for f in families] == ["Arial"]


def test_backup_database_from_in_memory_connection(tmp_path):
    conn = connect(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO families (name) VALUES ('Arial')")
    conn.commit()

    backup_path = tmp_path / "backup.db"
    backup_database(conn, backup_path)

    check = connect(backup_path)
    assert check.execute("SELECT name FROM families").fetchone()["name"] == "Arial"


def test_backup_database_creates_parent_directories(tmp_path):
    conn = connect(":memory:")
    init_schema(conn)

    backup_path = tmp_path / "nested" / "dir" / "backup.db"
    result = backup_database(conn, backup_path)

    assert result.exists()


def test_restore_database_overwrites_destination(tmp_path):
    source_path = tmp_path / "source.db"
    source_conn = connect(source_path)
    init_schema(source_conn)
    source_conn.execute("INSERT INTO families (name) VALUES ('Arial')")
    source_conn.commit()

    dest_path = tmp_path / "dest.db"
    dest_conn = connect(dest_path)
    init_schema(dest_conn)
    dest_conn.execute("INSERT INTO families (name) VALUES ('Verdana')")
    dest_conn.commit()
    dest_conn.close()

    restore_database(source_path, dest_path)

    check = connect(dest_path)
    families = [f["name"] for f in check.execute("SELECT name FROM families").fetchall()]
    assert families == ["Arial"]  # Verdana is gone — dest now matches source exactly


def test_restore_database_into_nonexistent_destination(tmp_path):
    source_path = tmp_path / "source.db"
    source_conn = connect(source_path)
    init_schema(source_conn)
    source_conn.execute("INSERT INTO families (name) VALUES ('Arial')")
    source_conn.commit()

    dest_path = tmp_path / "does_not_exist_yet" / "dest.db"
    restore_database(source_path, dest_path)

    check = connect(dest_path)
    assert check.execute("SELECT name FROM families").fetchone()["name"] == "Arial"
