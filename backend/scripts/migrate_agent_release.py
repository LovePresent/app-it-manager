"""Back up, validate, migrate, and verify an existing SQLite installation.

No application tables are initialized on a missing database. The sole metadata
adoption is a frozen deployed b856260 or 0ac5743 create_all schema. The latter
already contains IP change history; the former receives its original migration.
Run with the old application stopped so concurrent business writes cannot be
mistaken for a migration change. Failures retain the database and backup.
"""
import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from app.config import settings

BASELINE = "20260429_ip_change_history"
LEGACY_BRANCH = "20261025_legacy_inventory"
EXPECTED_HEAD = "20261025_agent_release"
FROZEN_SCHEMA = Path(__file__).with_name("legacy_schema_0ac5743.json")
FROZEN_DEPLOYED_SCHEMA = Path(__file__).with_name("legacy_schema_b856260.json")


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def read_only(path):
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def table_names(db):
    return [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name")]


def schema(db):
    result = {}
    for table in table_names(db):
        indexes = []
        for index in db.execute(f"PRAGMA index_list({quote(table)})"):
            columns = [item[2] for item in db.execute(f"PRAGMA index_info({quote(index[1])})")]
            # SQLite-generated constraint index names may change on a batch rebuild.
            indexes.append([index[2], index[3], columns])
        create_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        checks = []
        for match in re.finditer(r"\bCHECK\s*\(", create_sql, re.I):
            start, depth = match.end(), 1
            for end in range(start, len(create_sql)):
                depth += (create_sql[end] == "(") - (create_sql[end] == ")")
                if depth == 0:
                    checks.append(re.sub(r"\s+", "", create_sql[start:end]))
                    break
        result[table] = {
            "columns": [list(row[1:]) for row in db.execute(f"PRAGMA table_info({quote(table)})")],
            "foreign_keys": sorted([list(row[2:]) for row in db.execute(f"PRAGMA foreign_key_list({quote(table)})")], key=repr),
            "indexes": sorted(indexes, key=repr),
            "checks": sorted(checks),
        }
    return result


def encoded(value):
    if value is None:
        return ["null"]
    if isinstance(value, bytes):
        return ["blob", base64.b64encode(value).decode("ascii")]
    if isinstance(value, float):
        return ["real", value.hex()]
    return ["integer" if isinstance(value, int) else "text", value]


def snapshot(db, prior=None):
    result = {}
    for table in (prior or {name: None for name in table_names(db)}):
        columns = prior[table]["columns"] if prior else [row[1] for row in db.execute(f"PRAGMA table_info({quote(table)})")]
        rows = []
        for row in db.execute("SELECT " + ",".join(map(quote, columns)) + " FROM " + quote(table)):
            content = json.dumps([encoded(item) for item in row], ensure_ascii=False, separators=(",", ":")).encode()
            rows.append(hashlib.sha256(content).hexdigest())
        digest = hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()
        result[table] = {"columns": columns, "rows": len(rows), "sha256": digest}
    return result


def current_revision(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
    if not exists:
        return None
    rows = db.execute("SELECT version_num FROM alembic_version").fetchall()
    if len(rows) > 1:
        raise RuntimeError("Multiple migration heads; manual review required.")
    return rows[0][0] if rows else None


def alembic(command, revision, database_path):
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(database_path.resolve())}
    result = subprocess.run([sys.executable, "-m", "alembic", command, revision], cwd=BACKEND,
                            env=env, capture_output=True, text=True)
    if result.returncode:
        # Do not echo SQL or database row values from a failed statement.
        raise RuntimeError("Migration command failed; database and backup retained for review.")


def create_legacy(path, source="0ac5743"):
    if source not in {"0ac5743", "b856260"}:
        raise RuntimeError("Unknown legacy schema source.")
    manifest = json.loads((FROZEN_SCHEMA if source == "0ac5743" else FROZEN_DEPLOYED_SCHEMA).read_text(encoding="utf-8"))
    if manifest["sourceRevision"] != source or manifest["baselineRevision"] != (BASELINE if source == "0ac5743" else None):
        raise RuntimeError("Invalid frozen legacy schema.")
    with closing(sqlite3.connect(path)) as db:
        for statement in manifest["statements"]:
            db.execute(statement)
        db.commit()


def expected_schema(revision, source="0ac5743"):
    with tempfile.TemporaryDirectory(prefix="itam-migration-schema-") as temporary:
        path = Path(temporary) / "expected.db"
        if revision == LEGACY_BRANCH:
            create_legacy(path, "b856260")
            alembic("upgrade", LEGACY_BRANCH, path)
        else:
            create_legacy(path, source)
            if revision and revision != BASELINE:
                alembic("stamp", BASELINE, path)
                if revision == EXPECTED_HEAD:
                    alembic("upgrade", LEGACY_BRANCH, path)
                alembic("upgrade", revision, path)
        with closing(read_only(path)) as db:
            return schema(db)


@contextmanager
def startup_lock(path):
    # Production runs in Linux containers. Lock only coordinates this guard;
    # the deployment must stop the old application before switching containers.
    import fcntl
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def migrate():
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:" or url.query:
        raise RuntimeError("This release guard requires an existing local SQLite database; review other database engines separately.")
    path = Path(url.database).resolve()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("Existing database not found; refusing to create a replacement.")
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    graph = ScriptDirectory.from_config(config)
    if graph.get_heads() != [EXPECTED_HEAD]:
        raise RuntimeError("Unexpected migration graph.")
    known = {revision.revision for revision in graph.walk_revisions()}
    with startup_lock(path.with_name(path.name + ".agent-migration.lock")):
        with closing(read_only(path)) as db:
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("Database integrity check failed.")
            revision = current_revision(db)
            if revision is not None and revision not in known:
                raise RuntimeError("Unknown migration revision; refusing to adopt it.")
            existing_schema = schema(db)
            source = "0ac5743"
            if existing_schema != expected_schema(revision):
                if revision is None and existing_schema == expected_schema(None, "b856260"):
                    source = "b856260"
                else:
                    raise RuntimeError("Database schema does not match a supported revision; refusing to stamp or migrate it.")
            before = snapshot(db)
            backup_dir = Path(settings.AGENT_DATABASE_BACKUP_DIR).resolve()
            backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_" + uuid4().hex[:8]
            backup = backup_dir / ("itam_before_agent_" + stamp + ".db")
            os.close(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            with closing(sqlite3.connect(backup)) as target:
                db.backup(target)
                if snapshot(target) != before:
                    raise RuntimeError("Backup verification failed; refusing to migrate.")
            manifest = {"source_revision": revision, "source_schema": source, "target_revision": EXPECTED_HEAD,
                        "backup": backup.name, "tables": before}
            private_json(backup.with_suffix(".json"), manifest)
        if revision is None and source == "0ac5743":
            # Only Alembic metadata changes; IP history and every business row stay intact.
            alembic("stamp", BASELINE, path)
        if revision not in {LEGACY_BRANCH, EXPECTED_HEAD}:
            # Explicit ordering is necessary for PostgreSQL FKs too: inventory
            # exists before the unchanged license/device/agent migration chain.
            alembic("upgrade", LEGACY_BRANCH, path)
        alembic("upgrade", "head", path)
        with closing(read_only(path)) as db:
            if current_revision(db) != EXPECTED_HEAD or db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise RuntimeError("Post-migration revision or integrity check failed; retain backup for review.")
            if snapshot(db, before) != before:
                raise RuntimeError("Existing row preservation check failed; application startup blocked, backup retained.")
            if schema(db) != expected_schema(EXPECTED_HEAD):
                raise RuntimeError("Post-migration schema verification failed.")
        private_json(backup.with_suffix(".verified.json"), {"revision": EXPECTED_HEAD,
                     "existing_tables": len(before), "existing_values_preserved": True})
        return {"revision": EXPECTED_HEAD, "backup": backup.name, "existing_values_preserved": True}


if __name__ == "__main__":
    try:
        print(json.dumps(migrate(), separators=(",", ":")))
    except Exception as exc:
        print("Agent migration guard stopped: " + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
