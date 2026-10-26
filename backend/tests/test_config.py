from garmates.config import DATABASE_FILE, LEGACY_DATABASE_FILE, Settings


def test_database_from_before_the_rename_is_adopted(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for suffix in ("", "-wal", "-shm"):
        (data / f"{LEGACY_DATABASE_FILE}{suffix}").write_text(f"old{suffix}")

    Settings(data_dir=data).ensure_dirs()

    assert not list(data.glob(f"{LEGACY_DATABASE_FILE}*"))
    assert (data / DATABASE_FILE).read_text() == "old"
    assert (data / f"{DATABASE_FILE}-wal").read_text() == "old-wal"


def test_existing_database_is_never_replaced(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / DATABASE_FILE).write_text("current")
    (data / LEGACY_DATABASE_FILE).write_text("old")

    Settings(data_dir=data).ensure_dirs()

    assert (data / DATABASE_FILE).read_text() == "current"
    assert (data / LEGACY_DATABASE_FILE).exists()
