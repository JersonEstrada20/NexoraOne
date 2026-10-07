import asyncio
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import libsql
from nexora import db, async_db


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.c = db.Connection(libsql.connect(":memory:"))
        self.c.execute("CREATE TABLE balance(id INTEGER PRIMARY KEY, value INTEGER CHECK(value>=0), payload BLOB)")

    def tearDown(self):
        self.c.close()

    def test_row_factory_and_cursor_override(self):
        self.c.row_factory = sqlite3.Row
        self.c.execute("INSERT INTO balance VALUES(?,?,?)", (1, 12, b"binary"))
        self.c.commit()
        row = self.c.execute("SELECT * FROM balance").fetchone()
        self.assertEqual(dict(row), {"id": 1, "value": 12, "payload": b"binary"})
        self.assertEqual(row[1], row["VALUE"])
        cursor = self.c.cursor()
        cursor.row_factory = None
        self.assertEqual(cursor.execute("SELECT id FROM balance").fetchone(), (1,))

    def test_commit_rollback_constraints_rowcount(self):
        cur = self.c.execute("INSERT INTO balance(id,value) VALUES(1,20)")
        self.assertEqual(cur.lastrowid, 1)
        self.c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.c:
                self.c.execute("UPDATE balance SET value=15 WHERE id=1")
                self.c.execute("INSERT INTO balance(id,value) VALUES(1,2)")
        self.assertEqual(self.c.execute("SELECT value FROM balance").fetchone()[0], 20)
        self.c.execute("BEGIN IMMEDIATE")
        self.assertEqual(self.c.execute("UPDATE balance SET value=value-5 WHERE value>=5").rowcount, 1)
        self.c.rollback()
        self.assertEqual(self.c.execute("SELECT value FROM balance").fetchone()[0], 20)

    def test_script_many_and_iteration(self):
        self.c.executescript("CREATE TABLE more(id INTEGER); INSERT INTO more VALUES(9);")
        self.c.executemany("INSERT INTO more VALUES(?)", [(10,), (11,)])
        self.c.commit()
        self.assertEqual(list(self.c.execute("SELECT * FROM more")), [(9,), (10,), (11,)])

    def test_fail_closed(self):
        with patch.dict(os.environ, {"DATABASE_BACKEND": "turso", "TURSO_AUTH_TOKEN": "", "TURSO_DATABASE_URL": "libsql://example.turso.io"}):
            with self.assertRaises(ValueError):
                db.connect(":memory:")
        with patch.dict(os.environ, {"DATABASE_BACKEND": "invalid"}):
            with self.assertRaises(ValueError):
                db.connect(":memory:")

    def test_snapshot_reopens_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            source = str(Path(folder) / "source.db")
            output = Path(folder) / "backup.db"
            c = db.Connection(libsql.connect(source))
            c.execute("CREATE TABLE test(id INTEGER PRIMARY KEY AUTOINCREMENT, value BLOB)")
            c.execute("INSERT INTO test(value) VALUES(?)", (b"ok",))
            c.commit()
            c.close()
            with patch.object(db, "remote_enabled", return_value=True), patch.object(db, "connect", side_effect=lambda _: db.Connection(libsql.connect(source))):
                db.snapshot(source, output)
            with closing(sqlite3.connect(output)) as restored:
                self.assertEqual(restored.execute("SELECT value FROM test").fetchone()[0], b"ok")
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")


class AsyncStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_connection_and_context_cursor(self):
        with patch.object(async_db, "sync_connect", side_effect=lambda *a, **k: db.Connection(libsql.connect(":memory:"))):
            async with async_db.connect("ignored") as c:
                c.row_factory = sqlite3.Row
                await c.execute("CREATE TABLE test(value INTEGER)")
                await c.execute("INSERT INTO test VALUES(?)", (7,))
                await c.commit()
                async with c.execute("SELECT value FROM test") as cursor:
                    self.assertEqual((await cursor.fetchone())["value"], 7)
                await c.execute("BEGIN IMMEDIATE")
                await c.execute("UPDATE test SET value=8")
                await c.rollback()
                self.assertEqual((await (await c.execute("SELECT value FROM test")).fetchone())[0], 7)


if __name__ == "__main__":
    unittest.main()
