import unittest
import tempfile
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from telegram.error import NetworkError
from nexora.comandos import admin_requests
from nexora.request_history import parse_request_history

from nexora.comandos.admin_requests import (
    RequestChargeError,
    RequestDeliveryUncertain,
    _maybe_charge_request,
    _send_delivery_message,
)


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


class UncertainDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def _create_request(self, db_path):
        admin_requests.init_db()
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO requests(user_id,command,payload,status,cost,created_at) VALUES(?,?,?,?,?,?)",
            (123, "lookup", "query", "pending", 2, "2026-10-13T10:00:00Z"),
        )
        request_id = cur.lastrowid
        conn.commit()
        row = admin_requests._get_request_by_id(cur, request_id)
        conn.close()
        return request_id, row

    async def test_uncertain_delivery_blocks_request_and_records_message_and_charge(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            admin_requests, "DB_FILE", str(Path(directory) / "requests.db")
        ):
            request_id, row = self._create_request(admin_requests.DB_FILE)

            await admin_requests._mark_delivery_uncertain(row, "mensaje enviado", author_id=99, charged=1)

            conn = sqlite3.connect(admin_requests.DB_FILE)
            status, charged, history = conn.execute(
                "SELECT status, charged, resolution_note FROM requests WHERE id = ?", (request_id,)
            ).fetchone()
            conn.close()
            self.assertEqual("delivery_uncertain", status)
            self.assertEqual(1, charged)
            events = parse_request_history(history)
            self.assertEqual("delivery_uncertain", events[-1]["kind"])
            self.assertIn("[cobro_confirmado=1]", events[-1]["text"])

    async def test_network_error_is_recorded_before_it_reaches_admin(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            admin_requests, "DB_FILE", str(Path(directory) / "requests.db")
        ):
            request_id, row = self._create_request(admin_requests.DB_FILE)
            bot = AsyncMock()
            bot.send_message.side_effect = NetworkError("connection reset")
            with self.assertRaises(RequestDeliveryUncertain):
                await admin_requests._send_delivery_message(
                    SimpleNamespace(bot=bot), row, "respuesta", author_id=99, charged=1
                )

            conn = sqlite3.connect(admin_requests.DB_FILE)
            status = conn.execute("SELECT status FROM requests WHERE id = ?", (request_id,)).fetchone()[0]
            conn.close()
            self.assertEqual("delivery_uncertain", status)


class RequestChargeTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_debit_blocks_billable_response(self):
        with patch('nexora.comandos.utils.verificar_usuario_async', new=AsyncMock(return_value=(True, {'ilimitado': False}))), \
             patch('nexora.comandos.utils.descontar_creditos_async', new=AsyncMock(return_value=(False, {}))) as debit:
            with self.assertRaises(RequestChargeError):
                await _maybe_charge_request(None, 42, 123, 3, 0)
        debit.assert_awaited_once_with('123', 3, operation_id='request:42:billable-response')

    async def test_insufficient_balance_has_clear_reason(self):
        with patch('nexora.comandos.utils.verificar_usuario_async', new=AsyncMock(return_value=(True, {'ilimitado': False}))), \
             patch('nexora.comandos.utils.descontar_creditos_async', new=AsyncMock(return_value=(
                 False, {'message': 'Créditos insuficientes para confirmar el descuento'}
             ))):
            with self.assertRaisesRegex(RequestChargeError, 'créditos suficientes'):
                await _maybe_charge_request(None, 42, 123, 3, 0)

    async def test_successful_debit_uses_persistent_operation_key(self):
        with patch('nexora.comandos.utils.verificar_usuario_async', new=AsyncMock(return_value=(True, {'ilimitado': False}))), \
             patch('nexora.comandos.utils.descontar_creditos_async', new=AsyncMock(return_value=(True, {}))) as debit:
            self.assertEqual(await _maybe_charge_request(None, 42, 123, 3, 0), 1)
        debit.assert_awaited_once_with('123', 3, operation_id='request:42:billable-response')

    async def test_already_charged_request_does_not_call_credit_api(self):
        with patch('nexora.comandos.utils.verificar_usuario_async', new=AsyncMock()) as verify, \
             patch('nexora.comandos.utils.descontar_creditos_async', new=AsyncMock()) as debit:
            self.assertEqual(await _maybe_charge_request(None, 42, 123, 3, 1), 1)
        verify.assert_not_awaited()
        debit.assert_not_awaited()
