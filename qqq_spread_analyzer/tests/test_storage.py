import duckdb

from src.storage import Storage


def test_storage_schema_init(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("DB_PATH", str(db_path))
    from src.config import Settings

    storage = Storage(Settings(db_path=db_path))
    tables = storage._conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    storage.close()
    names = {row[0] for row in tables}
    assert "option_snapshots" in names
    cols = duckdb.connect(str(db_path)).execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'option_snapshots'"
    ).fetchall()
    col_names = {row[0] for row in cols}
    assert "option_right" in col_names
    assert "right" not in col_names
