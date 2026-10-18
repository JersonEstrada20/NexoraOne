from html import escape
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.filters import is_admin
from app.services.database import get_settings, set_antiraid, set_night_mode, set_slow_mode
from app.services.group_tools import (
    delete_filter, delete_text, find_filter, get_locks, get_text,
    is_user_whitelisted, list_filters, list_names, list_whitelist,
    normalize_name, set_lock, set_whitelist, upsert_filter, upsert_text,
)
from app.services.templates import render_group_template

router = Router()
_COPY_COMMAND_PREFIX = "__nexora_copy_message__:"
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


async def _send_configured_reply(message: Message, content: str):
    if content.startswith(_COPY_COMMAND_PREFIX):
        try:
            source_id = int(content[len(_COPY_COMMAND_PREFIX):])
            await message.bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=message.chat.id,
                message_id=source_id,
            )
        except (TypeError, ValueError):
            await message.answer("⚠️ La respuesta multimedia guardada ya no es válida. Configúrala otra vez.")
        except Exception:
            await message.answer("⚠️ No pude copiar esa respuesta; comprueba que el mensaje original siga disponible.")
        return
    rendered = await render_group_template(message.bot, message.chat, message.from_user, content)
    await message.answer(rendered)


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
    if not name or not re.fullmatch(r"[a-z0-9_]{1,32}", name):
        await message.answer("⚠️ El nombre debe usar letras sin tilde, números o _ (máximo 32).")
        return
    reserved = {"start", "menu", "me", "perfil", "register", "setcmd", "delcmd", "cmds", "mycmds"}
    try:
        from nexora.runtime import COMMANDS
        reserved.update(COMMANDS)
    except Exception:
        pass
    if name in reserved:
        await message.answer("⚠️ Ese nombre ya está ocupado por un comando del bot. Elige otro.")
        return
    if message.reply_to_message and not content:
        content = f"{_COPY_COMMAND_PREFIX}{message.reply_to_message.message_id}"
        await upsert_text("custom_commands", message.chat.id, name, content, message.from_user.id)
        await message.answer(f"✅ Comando <code>/{escape(name)}</code> guardado. Prueba <code>/{escape(name)}</code> o revisa /mycmds.", parse_mode="HTML")
        return
    if not name or not content:
        await message.answer(
            "🧩 <b>Cómo crear un comando</b>\n\n"
            "Texto: <code>/setcmd tratoadmin Aquí va el mensaje</code>\n"
            "Multimedia (foto, video, GIF, audio, documento o sticker): responde al mensaje que quieras guardar con "
            "<code>/setcmd tratoadmin</code>.\n\n"
            "El mensaje original debe quedarse en el grupo para que el bot pueda copiarlo. Puedes usar {name}, {username}, {group}, {members} y {id} en respuestas de texto.\n\n"
            "Después, cualquiera del grupo puede usar <code>/tratoadmin</code>. "
            "Administra la lista con /mycmds y elimina uno con /delcmd nombre.",
            parse_mode="HTML",
        )
        return
    await upsert_text("custom_commands", message.chat.id, name, content, message.from_user.id)
    await message.answer(f"✅ Comando <code>/{escape(name)}</code> creado.", parse_mode="HTML")


@router.message(Command("delcmd"))
async def del_command(message: Message):
    if not await _admin(message): return
    parts = _args(message); name = normalize_name(parts[1]) if len(parts) > 1 else ""
    deleted = await delete_text("custom_commands", message.chat.id, name) if name else False
    await message.answer("✅ Comando eliminado." if deleted else "No encontré ese comando.")


@router.message(Command("mycmds"))
async def commands(message: Message):
    names = await list_names("custom_commands", message.chat.id)
    text = "\n".join(f"• <code>/{escape(name)}</code>" for name in names)
    await message.answer("⚡ <b>Comandos personalizados</b>\n\n" + (text or "Todavía no hay comandos."), parse_mode="HTML")


@router.message(Command("filter"))
async def set_filter(message: Message):
    if not await _admin(message):
        return
    raw = (message.text or "").strip()
    command_body = re.sub(r"^/filter(?:@\w+)?\s*", "", raw, count=1, flags=re.IGNORECASE)
    trigger_match = re.match(r'(?:(exact|prefix):)?(?:"([^"]+)"|(\S+))(?=\s|$)', command_body, re.IGNORECASE)
    if not trigger_match:
        await message.answer(
            "🧩 <b>Respuestas automáticas</b>\n\n"
            "<code>/filter palabra respuesta</code> busca dentro del mensaje.\n"
            "<code>/filter &quot;hola mundo&quot; respuesta</code> admite frases.\n"
            "<code>/filter exact:hola respuesta</code> exige que el mensaje sea igual.\n"
            "<code>/filter prefix:/ayuda respuesta</code> coincide al inicio.\n"
            "También puedes responder una foto, video, GIF, audio o sticker con "
            "<code>/filter palabra</code>.\n\n"
            "Lista: /filters · Quitar: /stop palabra",
            parse_mode="HTML",
        )
        return

    match_type = (trigger_match.group(1) or "contains").lower()
    trigger = " ".join((trigger_match.group(2) or trigger_match.group(3) or "").casefold().split())
    response = command_body[trigger_match.end():].strip() or None
    if not trigger or len(trigger) > 64:
        await message.answer("⚠️ La frase debe tener entre 1 y 64 caracteres.")
        return
    if message.reply_to_message and not response:
        response = f"{_COPY_COMMAND_PREFIX}{message.reply_to_message.message_id}"
    if not response:
        await message.answer("Falta la respuesta. Añádela al comando o responde a un mensaje multimedia.")
        return
    if len(response) > 4096 and not response.startswith(_COPY_COMMAND_PREFIX):
        await message.answer("La respuesta de texto no puede superar 4096 caracteres.")
        return
    await upsert_filter(message.chat.id, trigger, match_type, response, message.from_user.id)
    await message.answer(
        f"✅ Respuesta guardada para <code>{escape(trigger)}</code> ({match_type}). "
        "Revísala con /filters; elimínala con /stop.",
        parse_mode="HTML",
    )


