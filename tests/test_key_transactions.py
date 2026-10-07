"""Exercise the real route without importing web.py or touching live secrets."""
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import libsql
from flask import Flask, jsonify, request
from nexora.db import Connection


class KeyTransactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.failure = None
        self.commits = 0
        with closing(sqlite3.connect(self.path)) as c:
            c.executescript('''
                CREATE TABLE usuarios(id_tg TEXT PRIMARY KEY,creditos INTEGER,fecha_caducidad TEXT);
                CREATE TABLE keys(key TEXT PRIMARY KEY,tipo TEXT,cantidad INTEGER,usos INTEGER);
                CREATE TABLE redemptions(key TEXT,user_id INTEGER);
                INSERT INTO usuarios VALUES('123',5,NULL);
                INSERT INTO keys VALUES('TEST','creditos',10,1);
            ''')
        app = Flask(__name__)
        app.testing = True
        def user(_):
            with closing(sqlite3.connect(self.path)) as c:
                c.row_factory = sqlite3.Row
                return c.execute('SELECT * FROM usuarios').fetchone()
        env = dict(app=app, jsonify=jsonify, request_value=lambda k: request.json.get(k),
                   require_internal_access=lambda: None, get_user_by_id=user,
                   init_keys_db=lambda: None, get_conn=self.connect,
                   KEYS_DB_PATH=self.path, remote_enabled=lambda: True,
                   record_purchase_event=lambda **k: 1, log_audit_event=lambda *a, **k: None,
                   bot_actor=lambda: 'test', sqlite3=sqlite3)
        tree = ast.parse(Path('nexora/web.py').read_text(encoding='utf-8'))
        routes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('keys_redeem', 'cred')]
        exec(compile(ast.Module(body=routes, type_ignores=[]), 'transaction_routes', 'exec'), env)
        self.client = app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def connect(self, *args):
        connection = Connection(libsql.connect(self.path))
        commit = connection.commit
        def faulty_commit():
            self.commits += 1
            if self.failure == 'before':
                raise sqlite3.OperationalError('Simulated connection failure')
            commit()
            if self.failure == 'after':
                raise sqlite3.OperationalError('Simulated lost commit acknowledgement')
        connection.commit = faulty_commit
        return connection

    def redeem(self):
        return self.client.post('/keys/redeem', json={'key': 'TEST', 'ID_TG': '123'})

    def state(self):
        with closing(sqlite3.connect(self.path)) as c:
            return (c.execute('SELECT creditos FROM usuarios').fetchone()[0],
                    c.execute('SELECT usos FROM keys').fetchone()[0],
                    c.execute('SELECT count(*) FROM redemptions').fetchone()[0])

    def test_repeated_redemption_pays_once(self):
        self.assertEqual(self.redeem().status_code, 200)
        self.assertEqual(self.redeem().status_code, 409)
        self.assertEqual(self.state(), (15, 0, 1))
        self.assertEqual(self.commits, 1)

    def test_failure_before_commit_rolls_everything_back(self):
        self.failure = 'before'
        self.assertEqual(self.redeem().status_code, 500)
        self.assertEqual(self.state(), (5, 1, 0))
        self.assertEqual(self.commits, 1)
        self.failure = None
        self.assertEqual(self.redeem().status_code, 200)
        self.assertEqual(self.state(), (15, 0, 1))

    def test_lost_commit_ack_does_not_repeat_credit(self):
        self.failure = 'after'
        self.assertEqual(self.redeem().status_code, 500)
        self.assertEqual(self.state(), (15, 0, 1))
        self.failure = None
        self.assertEqual(self.redeem().status_code, 409)
        self.assertEqual(self.commits, 1)
        self.assertEqual(self.state(), (15, 0, 1))

    def test_admin_credit_change_commits_once(self):
        response = self.client.post('/cred', json={'ID_TG': '123', 'operacion': 'sumar', 'cantidad': 7})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.state()[0], 12)
        self.assertEqual(self.commits, 1)

    def test_admin_lost_ack_reports_uncertain_without_retry(self):
        self.failure = 'after'
        response = self.client.post('/cred', json={'ID_TG': '123', 'operacion': 'sumar', 'cantidad': 7})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.state()[0], 12)
        self.assertEqual(self.commits, 1)
