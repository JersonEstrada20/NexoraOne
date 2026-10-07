import json
import importlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock
from types import SimpleNamespace

import aiosqlite

from app.config import BACKUP_CHAT_ID, OWNER_USER_ID
from app.handlers.menu import SECTIONS, EN_SECTIONS, menu_keyboard
from app.handlers.media import (
    _direct_keyboard,
    _friendly_download_error,
    _format_duration,
    _history_actions,
    _is_tiktok_asset_url,
    _is_tiktok_url,
)
from app.handlers import media
from app.handlers.automation import _relative
from app.handlers import automation, community
from app.handlers.config_transfer import build_group_export
from app.handlers.maintenance import _validate_restore
from app.services import backups, database
from app.services.group_tools import normalize_name
from app.services.templates import render_group_template


class MenuTests(unittest.TestCase):
    def test_all_sections_have_a_button(self):
        callbacks = {
            button.callback_data
            for row in menu_keyboard().inline_keyboard
            for button in row
        }
        self.assertTrue(
            {f"mainmenu:{section}" for section in SECTIONS}.issubset(callbacks)
        )

    def test_submenu_can_return_home(self):
        callbacks = {
            button.callback_data
            for row in menu_keyboard("downloads").inline_keyboard
            for button in row
        }
        self.assertIn("mainmenu:home", callbacks)

    def test_home_has_suggestion_button(self):
        callbacks = {
            button.callback_data
            for row in menu_keyboard().inline_keyboard
            for button in row
        }
        self.assertIn("suggest:start", callbacks)

    def test_telegram_text_limits(self):
        self.assertTrue(all(len(text) < 4096 for text in SECTIONS.values()))
        self.assertTrue(all(len(text) < 4096 for text in EN_SECTIONS.values()))

    def test_english_menu_has_every_section(self):
        callbacks = {button.callback_data for row in menu_keyboard(language="en").inline_keyboard for button in row}
        self.assertTrue({f"mainmenu:{section}" for section in EN_SECTIONS}.issubset(callbacks))

    def test_admin_tools_are_reached_from_the_single_menu(self):
        callbacks = {button.callback_data for row in menu_keyboard("settings").inline_keyboard for button in row}
        self.assertIn("unified:0:paneladmin", callbacks)
        self.assertNotIn("panel:home", callbacks)
        self.assertNotIn("center:home", callbacks)

    def test_download_panel_is_reached_from_the_single_menu(self):
        callbacks = {button.callback_data for row in menu_keyboard("downloads", role="owner").inline_keyboard for button in row}
        self.assertIn("downloads:panel", callbacks)


class ModuleTests(unittest.TestCase):
    def test_all_runtime_modules_import(self):
        modules = (
            "app.main",
            "app.handlers.admin",
            "app.handlers.features",
            "app.handlers.general",
            "app.handlers.media",
            "app.handlers.maintenance",
            "app.handlers.suggestions",
            "app.handlers.menu",
            "app.handlers.moderation",
            "app.handlers.automation",
            "app.handlers.community",
            "app.handlers.config_transfer",
            "app.services.admin_logs",
            "app.services.backups",
            "app.services.database",
            "app.services.diagnostics",
            "app.services.filters",
            "app.services.templates",
            "app.services.access",
            "app.services.cleanup",
            "app.services.group_tools",
        )
        for module in modules:
            with self.subTest(module=module):
                importlib.import_module(module)