@router.message(Command("filters"))
async def show_filters(message: Message):
    rows = await list_filters(message.chat.id)
    if not rows:
        await message.answer("🧩 No hay respuestas automáticas configuradas. Usa /filter para crear una.")
        return
    lines = [f"• <code>{escape(trigger)}</code> — {match_type}" for trigger, match_type, _ in rows]
    await message.answer("🧩 <b>Respuestas automáticas</b>\n\n" + "\n".join(lines), parse_mode="HTML")


@router.message(Command("stop"))
async def remove_filter(message: Message):
    if not await _admin(message):
        return
    raw = (message.text or "").strip()
    trigger = re.sub(r"^/stop(?:@\w+)?\s*", "", raw, count=1, flags=re.IGNORECASE)
    trigger = " ".join(trigger.strip().strip('"').casefold().split())
    if not trigger:
        await message.answer("Uso: <code>/stop palabra o frase</code>.", parse_mode="HTML")
        return
    removed = await delete_filter(message.chat.id, trigger)
    await message.answer("✅ Respuesta eliminada." if removed else "No encontré una respuesta con esa frase.")


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


@router.message(Command("noche", "nightmode"))
async def night_mode(message: Message):
    if not await _admin(message):
        return
    parts = (message.text or "").split()
    settings = await get_settings(message.chat.id)
    if len(parts) == 1:
        state = "activado" if settings["night_mode_enabled"] else "desactivado"
        await message.answer(
            f"🌙 Modo nocturno {state}. Horario: {settings['night_mode_start']}–{settings['night_mode_end']} "
            f"({escape(settings['night_mode_timezone'])}).\n"
            "Durante ese horario se eliminan mensajes de miembros que no sean admins.\n\n"
            "Configurar: <code>/noche on 22:00 07:00 America/Santiago</code>\n"
            "Apagar: <code>/noche off</code>",
            parse_mode="HTML",
        )
        return
    if parts[1].lower() in {"off", "apagar"}:
        await set_night_mode(message.chat.id, False, settings["night_mode_start"], settings["night_mode_end"], settings["night_mode_timezone"])
        await message.answer("🌙 Modo nocturno desactivado.")
        return
    values = parts[1:]
    if values[0].lower() in {"on", "activar"}:
        values = values[1:]
    if len(values) not in {2, 3}:
        await message.answer("Uso: <code>/noche on 22:00 07:00 America/Santiago</code> o <code>/noche off</code>.", parse_mode="HTML")
        return
    start, end = values[0], values[1]
    timezone = values[2] if len(values) == 3 else settings["night_mode_timezone"]
    try:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", end):
            raise ValueError
        ZoneInfo(timezone)
    except (ValueError, KeyError):
        await message.answer("⚠️ Usa horas de 24 h (HH:MM) y una zona válida, como <code>America/Santiago</code>.", parse_mode="HTML")
        return
    if start == end:
        await message.answer("⚠️ La hora de inicio y fin no pueden ser iguales.")
        return
    await set_night_mode(message.chat.id, True, start, end, timezone)
    await message.answer(
        f"✅ Modo nocturno activado: <b>{start}–{end}</b> ({escape(timezone)}). "
        "Los mensajes de miembros se eliminarán durante ese horario.",
        parse_mode="HTML",
    )


@router.message(Command("antiraid"))
async def anti_raid(message: Message):
    if not await _admin(message):
        return
    parts = (message.text or "").split()
    settings = await get_settings(message.chat.id)
    if len(parts) == 1:
        state = "activada" if settings["antiraid_enabled"] else "desactivada"
        await message.answer(
            f"🚨 Protección anti-raid {state}. Se activa con {settings['raid_join_threshold']} ingresos "
            f"en {settings['raid_window_seconds']} segundos.\n"
            "Al detectar una oleada, los nuevos ingresos deben resolver CAPTCHA durante dos minutos.\n\n"
            "Configurar: <code>/antiraid on 8 30</code> · Apagar: <code>/antiraid off</code>",
            parse_mode="HTML",
        )
        return
    if parts[1].lower() in {"off", "apagar"}:
        await set_antiraid(message.chat.id, False, settings["raid_join_threshold"], settings["raid_window_seconds"])
        await message.answer("🚨 Protección anti-raid desactivada.")
        return
    if parts[1].lower() not in {"on", "activar"}:
        await message.answer("Usa <code>/antiraid on 8 30</code> o <code>/antiraid off</code>.", parse_mode="HTML")
        return
    try:
        threshold = int(parts[2]) if len(parts) > 2 else settings["raid_join_threshold"]
        window = int(parts[3]) if len(parts) > 3 else settings["raid_window_seconds"]
    except ValueError:
        await message.answer("⚠️ El umbral y la ventana deben ser números.")
        return
    if not 3 <= threshold <= 100 or not 10 <= window <= 300:
        await message.answer("⚠️ El umbral debe ser 3–100 miembros y la ventana 10–300 segundos.")
        return
    await set_antiraid(message.chat.id, True, threshold, window)
    await message.answer(
        f"✅ Protección anti-raid activada: <b>{threshold} ingresos en {window}s</b>. "
        "Si detecta una oleada, pedirá CAPTCHA a los nuevos miembros durante dos minutos.",
        parse_mode="HTML",
    )


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
        await _send_configured_reply(message, content)
