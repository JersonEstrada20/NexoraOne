import asyncio

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.services.database import get_settings


async def _delete_later(message: Message, seconds: int):
    await asyncio.sleep(seconds)
    try:
        await message.delete()
    except Exception:
        pass


class CommandCleanupMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, Message) and event.chat.type != "private" and (event.text or "").startswith("/"):
            settings = await get_settings(event.chat.id)
            seconds = settings.get("auto_delete_seconds", 0)
            if seconds:
                asyncio.create_task(_delete_later(event, seconds))
        return await handler(event, data)