class BackupTests(unittest.TestCase):
    def test_owner_channel_is_the_only_default_destination(self):
        self.assertEqual(-1004334720154, BACKUP_CHAT_ID)

    def test_backup_creates_searchable_group_index(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "bot.db"
            connection = sqlite3.connect(db_path)
            connection.execute(
                "CREATE TABLE group_settings (chat_id INTEGER PRIMARY KEY, rules_text TEXT)"
            )
            connection.execute(
                "INSERT INTO group_settings VALUES (?, ?)",
                (-1001234567890, "Reglas de prueba"),
            )
            connection.commit()
            connection.close()

            with patch.object(backups, "DB_PATH", str(db_path)), patch.object(
                backups, "BACKUP_DIR", Path(directory) / "backups"
            ):
                backup_path, index_path = backups._create_backup()

            self.assertTrue(backup_path.exists())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            group = index["groups"]["-1001234567890"]
            self.assertEqual("Reglas de prueba", group["rules_text"])


class MaintenanceTests(unittest.TestCase):
    def test_owner_id_is_configured(self):
        self.assertEqual(7454664711, OWNER_USER_ID)
        from app.handlers import maintenance
        self.assertEqual(OWNER_USER_ID, maintenance.OWNER_USER_ID)

    def test_restore_rejects_an_unrelated_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unrelated.db"
            sqlite3.connect(path).close()
            with self.assertRaisesRegex(ValueError, "copia válida"):
                _validate_restore(path)

    def test_download_errors_are_safe_and_clear(self):
        self.assertIn("privado", _friendly_download_error(RuntimeError("Video is private")))
        self.assertIn("límite de Telegram", _friendly_download_error(RuntimeError("File is too big")))

    def test_video_search_uses_video_selection_buttons(self):
        results = [{"id": "abc123", "title": "Video", "channel": "Canal", "duration_text": "3:20"}]
        text, markup = media._search_menu(results, "token1", 0, "video")
        self.assertIn("Elige un video", text)
        self.assertEqual("media:select:token1:abc123", markup.inline_keyboard[0][0].callback_data)

    def test_duration_formatter_handles_real_seconds(self):
        self.assertEqual("4:25", _format_duration(265))
        self.assertEqual("1:02:03", _format_duration(3723))
        self.assertEqual("?:??", _format_duration(None))

    def test_download_size_formatter_is_readable(self):
        self.assertEqual("1.0 MB", media._format_bytes(1024 * 1024))
        self.assertEqual("?", media._format_bytes("NA"))

    def test_profile_card_generates_a_png(self):
        from app.handlers.features import _profile_card
        row = {"name": "Tester", "coins": 250, "xp": 125}
        data = _profile_card(row, 4, False)
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_expired_media_requests_are_removed(self):
        now = media.monotonic()
        media.MEDIA_REQUESTS.clear()
        media.SEARCH_CACHE.clear()
        media.MEDIA_REQUESTS["old"] = {"_created_at": now - media.REQUEST_TTL_SECONDS - 1}
        media.MEDIA_REQUESTS["new"] = {"_created_at": now}
        media._expire_memory_requests()
        self.assertNotIn("old", media.MEDIA_REQUESTS)
        self.assertIn("new", media.MEDIA_REQUESTS)
        media.MEDIA_REQUESTS.clear()

    def test_download_action_buttons_reference_the_history_owner_record(self):
        callbacks = [button.callback_data for row in _history_actions(42).inline_keyboard for button in row]
        self.assertEqual(["media:favorite:42", "media:repeat:42"], callbacks)

    def test_tiktok_links_are_detected_without_accepting_impostor_domains(self):
        self.assertTrue(_is_tiktok_url("https://vt.tiktok.com/ABC/"))
        self.assertTrue(_is_tiktok_url("https://www.tiktok.com/@user/video/123"))
        self.assertFalse(_is_tiktok_url("https://tiktok.com.example.org/falso"))
        self.assertTrue(_is_tiktok_asset_url("https://p16.tiktokcdn-us.com/photo.jpeg"))
        self.assertFalse(_is_tiktok_asset_url("https://example.org/photo.jpeg"))

    def test_instagram_links_and_assets_reject_impostor_domains(self):
        self.assertTrue(media._is_instagram_url("https://www.instagram.com/p/ABC/"))
        self.assertFalse(media._is_instagram_url("https://instagram.com.example.org/p/ABC/"))
        self.assertTrue(media._is_instagram_asset_url("https://scontent.cdninstagram.com/file.jpg"))
        self.assertFalse(media._is_instagram_asset_url("https://example.org/file.jpg"))

    def test_instagram_extractor_keeps_only_trusted_unique_assets(self):
        output = "\n".join([
            "https://scontent.cdninstagram.com/one.jpg",
            "https://scontent.cdninstagram.com/one.jpg",
            "https://video.fbcdn.net/two.mp4",
            "https://example.org/unsafe.jpg",
        ])
        result = SimpleNamespace(stdout=output, stderr="", returncode=0)
        with patch.object(media.subprocess, "run", return_value=result):
            urls = media._extract_instagram_urls("https://www.instagram.com/p/ABC/")
        self.assertEqual([
            "https://scontent.cdninstagram.com/one.jpg",
            "https://video.fbcdn.net/two.mp4",
        ], urls)

    def test_three_download_workers_are_available(self):
        self.assertEqual(3, media.DOWNLOAD_SEMAPHORE._value)

    def test_tiktok_direct_menu_does_not_offer_fake_quality_choices(self):
        markup = _direct_keyboard("abc", carousel=False)
        buttons = [button for row in markup.inline_keyboard for button in row]
        self.assertEqual(["📥 Descargar video", "❌ Cancelar"], [button.text for button in buttons])
        self.assertEqual(["media:direct:abc", "media:dismiss:abc"], [button.callback_data for button in buttons])

    def test_tiktok_carousel_menu_offers_photo_download(self):
        markup = _direct_keyboard("abc", carousel=True)
        self.assertEqual("🖼 Descargar fotos", markup.inline_keyboard[0][0].text)
        self.assertEqual("media:carousel:abc", markup.inline_keyboard[0][0].callback_data)

    def test_schedule_duration_parser(self):
        self.assertEqual(1800, _relative("30m"))
        self.assertEqual(604800, _relative("7d"))
        self.assertIsNone(_relative("tomorrow"))

    def test_custom_names_are_safely_normalized(self):
        self.assertEqual("reglas_grupo", normalize_name("/Reglas_Grupo !!!"))


class DownloadAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_free_download_access_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "bot.db")
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE download_exemptions (user_id INTEGER PRIMARY KEY)")
            connection.execute("INSERT INTO download_exemptions VALUES (999)")
            connection.commit()
            connection.close()
            with patch.object(media, "DB_PATH", db_path):
                self.assertTrue(await media._has_free_downloads(7454664711))
                self.assertTrue(await media._has_free_downloads(999))
                self.assertFalse(await media._has_free_downloads(123))

    async def test_owner_is_unlimited_even_without_database_access(self):
        with patch.object(media, "DB_PATH", "Z:/ruta/que/no/existe/bot.db"):
            self.assertTrue(await media._has_free_downloads(7454664711))

    async def test_history_records_cannot_be_repeated_by_another_user(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "media.db")
            cache_dir = Path(directory) / "cache"
            with patch.object(media, "DB_PATH", db_path), patch.object(media, "CACHE_DIR", cache_dir):
                await media._init_media_storage()
                history_id = await media._add_history(100, -1, "https://youtu.be/test", True, "192", "Canción", "success")
                owner_item = await media._history_item(history_id, 100)
                stranger_item = await media._history_item(history_id, 200)
            self.assertIsNotNone(owner_item)
            self.assertIsNone(stranger_item)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_settings_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "bot.db")
            with patch.object(database, "DB_PATH", db_path):
                await database.init_db()
                await database.ensure_group(-1001)
                await database.ensure_group(-1002)
                await database.set_rules_text(-1001, "Reglas del grupo uno")
                first = await database.get_settings(-1001)
                second = await database.get_settings(-1002)
                async with aiosqlite.connect(db_path) as db:
                    suggestion_table = await (await db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='suggestions'"
                    )).fetchone()
                    exemptions_table = await (await db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='download_exemptions'"
                    )).fetchone()
                    policy = await (await db.execute(
                        "SELECT max_downloads,window_seconds,parallel_downloads FROM download_policy WHERE id=1"
                    )).fetchone()

            self.assertEqual("Reglas del grupo uno", first["rules_text"])
            self.assertNotEqual(first["rules_text"], second["rules_text"])
            self.assertIsNotNone(suggestion_table)
            self.assertIsNotNone(exemptions_table)
            self.assertEqual((3, 600, 3), policy)

    async def test_new_features_work_on_a_fresh_database(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "fresh.db")
            with patch.object(database, "DB_PATH", db_path):
                await database.init_db()
                await database.ensure_group(-2001)
                await database.set_language(-2001, "en")
                await database.set_auto_delete_seconds(-2001, 15)
                await database.set_required_channel(-2001, "@ExampleChannel")
                settings = await database.get_settings(-2001)
                async with aiosqlite.connect(db_path) as db:
                    tables = {row[0] for row in await (await db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )).fetchall()}
            self.assertEqual("en", settings["language"])
            self.assertEqual(15, settings["auto_delete_seconds"])
            self.assertEqual("@ExampleChannel", settings["required_channel"])
            self.assertTrue({"media_favorites", "scheduled_messages", "giveaways", "group_activity_daily", "economy_missions"}.issubset(tables))

    async def test_group_export_contains_rules_and_notes(self):
        from app.handlers import config_transfer
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "export.db")
            with patch.object(database, "DB_PATH", db_path), patch.object(config_transfer, "DB_PATH", db_path):
                await database.init_db()
                await database.ensure_group(-3001)
                await database.set_rules_text(-3001, "Reglas de {group}")
                async with aiosqlite.connect(db_path) as db:
                    await db.execute("INSERT INTO group_notes(chat_id,name,content,created_by) VALUES(?,?,?,?)", (-3001, "info", "Texto", 1))
                    await db.commit()
                payload = await build_group_export(-3001)
            self.assertEqual("doxertube-group-config-v1", payload["format"])
            self.assertEqual("Reglas de {group}", payload["settings"]["rules_text"])
            self.assertEqual("info", payload["tables"]["group_notes"][0]["name"])


class TemplateTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_name_placeholder_is_rendered_in_rules(self):
        bot = SimpleNamespace(get_chat_member_count=AsyncMock(return_value=321))
        chat = SimpleNamespace(id=-1001, title="Doxer Perú")
        user = SimpleNamespace(id=7, full_name="Juan", username="juan")
        rendered = await render_group_template(bot, chat, user, "#{group} · {members} · {name}")
        self.assertEqual("#Doxer Perú · 321 · Juan", rendered)


class RestartRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_due_schedule_is_sent_after_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "schedule.db")
            with patch.object(database, "DB_PATH", db_path), patch.object(automation, "DB_PATH", db_path):
                await database.init_db()
                due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
                async with aiosqlite.connect(db_path) as db:
                    await db.execute("INSERT INTO scheduled_messages(chat_id,text,next_run,created_by) VALUES(?,?,?,?)", (-10, "Prueba", due, 1))
                    await db.commit()
                bot = SimpleNamespace(send_message=AsyncMock())
                await automation.process_due_schedules(bot)
                async with aiosqlite.connect(db_path) as db:
                    enabled = (await (await db.execute("SELECT enabled FROM scheduled_messages")).fetchone())[0]
            bot.send_message.assert_awaited_once_with(-10, "📢 Prueba")
            self.assertEqual(0, enabled)

    async def test_expired_giveaway_is_closed_after_a_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / "giveaway.db")
            with patch.object(database, "DB_PATH", db_path), patch.object(community, "DB_PATH", db_path):
                await database.init_db()
                due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
                async with aiosqlite.connect(db_path) as db:
                    cursor = await db.execute("INSERT INTO giveaways(chat_id,message_id,prize,created_by,ends_at) VALUES(?,?,?,?,?)", (-10, 5, "Premio", 1, due))
                    giveaway_id = cursor.lastrowid
                    await db.execute("INSERT INTO giveaway_entries(giveaway_id,user_id) VALUES(?,?)", (giveaway_id, 77))
                    await db.commit()
                bot = SimpleNamespace(edit_message_text=AsyncMock(), send_message=AsyncMock())
                await community.process_expired_giveaways(bot)
                async with aiosqlite.connect(db_path) as db:
                    status, winner = await (await db.execute("SELECT status,winner_id FROM giveaways WHERE id=?", (giveaway_id,))).fetchone()
            self.assertEqual("closed", status)
            self.assertEqual(77, winner)
            bot.edit_message_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
