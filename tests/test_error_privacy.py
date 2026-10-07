import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from aiogram.types import Message, Chat, User
from nexora.runtime import ServiceRuntime, COMMANDS
from app.config import OWNER_USER_ID
from nexora.comandos.bot_errors import api_error_text


class ErrorPrivacyTests(unittest.TestCase):
    def test_server_and_auth_errors_hide_raw_details(self):
        for status in (401, 403, 500, 503, 599):
            with self.subTest(status=status):
                result = api_error_text('consultar estado', status, {'message': 'PRIVATE_TOKEN_PERSONAL_DATA'})
                self.assertNotIn('PRIVATE_TOKEN_PERSONAL_DATA', result)
                self.assertNotIn('Railway', result)

    def test_user_validation_errors_are_html_escaped(self):
        result = api_error_text('validar', 400, {'message': '<invalid>'})
        self.assertIn('&lt;invalid&gt;', result)


class RuntimeErrorPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_error_reference_matches_log_without_leaking_exception(self):
        runtime = ServiceRuntime()
        runtime.application = SimpleNamespace(bot=None)
        message = Message(message_id=1, date=datetime.now(timezone.utc),
                          chat=Chat(id=OWNER_USER_ID, type='private'),
                          from_user=User(id=OWNER_USER_ID, is_bot=False, first_name='Test'),
                          text='/status')
        reply = AsyncMock()
        update = SimpleNamespace(effective_message=SimpleNamespace(text='/status', reply_text=reply))
        handler = AsyncMock(side_effect=RuntimeError('SECRET_PRIVATE_PAYLOAD'))
        with patch.dict(COMMANDS, {'status': handler}), \
             patch('nexora.runtime.Update.de_json', return_value=update), \
             patch('nexora.runtime.CallbackContext.from_update', return_value=SimpleNamespace(args=[])), \
             self.assertLogs(level='ERROR') as logs:
            await runtime.invoke(message)
        text = reply.await_args.args[0]
        self.assertRegex(text, r'Referencia: [0-9A-F]{8}')
        reference = text.split('Referencia: ')[1].split('.')[0]
        self.assertIn(reference, logs.output[0])
        self.assertNotIn('SECRET_PRIVATE_PAYLOAD', text + logs.output[0])
