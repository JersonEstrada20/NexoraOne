import unittest
from unittest.mock import AsyncMock, patch
from app.handlers import media


class TikTokDirectTests(unittest.IsolatedAsyncioTestCase):
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
