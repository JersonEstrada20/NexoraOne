from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.filters import is_admin
from app.services.database import set_slow_mode
from app.services.group_tools import (
    delete_text, get_locks, get_text, is_user_whitelisted, list_names,
    list_whitelist, normalize_name, set_lock, set_whitelist, upsert_text,
)

router = Router()
LOCK_ALIASES = {
    "foto": "fotos", "fotos": "fotos", "video": "videos", "videos": "videos",
    "sticker": "stickers", "stickers": "stickers", "gif": "gifs", "gifs": "gifs",
    "audio": "audios", "audios": "audios", "voz": "audios",
    "encuesta": "encuestas", "encuestas": "encuestas",
    "documento": "documentos", "documentos": "documentos",
}


async def _admin(message: Message) -> bool:
    if message.chat.type == "private":
        await message.answer("Este comando se usa dentro de un grupo.")
        return False
    if not message.from_user or not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("🔒 Solo los administradores pueden usar este comando.")
        return False
    return True


def _args(message: Message):
    return (message.text or "").split(maxsplit=2)


@router.message(Command("save"))
async def save_note(message: Message):
    if not await _admin(message): return
    parts = _args(message)
    name = normalize_name(parts[1]) if len(parts) > 1 else ""
    content = parts[2] if len(parts) > 2 else None
    if message.reply_to_message and not content:
        content = message.reply_to_message.text or message.reply_to_message.caption
    if not name or not content:
        await message.answer("Uso: <code>/save nombre texto</code> o responde un mensaje.", parse_mode="HTML")
        return
    await upsert_text("group_notes", message.chat.id, name, content, message.from_user.id)
    await message.answer(f"✅ Nota <code>#{escape(name)}</code> guardada.", parse_mode="HTML")


@router.message(Command("get"))
async def get_note(message: Message):
    parts = _args(message)
    name = normalize_name(parts[1]) if len(parts) > 1 else ""
    content = await get_text("group_notes", message.chat.id, name) if name else None
    await message.answer(content or "🔎 Esa nota no existe. Mira <code>/notes</code>.", parse_mode="HTML")


@router.message(Command("notes"))
async def notes(message: Message):
    names = await list_names("group_notes", message.chat.id)
    text = "\n".join(f"• <code>/get {escape(name)}</code>" for name in names)
    await message.answer("🗒 <b>Notas del grupo</b>\n\n" + (text or "Todavía no hay notas."), parse_mode="HTML")


@router.message(Command("delnote"))
async def del_note(message: Message):
    if not await _admin(message): return
    parts = _args(message); name = normalize_name(parts[1]) if len(parts) > 1 else ""
    deleted = await delete_text("group_notes", message.chat.id, name) if name else False
    await message.answer("✅ Nota eliminada." if deleted else "No encontré esa nota.")


@router.message(Command("setcmd"))
async def set_command(message: Message):
    if not await _admin(message): return
    parts = _args(message)
    name = normalize_name(parts[1]) if len(parts) > 1 else ""
    content = parts[2] if len(parts) > 2 else None
    if message.reply_to_message and not content:
        content = message.reply_to_message.text or message.reply_to_message.caption
    if not name or not content:
        await message.answer("Uso: <code>/setcmd nombre respuesta</code> o responde un mensaje.", parse_mode="HTML")
        return
    await upsert_text("custom_commands", message.chat.id, name, content, message.from_user.id)
    await message.answer(f"✅ Comando <code>/{escape(name)}</code> creado.", parse_mode="HTML")


@router.message(Command("delcmd"))
async def del_command(message: Message):
    if not await _admin(message): return
    parts = _args(message); name = normalize_name(parts[1]) if len(parts) > 1 else ""
    deleted = await delete_text("custom_commands", message.chat.id, name) if name else False
    await message.answer("✅ Comando eliminado." if deleted else "No encontré ese comando.")


async def commands(message: Message):
    names = await list_names("custom_commands", message.chat.id)
    text = "\n".join(f"• <code>/{escape(name)}</code>" for name in names)
    await message.answer("⚡ <b>Comandos personalizados</b>\n\n" + (text or "Todavía no hay comandos."), parse_mode="HTML")


@router.message(Command("pin"))
async def pin(message: Message):
    if not await _admin(message): return
    if not message.reply_to_message:
        await message.answer("Responde al mensaje que quieres fijar con <code>/pin</code>.", parse_mode="HTML"); return
    try:
        await message.bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
        await message.answer("📌 Mensaje fijado.")
    except Exception as exc:
        await message.answer(f"No pude fijarlo. Revisa el permiso de fijar mensajes.\n<code>{escape(str(exc))}</code>", parse_mode="HTML")


@router.message(Command("unpin"))
async def unpin(message: Message):
    if not await _admin(message): return
    try:
        await message.bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id if message.reply_to_message else None)
        await message.answer("📍 Mensaje desfijado.")
    except Exception as exc:
        await message.answer(f"No pude desfijarlo: <code>{escape(str(exc))}</code>", parse_mode="HTML")


