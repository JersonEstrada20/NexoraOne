from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.database import get_settings


async def has_required_channel_access(bot, chat_id: int, user_id: int):
    settings = await get_settings(chat_id)
    channel = settings.get("required_channel")
    if not channel:
        return True, None
    try:
        member = await bot.get_chat_member(channel, user_id)
        status = getattr(member.status, "value", member.status)
        allowed = str(status) not in {"left", "kicked"}
        return allowed, channel
    except Exception:
        return False, channel


class RequiredChannelMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        message = event.message if isinstance(event, CallbackQuery) else event
        if not isinstance(message, Message) or message.chat.type == "private" or not event.from_user:
            return await handler(event, data)
        allowed, channel = await has_required_channel_access(event.bot, message.chat.id, event.from_user.id)
        if allowed:
            if isinstance(event, CallbackQuery) and event.data == "access:retry":
                await event.answer("✅ Acceso verificado. Ya puedes usar la función.", show_alert=True)
                return None
            return await handler(event, data)
        builder = InlineKeyboardBuilder()
        if channel and str(channel).startswith("@"):
            builder.button(text="📢 Unirme al canal", url=f"https://t.me/{str(channel)[1:]}")
        builder.button(text="✅ Ya me uní", callback_data="access:retry")
        text = f"🔒 Para usar esta función primero debes unirte a {channel}."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await message.reply(text, reply_markup=builder.as_markup())
        return None
