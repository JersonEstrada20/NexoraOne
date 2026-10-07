import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from nexora.comandos import system_ops


class StatusReportTests(unittest.IsolatedAsyncioTestCase):
    def update(self):
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=7454664711),
            effective_message=SimpleNamespace(message_id=10, reply_text=AsyncMock()),
        )

    async def test_complete_report_does_not_expose_key(self):
        update = self.update()
        data = {'status': 'ok', 'storage': {'data_dir': '/data', 'items': [
            {'name': 'test.db', 'exists': True, 'in_data_dir': True, 'size': 42}]},
            'metrics': {'usuarios': {'total': 5}, 'solicitudes': {'pending': 2}}}
        with patch.object(system_ops, '_is_admin', return_value=True), \
             patch.object(system_ops, 'API_BASE', 'https://example.com'), \
             patch.object(system_ops, 'INTERNAL_API_KEY', 'test-secret-not-for-output'), \
             patch.object(system_ops, 'fetch_api_json_async', AsyncMock(return_value=(200, data))) as fetch:
            await system_ops.status_command(update, SimpleNamespace())
        fetch.assert_awaited_once_with('/health', timeout=15)
        update.effective_message.reply_text.assert_awaited_once()
        text = update.effective_message.reply_text.await_args.args[0]
        for section in ('STATUS', 'Usuarios', 'Keys', 'Solicitudes', 'Catálogo', 'Errores', 'test.db'):
            self.assertIn(section, text)
        self.assertIn('Key <code>OK</code>', text)
        self.assertNotIn('test-secret-not-for-output', text)

    async def test_missing_key_is_reported_without_name_error(self):
        update = self.update()
        with patch.object(system_ops, '_is_admin', return_value=True), \
             patch.object(system_ops, 'API_BASE', 'https://example.com'), \
             patch.object(system_ops, 'INTERNAL_API_KEY', ''), \
             patch.object(system_ops, 'fetch_api_json_async', AsyncMock(return_value=(200, {}))):
            await system_ops.status_command(update, SimpleNamespace())
        self.assertIn('Key <code>FALTA</code>', update.effective_message.reply_text.await_args.args[0])

    async def test_unavailable_web_returns_error_message(self):
        update = self.update()
        with patch.object(system_ops, '_is_admin', return_value=True), \
             patch.object(system_ops, 'API_BASE', 'https://example.com'), \
             patch.object(system_ops, 'fetch_api_json_async', AsyncMock(return_value=(503, {}))):
            await system_ops.status_command(update, SimpleNamespace())
        update.effective_message.reply_text.assert_awaited_once()

    async def test_other_user_cannot_query_health(self):
        update = self.update()
        with patch.object(system_ops, '_is_admin', return_value=False), \
             patch.object(system_ops, 'fetch_api_json_async', AsyncMock()) as fetch:
            await system_ops.status_command(update, SimpleNamespace())
        fetch.assert_not_called()
        self.assertIn('No tienes permisos', update.effective_message.reply_text.await_args.args[0])
