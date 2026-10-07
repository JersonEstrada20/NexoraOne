import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import bans
from nexora.runtime import COMMANDS

class CommandContract(unittest.TestCase):
    def test_unique_entry_points(self):
        entries = {}
        for path in Path('app/handlers').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Command':
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            entries.setdefault(arg.value, []).append(str(path))
        for name in ('register','perfil','paneladmin','backup','historial','ban','unban','bang','unbang','bangg','unbangg'):
            self.assertEqual(len(entries.get(name,[])),1,name)
        for name in ('reg','registrarme','rg','cartera','minivel','nivel','panel','admin','helpadmin','cmdsadmin','backupnow','cmds'):
            self.assertNotIn(name, entries)
        self.assertFalse(set(entries) & set(COMMANDS), 'Service command collision')

class PersistentBans(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'test.db'
        self.patcher = patch.object(bans,'DB_PATH',str(self.path))
        self.patcher.start()
        await bans.init_bans()

    async def asyncTearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    async def test_global_cannot_be_downgraded(self):
        await bans.set_ban(123,'spam',True)
        await bans.set_ban(123,'other',False)
        self.assertEqual((await bans.banned(123))[1],1)
        await bans.record(123,-1001)
        await bans.record(123,-1001)
        self.assertEqual(await bans.targets(123),[-1001])
        await bans.record(123,-1001,remove=True)
        self.assertEqual(await bans.targets(123),[])
        await bans.clear_ban(123)
        self.assertIsNone(await bans.banned(123))

    async def test_blocked_actor_cannot_call_handler(self):
        from types import SimpleNamespace
        await bans.set_ban(123,'spam')
        handler = AsyncMock()
        event = SimpleNamespace(from_user=SimpleNamespace(id=123))
        await bans.BanMiddleware()(handler,event,{})
        handler.assert_not_awaited()

if __name__ == '__main__':
    unittest.main()
