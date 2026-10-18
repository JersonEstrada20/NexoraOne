import unittest
from email.message import Message as Headers
from io import BytesIO
from unittest.mock import AsyncMock, patch
from app.handlers import media


class TikTokDirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolved_cdn_video_is_downloaded_directly(self):
        url = "https://v.tiktokcdn.com/video.mp4"

        class FakeResponse(BytesIO):
            headers = Headers()

            def geturl(self):
                return url

        response = FakeResponse(b"video-bytes")
        response.headers["Content-Type"] = "video/mp4"
        response.headers["Content-Length"] = str(len(b"video-bytes"))

        with patch.object(media, "urlopen", return_value=response):
            path, work, info = await media._download_process(url, job_id="tiktok-test")
        try:
            self.assertEqual(path.read_bytes(), b"video-bytes")
            self.assertEqual(info["title"], "Video de TikTok")
        finally:
            media.shutil.rmtree(work, ignore_errors=True)

    async def test_video_starts_without_confirmation(self):
        message = AsyncMock()
        status = message.reply.return_value
        with patch.object(media, "_fetch_tiktok_data", return_value={
            "kind": "video", "video_url": "https://v.tiktokcdn.com/video.mp4",
            "title": "Mi video #musica #Perú",
        }), patch.object(media, "_send_download", new_callable=AsyncMock) as send:
            await media._ask_video_quality(message, "https://vt.tiktok.com/example/", 123)
        send.assert_awaited_once_with(
            message, "https://v.tiktokcdn.com/video.mp4", audio=False, document=False,
            quality="best", requester_id=123, status_message=status,
            title_override="Mi video #musica #Perú",
            source_url="https://vt.tiktok.com/example/",
        )
        self.assertFalse(any("Video de TikTok detectado" in str(call) for call in status.edit_text.await_args_list))
