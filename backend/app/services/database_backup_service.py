from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import settings
from app.database import engine


BACKUP_DIR = Path("data") / "db_backups"
SQLITE_HEADER = b"SQLite format 3\x00"
REQUIRED_TABLES = {"users", "audit_logs"}


class DatabaseBackupError(Exception):
    pass


def _database_url():
    return make_url(settings.DATABASE_URL)


def database_dialect() -> str:
    return _database_url().drivername.split("+", 1)[0]


def is_sqlite_database() -> bool:
    return database_dialect() == "sqlite"


def get_sqlite_database_path() -> Path:
    url = _database_url()
    database = url.database
    if not database or database == ":memory:":
        raise DatabaseBackupError("파일 기반 SQLite DB만 백업/복원을 지원합니다.")
    return Path(database).expanduser().resolve()


def ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR.resolve()


def format_bytes(size: int | None) -> str:
    if size is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def serialize_backup(path: Path) -> dict:
    stat = path.stat()
    created_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return {
        "filename": path.name,
        "size_bytes": stat.st_size,
        "size_label": format_bytes(stat.st_size),
        "created_at": created_at.isoformat(),
    }


def get_database_info() -> dict:
    backup_dir = ensure_backup_dir()
    if not is_sqlite_database():
        return {
            "supported": False,
            "dialect": database_dialect(),
            "database_path": None,
            "database_size_bytes": None,
            "database_size_label": "-",
            "modified_at": None,
            "backup_directory": str(backup_dir),
            "backup_count": len(list_backup_files()),
        }

    db_path = get_sqlite_database_path()
    stat = db_path.stat() if db_path.exists() else None
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat() if stat else None
    return {
        "supported": True,
        "dialect": "sqlite",
        "database_path": str(db_path),
        "database_size_bytes": stat.st_size if stat else None,
        "database_size_label": format_bytes(stat.st_size if stat else None),
        "modified_at": modified_at,
        "backup_directory": str(backup_dir),
        "backup_count": len(list_backup_files()),
    }


def list_backup_files() -> list[Path]:
    backup_dir = ensure_backup_dir()
    return sorted(
        (path for path in backup_dir.glob("*.db") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def list_backups() -> list[dict]:
    return [serialize_backup(path) for path in list_backup_files()]


def resolve_backup_file(filename: str) -> Path:
    backup_dir = ensure_backup_dir()
    if filename != Path(filename).name:
        raise DatabaseBackupError("잘못된 백업 파일명입니다.")
    path = (backup_dir / filename).resolve()
    if path.parent != backup_dir:
        raise DatabaseBackupError("잘못된 백업 파일 경로입니다.")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(filename)
    return path


def create_sqlite_backup(prefix: str = "itam_backup") -> Path:
    if not is_sqlite_database():
        raise DatabaseBackupError("SQLite DB에서만 백업을 생성할 수 있습니다.")

    db_path = get_sqlite_database_path()
    if not db_path.exists():
        raise DatabaseBackupError("DB 파일을 찾을 수 없습니다.")

    backup_dir = ensure_backup_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_dir / f"{prefix}_{timestamp}.db"

    source = sqlite3.connect(str(db_path))
    target = sqlite3.connect(str(destination))
    try:
        source.execute("PRAGMA wal_checkpoint(PASSIVE)")
        source.backup(target)
    finally:
        target.close()
        source.close()

    validate_sqlite_database(destination)
    return destination


def validate_sqlite_database(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(len(SQLITE_HEADER))
    if header != SQLITE_HEADER:
        raise DatabaseBackupError("SQLite DB 파일이 아닙니다.")

    connection = sqlite3.connect(str(path))
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0].lower() != "ok":
            raise DatabaseBackupError("DB 무결성 검사에 실패했습니다.")

        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        tables = {row[0] for row in rows}
        missing = REQUIRED_TABLES - tables
        if missing:
            names = ", ".join(sorted(missing))
            raise DatabaseBackupError(f"필수 테이블이 없습니다: {names}")
    finally:
        connection.close()


def restore_sqlite_database(upload_path: Path) -> dict:
    if not is_sqlite_database():
        raise DatabaseBackupError("SQLite DB에서만 복원을 실행할 수 있습니다.")

    validate_sqlite_database(upload_path)
    db_path = get_sqlite_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine.dispose()
    shutil.copy2(upload_path, db_path)

    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.commit()
    finally:
        connection.close()

    validate_sqlite_database(db_path)
    return get_database_info()
