"""Explicit SQLite/libSQL routing shared by the bot and web.

Turso uses one database with distinct tables, never a disposable local replica.
No write is retried: a network failure after COMMIT has an unknown outcome.
"""
import os
import sqlite3
import re
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit
from functools import wraps

SCHEMA_VERSION = "turso-unified-v1"


def initialized_remote():
    if not remote_enabled() or os.getenv("NEXORA_INITIALIZE_SCHEMA") == "1":
        return False
    with closing(connect("ignored")) as conn:
        try:
            row = conn.execute("SELECT version FROM nexora_schema WHERE version=?", (SCHEMA_VERSION,)).fetchone()
        except sqlite3.OperationalError:
            row = None
    if not row:
        raise RuntimeError("Turso no está inicializado: ejecutar scripts/init_turso.py --initialize antes de desplegar")
    return True


def schema_initializer(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if initialized_remote():
            return
        return fn(*args, **kwargs)
    return wrapped


def remote_enabled():
    backend = os.getenv("DATABASE_BACKEND", "sqlite").strip().lower()
    if backend not in {"sqlite", "turso"}:
        raise ValueError("DATABASE_BACKEND debe ser sqlite o turso")
    return backend == "turso"


def remote_config():
    url = os.getenv("TURSO_DATABASE_URL", "").strip()
    token = os.getenv("TURSO_AUTH_TOKEN", "").strip()
    parsed = urlsplit(url)
    if (parsed.scheme not in {"libsql", "https"} or not parsed.hostname
            or not parsed.hostname.endswith(".turso.io")
            or parsed.port not in (None, 443) or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("TURSO_DATABASE_URL inválida: usa la URL de Turso sin credenciales")
    if not token:
        raise ValueError("Falta TURSO_AUTH_TOKEN")
    return url, token


def _call(fn, *args, **kwargs):
    # The driver has one Error type. Preserve useful SQLite categories, but do
    # not send raw HTTP errors (which can include URLs/tokens) to logs or users.
    import libsql
    try:
        return fn(*args, **kwargs)
    except (libsql.Error, ValueError) as exc:
        message = str(exc).lower()
        if "constraint" in message:
            raise sqlite3.IntegrityError("Restricción de integridad en Turso") from None
        for text in ("duplicate column name", "no such table", "database is locked"):
            if text in message:
                raise sqlite3.OperationalError(text) from None
        codes = re.findall(r"\b(?:SQLITE|HRANA|STREAM|TRANSACTION)_[A-Z_]+\b", str(exc))
        raise sqlite3.OperationalError(
            "Turso no completó la operación" + (" (" + ",".join(codes) + ")" if codes else "")
            + ". Si era una escritura, verifica su estado antes de repetirla."
        ) from None


class Cursor:
    def __init__(self, connection, raw):
        self.connection, self.raw = connection, raw
        self.row_factory = connection.row_factory
        self.arraysize = 1

    @property
    def description(self):
        return self.raw.description

    @property
    def rowcount(self):
        return self.raw.rowcount

    @property
    def lastrowid(self):
        return self.raw.lastrowid

    def execute(self, sql, parameters=()):
        _call(self.raw.execute, sql, parameters)
        return self

    def executemany(self, sql, parameters):
        _call(self.raw.executemany, sql, parameters)
        return self

    def executescript(self, sql):
        _call(self.raw.executescript, sql)
        return self

    def _row(self, values):
        if values is None or self.row_factory is None:
            return values
        if self.row_factory is sqlite3.Row:
            # sqlite3.Row requires a real sqlite3.Cursor. Only result values go
            # into this in-memory helper; business data is never persisted here.
            with closing(sqlite3.connect(":memory:")) as memory:
                memory.row_factory = sqlite3.Row
                columns = [col[0].replace('"', '""') for col in self.description]
                sql = "SELECT " + ",".join('? AS "' + col + '"' for col in columns)
                return memory.execute(sql, values).fetchone()
        return self.row_factory(self, values)

    def fetchone(self):
        return self._row(_call(self.raw.fetchone))

    def fetchall(self):
        return [self._row(row) for row in _call(self.raw.fetchall)]

    def fetchmany(self, size=None):
        return [self._row(row) for row in _call(self.raw.fetchmany, size or self.arraysize)]

    def close(self):
        _call(self.raw.close)

    def __iter__(self):
        return self

    def __next__(self):
        row = self.fetchone()
        if row is None:
            raise StopIteration
        return row


class Connection:
    def __init__(self, raw):
        self.raw = raw
        self.row_factory = None

    @property
    def in_transaction(self):
        return self.raw.in_transaction

    @property
    def isolation_level(self):
        return self.raw.isolation_level

    @isolation_level.setter
    def isolation_level(self, value):
        self.raw.isolation_level = value

    def cursor(self):
        return Cursor(self, _call(self.raw.cursor))

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, parameters):
        return self.cursor().executemany(sql, parameters)

    def executescript(self, sql):
        return self.cursor().executescript(sql)

    def commit(self):
        _call(self.raw.commit)

    def rollback(self):
        _call(self.raw.rollback)

    def close(self):
        _call(self.raw.close)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                self.commit()
            except Exception:
                self.rollback()
                raise
        else:
            self.rollback()


def connect(database, **kwargs):
    if not remote_enabled():
        return sqlite3.connect(database, **kwargs)
    import libsql
    url, token = remote_config()
    options = {"timeout": kwargs.pop("timeout", 15.0)}
    options["_check_same_thread"] = kwargs.pop("check_same_thread", True)
    if "isolation_level" in kwargs:
        options["isolation_level"] = kwargs.pop("isolation_level")
    if kwargs:
        raise TypeError("Opciones de conexión no admitidas: " + ",".join(kwargs))
    return Connection(_call(libsql.connect, url, auth_token=token, **options))


def snapshot(database, destination):
    """Create a consistent, standalone SQLite export; never copy a live file."""
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError("El destino del respaldo ya existe")
    try:
        with closing(connect(database)) as source, closing(sqlite3.connect(target)) as out:
            if not remote_enabled():
                source.backup(out)
                return
            source.execute("BEGIN")
            schema = source.execute(
                "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL "
                "AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"
            ).fetchall()
            for kind, name, sql in schema:
                if kind != "table":
                    continue
                out.execute(sql)
                quoted = '"' + name.replace('"', '""') + '"'
                cursor = source.execute("SELECT * FROM " + quoted)
                while rows := cursor.fetchmany(500):
                    marks = ",".join("?" for _ in rows[0])
                    out.executemany("INSERT INTO " + quoted + " VALUES (" + marks + ")", rows)
            for kind, name, sql in schema:
                if kind != "table":
                    out.execute(sql)
            if source.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
                sequences = source.execute("SELECT name,seq FROM sqlite_sequence").fetchall()
                out.execute("DELETE FROM sqlite_sequence")
                out.executemany("INSERT INTO sqlite_sequence(name,seq) VALUES(?,?)", sequences)
            source.rollback()
            out.commit()
            if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError("Respaldo inválido")
    except Exception:
        target.unlink(missing_ok=True)
        raise
