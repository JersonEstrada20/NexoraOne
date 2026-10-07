import asyncio
import re
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from nexora import async_db as aiosqlite
import aiohttp
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config import DB_PATH
from app.services.database import (
    delete_level_role, get_activity_profile, get_level_roles, set_level_role,
    get_activity_total, get_weekly_activity, get_group_stats, get_settings, set_required_channel,
    set_weekly_stats_enabled, set_auto_delete_seconds, set_language,
)
from app.services.filters import is_admin

router = Router()
LIMA = ZoneInfo("America/Lima")
DAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6}


async def _admin(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.answer("Este comando es para grupos."); return False
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("🔒 Solo administradores."); return False
    return True


def _relative(value: str):
    match = re.fullmatch(r"(\d+)(s|m|h|d)", (value or "").lower())
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)] if match else None


def _next_time(hour_text: str, weekday: int | None = None):
    try:
        hour, minute = map(int, hour_text.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59): return None
    except (ValueError, AttributeError): return None
    now = datetime.now(LIMA)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday is None:
        if candidate <= now: candidate += timedelta(days=1)
    else:
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= now: candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc)


async def _save_schedule(message: Message, text: str, next_run: datetime, repeat: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO scheduled_messages(chat_id,text,next_run,repeat_seconds,created_by) VALUES(?,?,?,?,?)",
            (message.chat.id, text, next_run.isoformat(), repeat, message.from_user.id))
        await db.commit()
    local = next_run.astimezone(LIMA).strftime("%d/%m %H:%M")
    await message.answer(f"✅ Mensaje programado #{cursor.lastrowid}\n🕒 Próximo envío: {local} (hora Perú)")


@router.message(Command("programar"))
async def schedule_once(message: Message, command: CommandObject):
    if not await _admin(message): return
    parts = (command.args or "").split(maxsplit=1); seconds = _relative(parts[0]) if parts else None
    if not seconds or len(parts) < 2:
        await message.answer("Uso: <code>/programar 30m Mensaje</code>", parse_mode="HTML"); return
    await _save_schedule(message, parts[1], datetime.now(timezone.utc) + timedelta(seconds=seconds), None)


@router.message(Command("programardiario"))
async def schedule_daily(message: Message, command: CommandObject):
    if not await _admin(message): return
    parts = (command.args or "").split(maxsplit=1); next_run = _next_time(parts[0]) if parts else None
    if not next_run or len(parts) < 2:
        await message.answer("Uso: <code>/programardiario 18:30 Mensaje</code>", parse_mode="HTML"); return
    await _save_schedule(message, parts[1], next_run, 86400)


@router.message(Command("programarsemanal"))
async def schedule_weekly(message: Message, command: CommandObject):
    if not await _admin(message): return
    parts = (command.args or "").split(maxsplit=2)
    weekday = DAYS.get(parts[0].lower()) if parts else None
    next_run = _next_time(parts[1], weekday) if weekday is not None and len(parts) > 1 else None
    if not next_run or len(parts) < 3:
        await message.answer("Uso: <code>/programarsemanal viernes 20:00 Mensaje</code>", parse_mode="HTML"); return
    await _save_schedule(message, parts[2], next_run, 604800)


@router.message(Command("programados"))
async def schedules(message: Message):
    if not await _admin(message): return
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("SELECT id,text,next_run,repeat_seconds FROM scheduled_messages WHERE chat_id=? AND enabled=1 ORDER BY next_run", (message.chat.id,))).fetchall()
    lines = ["🗓 <b>Mensajes programados</b>", ""]
    for schedule_id, text, next_run, repeat in rows:
        local = datetime.fromisoformat(next_run).astimezone(LIMA).strftime("%d/%m %H:%M")
        kind = "una vez" if not repeat else "diario" if repeat == 86400 else "semanal"
        lines.append(f"#{schedule_id} · {local} · {kind}\n└ {escape(text[:60])}")
    await message.answer("\n".join(lines) if rows else "No hay mensajes programados.", parse_mode="HTML")


@router.message(Command("cancelarprogramado"))
async def cancel_schedule(message: Message, command: CommandObject):
    if not await _admin(message): return
    try: schedule_id = int(command.args or "")
    except ValueError:
        await message.answer("Uso: <code>/cancelarprogramado ID</code>", parse_mode="HTML"); return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE scheduled_messages SET enabled=0 WHERE id=? AND chat_id=?", (schedule_id, message.chat.id)); await db.commit()
    await message.answer("✅ Programación cancelada." if cursor.rowcount else "No encontré esa programación.")


