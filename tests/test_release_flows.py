import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import aiosqlite
from app.handlers import features, media, improvements, admin, suggestions
from app.handlers.menu import menu_keyboard
from app.services import database


class ReleaseFlows(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "test.db")
        self.patches = [patch.object(module, "DB_PATH", self.path) for module in
                        (features, media, improvements, database, suggestions)]
        for item in self.patches:
            item.start()
        await database.init_db()

    async def asyncTearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def message(self, user_id=11):
        return SimpleNamespace(from_user=SimpleNamespace(id=user_id, full_name="Persona", username=None),
            chat=SimpleNamespace(id=-1001, title="Grupo", type="supergroup"),
            message_id=5, reply_to_message=None, sender_chat=None, text="/daily",
            bot=AsyncMock(), reply=AsyncMock(), answer_video=AsyncMock())

    async def balance(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            return (await (await db.execute("SELECT coins FROM economy WHERE user_id=?", (user_id,))).fetchone())[0]

    async def test_daily_parallel_pays_once(self):
        message = self.message()
        await features._init_user(11, "Persona")
        with patch.object(features, "_animate", AsyncMock()), patch.object(features.random, "randint", return_value=100):
            await asyncio.gather(features.daily(message), features.daily(message))
        self.assertEqual(await self.balance(11), 200)

    async def test_double_purchase_charges_once(self):
        await features._init_user(11, "Persona")
        await features._change(11, coins=900)
        await asyncio.gather(*(features._buy_item(11, "Persona", -1001, "pico") for _ in range(2)))
        self.assertEqual(await self.balance(11), 850)
        self.assertEqual(await features._item_count(11, "pico"), 1)

    async def test_replayed_transfer_is_not_duplicated(self):
        message = self.message()
        await features.transfer(message, SimpleNamespace(args="22 30"))
        await features.transfer(message, SimpleNamespace(args="22 30"))
        self.assertEqual(await self.balance(11), 70)
        self.assertEqual(await self.balance(22), 130)

    async def test_regular_menu_hides_admin_and_owner_controls(self):
        callbacks = {b.callback_data for r in menu_keyboard(role="user").inline_keyboard for b in r}
        self.assertNotIn("mainmenu:settings", callbacks)
        self.assertNotIn("downloads:panel", callbacks)
        self.assertIn("mainmenu:downloads", callbacks)

    async def test_warn_by_id_preserves_reason(self):
        message = self.message()
        with patch.object(admin, "require_admin", AsyncMock(return_value=True)), \
             patch.object(admin, "is_admin", AsyncMock(return_value=False)), \
             patch.object(admin, "send_admin_log", AsyncMock()):
            await admin.cmd_warn(message, SimpleNamespace(args="22 spam repetido"))
        self.assertEqual(await database.get_warns(-1001, 22), 1)
        self.assertEqual(await database.get_warns(-1002, 22), 0)
        logs = await database.get_user_logs(-1001, 22)
        self.assertIn("spam repetido", logs[0][3])

    async def test_ticket_from_other_group_cannot_be_answered(self):
        case = await database.add_ticket(-1002, 22, "ayuda")
        message = self.message()
        with patch.object(improvements, "require_admin", AsyncMock(return_value=True)):
            await improvements.reply_ticket(message, SimpleNamespace(args=f"{case} hola"))
        message.bot.send_message.assert_not_awaited()

    async def test_removed_admin_cannot_save_settings(self):
        message = self.message()
        message.text = "Reglas nuevas"
        state = AsyncMock()
        state.get_data.return_value = {"chat_id": -1001}
        with patch.object(admin, "require_admin", AsyncMock(return_value=False)), \
             patch.object(admin, "set_rules_text", AsyncMock()) as save:
            await admin.save_panel_rules(message, state)
        save.assert_not_awaited()

    async def test_failed_suggestion_delivery_stays_open(self):
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("INSERT INTO suggestions(user_id,source_chat_id,text) VALUES(22,-1001,'idea')")
            case_id = cursor.lastrowid
            await db.commit()
        message = self.message(suggestions.OWNER_USER_ID)
        message.text = "Respuesta"
        message.bot.send_message.side_effect = RuntimeError("blocked")
        state = AsyncMock()
        state.get_data.return_value = {"suggestion_id": case_id}
        await suggestions.send_owner_reply(message, state)
        async with aiosqlite.connect(self.path) as db:
            status = (await (await db.execute("SELECT status FROM suggestions WHERE id=?", (case_id,))).fetchone())[0]
        self.assertEqual(status, "open")

    async def test_cancel_interrupts_upload_stage(self):
        job = "test-stage"
        media.ACTIVE_DOWNLOADS[11] = job
        task = asyncio.create_task(media._stage(job, asyncio.sleep(60)))
        await asyncio.sleep(0)
        try:
            self.assertTrue(media.cancel_user_download(11))
            with self.assertRaises(media.DownloadCancelled):
                await task
            self.assertNotIn(job, media.DOWNLOAD_STAGES)
        finally:
            media.ACTIVE_DOWNLOADS.pop(11, None)
            media.CANCELLED_DOWNLOADS.discard(job)

    async def test_telegram_cache_avoids_download(self):
        query = "https://vt.tiktok.com/test/"
        key = media._cache_key(query, False, "best") + "video"
        async with aiosqlite.connect(self.path) as db:
            await db.execute("CREATE TABLE telegram_media (cache_key TEXT PRIMARY KEY, file_id TEXT, title TEXT)")
            await db.execute("INSERT INTO telegram_media VALUES (?,?,?)", (key, "telegram-file", "Texto #tag"))
            await db.commit()
        message = self.message()
        with patch.object(media, "_has_free_downloads", AsyncMock(return_value=True)), \
             patch.object(media, "_download_process", AsyncMock()) as download:
            await media._send_download(message, query, quality="best", requester_id=11)
        download.assert_not_awaited()
        message.answer_video.assert_awaited_once_with("telegram-file", caption="🎬 Texto #tag")
        self.assertNotIn(11, media.ACTIVE_DOWNLOADS)