@router.message(Command("unpinall"))
async def unpin_all(message: Message):
    if not await _admin(message): return
    await message.bot.unpin_all_chat_messages(message.chat.id)
    await message.answer("✅ Se desfijaron todos los mensajes.")


@router.message(Command("slowmode"))
async def slowmode(message: Message):
    if not await _admin(message): return
    parts = _args(message)
    try: seconds = int(parts[1])
    except (IndexError, ValueError):
        await message.answer("Uso: <code>/slowmode 10</code> (0 para apagar; máximo 3600).", parse_mode="HTML"); return
    if seconds not in {0, 10, 30, 60, 300, 900, 3600}:
        await message.answer("Valores permitidos: 0, 10, 30, 60, 300, 900 o 3600 segundos."); return
    await set_slow_mode(message.chat.id, seconds)
    await message.answer("⚡ Modo lento apagado." if seconds == 0 else f"🐢 Modo lento: un mensaje cada {seconds} segundos.")


@router.message(Command("bloquear", "desbloquear"))
async def content_lock(message: Message):
    if not await _admin(message): return
    parts = _args(message); requested = parts[1].lower() if len(parts) > 1 else ""
    kind = LOCK_ALIASES.get(requested)
    if not kind:
        await message.answer("Tipos: fotos, videos, stickers, gifs, audios, documentos o encuestas."); return
    enabled = (message.text or "").split()[0].lower().startswith("/bloquear")
    await set_lock(message.chat.id, kind, enabled)
    await message.answer(f"{'🔒 Bloqueado' if enabled else '🔓 Desbloqueado'}: {kind}.")


@router.message(Command("bloqueos"))
async def locks(message: Message):
    values = sorted(await get_locks(message.chat.id))
    await message.answer("🔒 <b>Contenido bloqueado</b>\n" + ("\n".join(f"• {x}" for x in values) or "Ninguno."), parse_mode="HTML")


def _target_user(message: Message, parts):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    try: return int(parts[1])
    except (IndexError, ValueError): return None


@router.message(Command("whitelistuser", "unwhitelistuser"))
async def whitelist_user(message: Message):
    if not await _admin(message): return
    parts = _args(message); user_id = _target_user(message, parts)
    if not user_id:
        await message.answer("Responde a una persona o usa <code>/whitelistuser ID</code>.", parse_mode="HTML"); return
    enabled = (message.text or "").split()[0].lower().startswith("/whitelistuser")
    await set_whitelist("user_whitelist", message.chat.id, user_id, enabled)
    await message.answer(f"{'✅ Usuario autorizado' if enabled else '🗑 Usuario retirado'}: <code>{user_id}</code>", parse_mode="HTML")


@router.message(Command("whitelistusers"))
async def whitelist_users(message: Message):
    values = await list_whitelist("user_whitelist", message.chat.id)
    await message.answer("👥 <b>Usuarios autorizados</b>\n" + ("\n".join(f"• <code>{x}</code>" for x in values) or "Ninguno."), parse_mode="HTML")


@router.message(Command("whitelistlink", "unwhitelistlink"))
async def whitelist_link(message: Message):
    if not await _admin(message): return
    parts = _args(message); domain = parts[1].lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0] if len(parts) > 1 else ""
    if not domain or "." not in domain:
        await message.answer("Uso: <code>/whitelistlink youtube.com</code>", parse_mode="HTML"); return
    enabled = (message.text or "").split()[0].lower().startswith("/whitelistlink")
    await set_whitelist("link_whitelist", message.chat.id, domain, enabled)
    await message.answer(f"{'✅ Dominio permitido' if enabled else '🗑 Dominio retirado'}: <code>{escape(domain)}</code>", parse_mode="HTML")


@router.message(Command("whitelistlinks"))
async def whitelist_links(message: Message):
    values = await list_whitelist("link_whitelist", message.chat.id)
    await message.answer("🔗 <b>Enlaces permitidos</b>\n" + ("\n".join(f"• <code>{escape(str(x))}</code>" for x in values) or "Ninguno."), parse_mode="HTML")


@router.message(F.photo | F.video | F.animation | F.sticker | F.audio | F.voice | F.document | F.poll)
async def enforce_locks(message: Message):
    if not message.from_user or message.chat.type == "private": return
    if await is_admin(message.bot, message.chat.id, message.from_user.id) or await is_user_whitelisted(message.chat.id, message.from_user.id): return
    kind = ("fotos" if message.photo else "videos" if message.video else "gifs" if message.animation else
            "stickers" if message.sticker else "audios" if (message.audio or message.voice) else
            "documentos" if message.document else "encuestas")
    if kind not in await get_locks(message.chat.id): return
    try: await message.delete()
    except Exception: return
    await message.answer(f"🔒 {message.from_user.full_name}, en este grupo están bloqueados: {kind}.")


@router.message(F.text.regexp(r"^/[A-Za-z0-9_áéíóúÁÉÍÓÚñÑ]+(?:@\w+)?$"))
async def custom_command(message: Message):
    if message.chat.type == "private": return
    name = normalize_name((message.text or "").split("@")[0])
    content = await get_text("custom_commands", message.chat.id, name)
    if content:
        await message.answer(content)