@router.message(Command("encuesta", "encuestaanonima"))
async def advanced_poll(message: Message, command: CommandObject):
    if not await _admin(message): return
    parts = [part.strip() for part in (command.args or "").split("|") if part.strip()]
    if len(parts) < 3 or len(parts) > 11:
        await message.answer("Uso: <code>/encuesta Pregunta | Opción 1 | Opción 2</code> (máximo 10 opciones).", parse_mode="HTML"); return
    anonymous = (message.text or "").split()[0].lower().startswith("/encuestaanonima")
    await message.bot.send_poll(message.chat.id, parts[0], parts[1:], is_anonymous=anonymous, allows_multiple_answers=False)


async def level(message: Message):
    target = message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else message.from_user
    messages, current_level, role = await get_activity_profile(message.chat.id, target.id)
    progress = messages % 25
    bar = "🟩" * (progress // 5) + "⬜" * (5 - progress // 5)
    await message.answer(f"⭐ <b>Nivel de {escape(target.full_name)}</b>\n\nNivel: <b>{current_level}</b>\nRol: <b>{escape(role or 'Sin rol')}</b>\nMensajes: {messages}\n{bar} {progress}/25", parse_mode="HTML")


@router.message(Command("setrolnivel"))
async def set_role(message: Message, command: CommandObject):
    if not await _admin(message): return
    parts = (command.args or "").split(maxsplit=1)
    try: level_value = int(parts[0])
    except (ValueError, IndexError):
        await message.answer("Uso: <code>/setrolnivel 5 Experto</code>", parse_mode="HTML"); return
    if len(parts) < 2 or level_value < 1:
        await message.answer("Indica nivel y nombre del rol."); return
    await set_level_role(message.chat.id, level_value, parts[1][:30])
    await message.answer(f"✅ Al nivel {level_value} se obtiene el rol: {parts[1][:30]}")


@router.message(Command("delrolnivel"))
async def del_role(message: Message, command: CommandObject):
    if not await _admin(message): return
    try: level_value = int(command.args or "")
    except ValueError:
        await message.answer("Uso: <code>/delrolnivel 5</code>", parse_mode="HTML"); return
    await delete_level_role(message.chat.id, level_value); await message.answer("✅ Rol eliminado.")


@router.message(Command("rolesnivel"))
async def roles(message: Message):
    rows = await get_level_roles(message.chat.id)
    await message.answer("🎖 <b>Roles por nivel</b>\n\n" + ("\n".join(f"• Nivel {level}: {escape(role)}" for level, role in rows) or "No hay roles configurados."), parse_mode="HTML")


@router.message(Command("statssemanales"))
async def weekly_stats_setting(message: Message, command: CommandObject):
    if not await _admin(message): return
    value = (command.args or "").lower()
    if value not in {"on", "off"}:
        await message.answer("Uso: <code>/statssemanales on</code> o <code>off</code>.", parse_mode="HTML"); return
    await set_weekly_stats_enabled(message.chat.id, value == "on")
    await message.answer(f"📊 Resumen semanal {'activado' if value == 'on' else 'desactivado'}.")


@router.message(Command("canalobligatorio"))
async def required_channel(message: Message, command: CommandObject):
    if not await _admin(message): return
    value = (command.args or "").strip()
    if value.lower() == "off":
        await set_required_channel(message.chat.id, None)
        await message.answer("✅ Canal obligatorio desactivado."); return
    if not value.startswith("@") and not value.startswith("-100"):
        await message.answer("Uso: <code>/canalobligatorio @TuCanal</code> o <code>off</code>.", parse_mode="HTML"); return
    try:
        chat = await message.bot.get_chat(int(value) if value.startswith("-100") else value)
    except Exception:
        await message.answer("No puedo acceder a ese canal. Agrega el bot como administrador y revisa el usuario/ID."); return
    await set_required_channel(message.chat.id, value)
    await message.answer(f"✅ Para descargas y economía ahora se exige pertenecer a {chat.title}.")


@router.message(Command("autolimpieza"))
async def auto_cleanup(message: Message, command: CommandObject):
    if not await _admin(message): return
    try: seconds = int(command.args or "")
    except ValueError:
        await message.answer("Uso: <code>/autolimpieza 15</code> o <code>0</code> para apagar.", parse_mode="HTML"); return
    if seconds != 0 and not 5 <= seconds <= 3600:
        await message.answer("El tiempo debe ser 0 o estar entre 5 y 3600 segundos."); return
    await set_auto_delete_seconds(message.chat.id, seconds)
    await message.answer("🧹 Autolimpieza desactivada." if seconds == 0 else f"🧹 Los mensajes de comandos se borrarán después de {seconds} segundos.")


@router.message(Command("idioma"))
async def language(message: Message, command: CommandObject):
    if not await _admin(message): return
    value = (command.args or "").lower().strip()
    aliases = {"es": "es", "español": "es", "en": "en", "english": "en", "inglés": "en", "ingles": "en"}
    selected = aliases.get(value)
    if not selected:
        await message.answer("Uso: <code>/idioma es</code> o <code>/idioma en</code>.", parse_mode="HTML"); return
    await set_language(message.chat.id, selected)
    await message.answer("✅ Idioma cambiado a Español." if selected == "es" else "✅ Language changed to English. Open /menu again.")


@router.message(Command("letra"))
async def lyrics(message: Message, command: CommandObject):
    query = (command.args or "").strip()
    if not query:
        await message.answer("Uso: <code>/letra artista canción</code>", parse_mode="HTML"); return
    status = await message.answer("🔎 Buscando la letra…")
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "NEXORA ONE/1.0"}) as session:
            async with session.get("https://lrclib.net/api/search", params={"q": query}) as response:
                results = await response.json() if response.status == 200 else []
        item = next((result for result in results if result.get("plainLyrics")), None)
        if not item:
            await status.edit_text("No encontré una letra disponible para esa búsqueda."); return
        lyrics_text = item["plainLyrics"].strip()
        title = item.get("trackName") or query
        artist = item.get("artistName") or ""
        body = f"🎤 <b>{escape(title)}</b>\n👤 {escape(artist)}\n\n{escape(lyrics_text)}"
        if len(body) <= 4000:
            await status.edit_text(body, parse_mode="HTML")
        else:
            await status.edit_text(f"🎤 <b>{escape(title)}</b> — {escape(artist)}", parse_mode="HTML")
            for start in range(0, len(lyrics_text), 3800):
                await message.answer(f"<pre>{escape(lyrics_text[start:start+3800])}</pre>", parse_mode="HTML")
    except Exception:
        await status.edit_text("❌ El servicio de letras no respondió. Intenta nuevamente.")


