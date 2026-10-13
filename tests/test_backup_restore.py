"""Test the destructive restore route only against an isolated temporary database."""
import ast
from contextlib import closing
import io
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import zipfile

from flask import Flask, redirect, request, url_for


class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "multiplataforma.db"
        self.safety = Path(self.temp.name) / "nexora-before-restore-test.db"
        self._write_database(self.target, "original")
        self.backup_created = False

        app = Flask(__name__)
        app.testing = True
        app.add_url_rule("/admin/panel", "admin_panel", lambda: "ok")
        env = {
            "require_panel_roles": lambda *_: None,
            "remote_enabled": lambda: False,
            "request": request,
            "redirect": redirect,
            "url_for": url_for,
            "get_storage_snapshot": lambda: {"items": [{"path": str(self.target)}]},
            "zipfile": zipfile,
            "os": os,
            "shutil": shutil,
            "sqlite3": sqlite3,
            "log_audit_event": lambda *args, **kwargs: None,
            "create_named_db_backup": self._create_safety_backup,
        }
        tree = ast.parse(Path("nexora/web.py").read_text(encoding="utf-8"))
        route = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "admin_restore_db_backup"
        )
        route.decorator_list = []
        exec(compile(ast.Module(body=[route], type_ignores=[]), "restore_route", "exec"), env)
        cleanup_route = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "admin_cleanup_history"
        )
        cleanup_route.decorator_list = []
        exec(compile(ast.Module(body=[cleanup_route], type_ignores=[]), "cleanup_route", "exec"), env)
        self.restore_handler = env["admin_restore_db_backup"]
        self.cleanup_handler = env["admin_cleanup_history"]
        app.add_url_rule("/restore", "restore", self.restore_handler, methods=["POST"])
        self.client = app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _write_database(path, value):
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS sample(value TEXT)")
            conn.execute("DELETE FROM sample")
            conn.execute("INSERT INTO sample(value) VALUES(?)", (value,))
            conn.commit()

    def _create_safety_backup(self, prefix):
        self.backup_created = True
        shutil.copy2(self.target, self.safety)
        return str(self.safety)

    def _zip(self, content):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(self.target.name, content)
        stream.seek(0)
        return stream

    @staticmethod
    def _read_value(path):
        with closing(sqlite3.connect(path)) as conn:
            return conn.execute("SELECT value FROM sample").fetchone()[0]

    def test_valid_backup_restores_and_keeps_pre_restore_copy(self):
        replacement = Path(self.temp.name) / "replacement.db"
        self._write_database(replacement, "restored")
        uploaded = self._zip(replacement.read_bytes())
        response = self.client.post(
            "/restore",
            data={"confirm": "RESTAURAR", "backup_zip": (uploaded, "backup.zip")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._read_value(self.target), "restored")
        self.assertEqual(self._read_value(self.safety), "original")
        self.assertTrue(self.backup_created)

    def test_invalid_database_is_rejected_without_touching_target(self):
        uploaded = self._zip(b"not a sqlite database")
        response = self.client.post(
            "/restore",
            data={"confirm": "RESTAURAR", "backup_zip": (uploaded, "bad.zip")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._read_value(self.target), "original")
        self.assertFalse(self.backup_created)

    def test_restore_requires_founder_role(self):
        roles = []
        self.restore_handler.__globals__["require_panel_roles"] = lambda *args: roles.extend(args) or "denied"
        self.assertEqual(self.restore_handler(), "denied")
        self.assertEqual(roles, ["FUNDADOR"])
        self.assertFalse(self.backup_created)

    def test_history_cleanup_requires_founder_role(self):
        roles = []
        self.cleanup_handler.__globals__["require_panel_roles"] = lambda *args: roles.extend(args) or "denied"
        self.assertEqual(self.cleanup_handler(), "denied")
        self.assertEqual(roles, ["FUNDADOR"])


if __name__ == "__main__":
    unittest.main()
