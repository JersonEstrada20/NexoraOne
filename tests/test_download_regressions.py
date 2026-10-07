import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.methods import SendVideo, SendAudio, SendDocument
from aiogram.types import Message, Chat, User
from app.handlers import media
from nexora.runtime import ADMIN, COMMANDS, ServiceRuntime
from nexora.comandos import system_ops


class DownloadRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_aiogram_awaitables_are_accepted(self):
        for method, field in ((SendVideo, 'video'), (SendAudio, 'audio'),
                              (SendDocument, 'document')):
            with self.subTest(method=method.__name__):
                bot = AsyncMock(return_value='sent')
                operation = method(chat_id=123, **{field: 'file-id'}).as_(bot)
                self.assertEqual(await media._stage('send-test', operation), 'sent')
                bot.assert_awaited_once_with(operation)
                self.assertNotIn('send-test', media.DOWNLOAD_STAGES)

    async def test_cancellation_stops_awaitable_and_cleans_stage(self):
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def send(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        operation = SendVideo(chat_id=123, video='id').as_(AsyncMock(side_effect=send))
        media.ACTIVE_DOWNLOADS[123] = 'cancel-test'
        task = asyncio.create_task(media._stage('cancel-test', operation))
        try:
            await asyncio.wait_for(started.wait(), 1)
            self.assertTrue(media.cancel_user_download(123))
            with self.assertRaises(media.DownloadCancelled):
                await task
            self.assertTrue(stopped.is_set())
            self.assertNotIn('cancel-test', media.DOWNLOAD_STAGES)
        finally:
            media.ACTIVE_DOWNLOADS.pop(123, None)
            media.CANCELLED_DOWNLOADS.discard('cancel-test')

    async def test_coroutine_errors_propagate_and_cleanup(self):
        async def fail():
            raise RuntimeError('test failure')

        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            await media._stage('failure-test', fail())
        self.assertNotIn('failure-test', media.DOWNLOAD_STAGES)

    async def test_long_cdn_id_produces_bounded_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            async def spawn(*command, **kwargs):
                template = command[command.index('-o') + 1]
                with media.YoutubeDL({'outtmpl': template, 'quiet': True}) as ydl:
                    filename = ydl.prepare_filename({
                        'title': 'Música 🎤 #Perú ' * 100,
                        'id': 'cdn-video?a=0&signature=' + 'x' * 1000,
                        'ext': 'mp4',
                    })
                self.assertLess(len((Path(filename).name + '.part').encode('utf-8')), 255)
                Path(filename).write_bytes(b'test-video')
                return SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0),
                                       stdout=SimpleNamespace(readline=AsyncMock(return_value=b'')))

            with patch.object(media.tempfile, 'mkdtemp', return_value=directory), \
                 patch.object(media.asyncio, 'create_subprocess_exec', side_effect=spawn):
                path, work, info = await media._download_process(
                    'https://v.tiktokcdn.com/video?a=' + 'x' * 1000, quality='best', job_id='path-test')
            self.assertEqual(path.read_bytes(), b'test-video')
            self.assertNotIn('path-test', media.DOWNLOAD_PROCESSES)


class StatusRouting(unittest.IsolatedAsyncioTestCase):
    def test_registered_as_owner_command(self):
        self.assertIs(COMMANDS['status'], system_ops.status_command)
        self.assertIs(ADMIN['status'], system_ops.status_command)

    async def test_runtime_routes_owner_and_rejects_other_user(self):
        from app.config import OWNER_USER_ID
        runtime = ServiceRuntime()
        runtime.application = SimpleNamespace(bot=None)
        handler = AsyncMock()
        context = SimpleNamespace(args=None)
        with patch.dict(COMMANDS, {'status': handler}), \
             patch('nexora.runtime.CallbackContext.from_update', return_value=context):
            for user_id in (OWNER_USER_ID, 123):
                message = Message(message_id=1, date=datetime.now(timezone.utc),
                                  chat=Chat(id=user_id, type='private'),
                                  from_user=User(id=user_id, is_bot=False, first_name='Test'),
                                  text='/status')
                await runtime.invoke(message)
        handler.assert_awaited_once()
        self.assertEqual(handler.await_args.args[0].effective_user.id, OWNER_USER_ID)
