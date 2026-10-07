"""Opt-in smoke test: isolated temporary rows, no Telegram calls or billing.

Creates and removes a uniquely named test table and exports a temporary backup.
Never prints secrets or business records. Do not run the general unit tests
against the production backend.
"""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from contextlib import suppress
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run():
    from nexora.db import connect, snapshot, initialized_remote
    from nexora import async_db
    initialized_remote()
    name = "nexora_probe_" + uuid.uuid4().hex
    created = False
    try:
        with closing(connect("ignored")) as conn:
            conn.execute(f"CREATE TABLE {name}(id INTEGER PRIMARY KEY, value INTEGER CHECK(value>=0))")
            created = True
            conn.executemany(f"INSERT INTO {name} VALUES(?,?)", [(1, 20), (2, 0)])
            conn.commit()
        with closing(connect("ignored")) as conn:
            assert conn.execute(f"SELECT value FROM {name} WHERE id=1").fetchone()[0] == 20
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"UPDATE {name} SET value=0 WHERE id=1")
            conn.rollback()
            assert conn.execute(f"SELECT value FROM {name} WHERE id=1").fetchone()[0] == 20
        print("OK: escritura, cierre/reconexión y rollback.", flush=True)

        def transfer_once():
            with closing(connect("ignored")) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    receipt = conn.execute(f"INSERT OR IGNORE INTO {name} VALUES(3,0)")
                    if receipt.rowcount:
                        conn.execute(f"UPDATE {name} SET value=value-5 WHERE id=1")
                        conn.execute(f"UPDATE {name} SET value=value+5 WHERE id=2")
                    conn.commit()
                except sqlite3.OperationalError as exc:
                    with suppress(Exception):
                        conn.rollback()
                    if "SQLITE_BUSY" in str(exc) or "database is locked" in str(exc):
                        return False  # Rejected, not a successful transfer.
                    raise
                return True

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: transfer_once(), range(2)))
        assert any(outcomes), "Both concurrent transactions were rejected"
        # Re-delivery after the competing transaction completed must be a no-op.
        assert transfer_once()
        with closing(connect("ignored")) as conn:
            assert conn.execute(f"SELECT value FROM {name} ORDER BY id").fetchall() == [(15,), (5,), (0,)]
        print("OK: concurrencia sin doble débito; bloqueo rechazado y reentrega idempotente.", flush=True)

        async def async_check():
            async with async_db.connect("ignored") as conn:
                conn.row_factory = sqlite3.Row
                async with conn.execute(f"SELECT value FROM {name} WHERE id=1") as cursor:
                    assert (await cursor.fetchone())["value"] == 15
        asyncio.run(async_check())
        print("OK: conexión asíncrona del bot.", flush=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.db"
            snapshot("ignored", path)
            with closing(sqlite3.connect(path)) as restored:
                assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert restored.execute(f"SELECT value FROM {name} WHERE id=1").fetchone()[0] == 15
        print("OK: respaldo remoto abierto como SQLite independiente.", flush=True)
        os.environ.setdefault("NEXORA_PANEL_SECRET", secrets.token_hex(32))
        os.environ["NEXORA_INTERNAL_API_KEY"] = secrets.token_hex(32)
        from nexora.web import app
        client = app.test_client()
        assert client.get("/tg_info?ID_TG=7454664711").status_code in (401, 403)
        response = client.get("/tg_info?ID_TG=7454664711", headers={"X-Internal-Api-Key": os.environ["NEXORA_INTERNAL_API_KEY"]})
        assert response.status_code == 200
        print("OK: API web autenticada; acceso anónimo rechazado.", flush=True)
    finally:
        if created:
            with closing(connect("ignored")) as conn:
                conn.execute(f"DROP TABLE IF EXISTS {name}")
                conn.commit()
            print("Datos de prueba retirados.", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-test", action="store_true", required=True)
    parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    os.environ["DATABASE_BACKEND"] = "turso"
    os.environ.pop("NEXORA_INITIALIZE_SCHEMA", None)
    try:
        run()
    except Exception as exc:
        print("Prueba incompleta: " + type(exc).__name__ + ". No desplegar.")
        if isinstance(exc, sqlite3.OperationalError):
            print(str(exc))  # Adapter errors are sanitized.
        import traceback
        for frame in traceback.extract_tb(exc.__traceback__):
            print(Path(frame.filename).name + ":" + str(frame.lineno) + " " + frame.name)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
