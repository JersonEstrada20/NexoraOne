import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from nexora.comandos.admin_requests import _send_delivery_message


class RequestDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_receipt_is_not_edited(self):
        row = [None] * 24
        row[1] = 123
        row[19:24] = [-100123, 45, 'supergroup', -100123, 46]
        bot = AsyncMock()
        await _send_delivery_message(SimpleNamespace(bot=bot), row, 'Respuesta de prueba')
        bot.send_message.assert_awaited_once_with(
            chat_id=-100123, text='Respuesta de prueba', parse_mode='HTML',
            reply_to_message_id=45, allow_sending_without_reply=True)
        bot.edit_message_text.assert_not_called()
        bot.edit_message_caption.assert_not_called()
        bot.delete_message.assert_not_called()

    async def test_legacy_request_delivers_to_user(self):
        bot = AsyncMock()
        await _send_delivery_message(SimpleNamespace(bot=bot), [1, 123], 'Finalizado')
        bot.send_message.assert_awaited_once_with(
            chat_id=123, text='Finalizado', parse_mode='HTML')

    async def test_each_reply_is_a_new_message(self):
        bot = AsyncMock()
        context = SimpleNamespace(bot=bot)
        await _send_delivery_message(context, [1, 123], 'Primera respuesta')
        await _send_delivery_message(context, [1, 123], 'Segunda respuesta')
        self.assertEqual(bot.send_message.await_count, 2)
        bot.edit_message_text.assert_not_called()

    async def test_delivery_error_is_not_silently_ignored(self):
        bot = AsyncMock()
        bot.send_message.side_effect = RuntimeError('test failure')
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            await _send_delivery_message(SimpleNamespace(bot=bot), [1, 123], 'Respuesta')