async def process_due_schedules(bot):
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("SELECT id,chat_id,text,next_run,repeat_seconds FROM scheduled_messages WHERE enabled=1")).fetchall()
        for schedule_id, chat_id, text, next_run, repeat in rows:
            if datetime.fromisoformat(next_run) > now: continue
            try: await bot.send_message(chat_id, "📢 " + text)
            except Exception: continue
            if repeat:
                future = datetime.fromisoformat(next_run)
                while future <= now: future += timedelta(seconds=repeat)
                await db.execute("UPDATE scheduled_messages SET next_run=? WHERE id=?", (future.isoformat(), schedule_id))
            else:
                await db.execute("UPDATE scheduled_messages SET enabled=0 WHERE id=?", (schedule_id,))
        await db.commit()


async def scheduled_messages_loop(bot):
    while True:
        try:
            await process_due_schedules(bot)
        except Exception:
            pass
        await asyncio.sleep(20)


async def weekly_stats_loop(bot):
    while True:
        try:
            local_now = datetime.now(LIMA)
            year_week = f"{local_now.isocalendar().year}-{local_now.isocalendar().week:02d}"
            if local_now.weekday() == 0 and local_now.hour >= 9:
                async with aiosqlite.connect(DB_PATH) as db:
                    groups = await (await db.execute("SELECT chat_id,log_chat_id FROM group_settings WHERE weekly_stats_enabled=1")).fetchall()
                    for chat_id, log_chat_id in groups:
                        exists = await (await db.execute("SELECT 1 FROM weekly_stats_sent WHERE chat_id=? AND year_week=?", (chat_id, year_week))).fetchone()
                        if exists: continue
                        messages, users = await get_weekly_activity(chat_id)
                        stats = await get_group_stats(chat_id)
                        text = (f"📊 <b>Resumen semanal</b>\n\n💬 Mensajes de los últimos 7 días: {messages}\n"
                                f"👥 Usuarios activos: {users}\n⚠️ Usuarios con warns: {stats['warned_users_count']}\n"
                                f"🚩 Reportes abiertos: {stats['open_reports_count']}\n🎫 Tickets abiertos: {stats['open_tickets_count']}")
                        try: await bot.send_message(log_chat_id or chat_id, text, parse_mode="HTML")
                        except Exception: continue
                        await db.execute("INSERT OR IGNORE INTO weekly_stats_sent(chat_id,year_week) VALUES(?,?)", (chat_id, year_week))
                    await db.commit()
        except Exception:
            pass
        await asyncio.sleep(1800)
