import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.handlers import admin


class BanTargetsTests(unittest.IsolatedAsyncioTestCase):
    async def test_id_and_reason_without_reply(self):
        message = SimpleNamespace(reply_to_message=None, chat=SimpleNamespace(id=-1001),
                                  from_user=SimpleNamespace(id=42), bot=AsyncMock(), reply=AsyncMock())
        with patch.object(admin, "require_admin", AsyncMock(return_value=True)), \
             patch.object(admin, "is_admin", AsyncMock(return_value=False)), \
             patch.object(admin, "add_log", AsyncMock()) as log:
            await admin.cmd_ban(message, SimpleNamespace(args="123456 spam repetido"))
        message.bot.ban_chat_member.assert_awaited_once_with(-1001, 123456)
        self.assertEqual(log.await_args.kwargs["reason"], "spam repetido")

    async def test_id_without_reason_offers_buttons(self):
        message = SimpleNamespace(reply_to_message=None, chat=SimpleNamespace(id=-1001),
                                  from_user=SimpleNamespace(id=42), bot=AsyncMock(), reply=AsyncMock())
        with patch.object(admin, "require_admin", AsyncMock(return_value=True)), \
             patch.object(admin, "is_admin", AsyncMock(return_value=False)):
            await admin.cmd_ban(message, SimpleNamespace(args="123456"))
        message.bot.ban_chat_member.assert_not_awaited()
        keyboard = message.reply.await_args.kwargs["reply_markup"]
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "banreason:123456:spam")
