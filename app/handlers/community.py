import asyncio
import random
import re
from datetime import datetime, timedelta, timezone
from html import escape

from nexora import async_db as aiosqlite
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DB_PATH
from app.services.database import get_activity_ranking, get_activity_total
from app.services.filters import is_admin

router = Router()


async def _require_admin(message: Message):
    if message.chat.type == "private":
        await message.answer("Este comando se usa dentro del grupo.")
        return False
    if not message.from_user or not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("🔒 Solo administradores.")
        return False
    return True


def _duration_seconds(value: str):
    match = re.fullmatch(r"(\d+)(s|m|h|d)", (value or "").lower())
    if not match:
        return None
    amount = int(match.group(1))
    return amount * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


def _giveaway_keyboard(giveaway_id: int, count: int = 0):
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🎉 Participar ({count})", callback_data=f"giveaway:join:{giveaway_id}")
    return builder.as_markup()


async def _finish_giveaway(bot, giveaway_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        giveaway = await (await db.execute(
            "SELECT chat_id,message_id,prize,status FROM giveaways WHERE id=?", (giveaway_id,))).fetchone()
        if not giveaway or giveaway[3] != "open":
            return
        users = [row[0] for row in await (await db.execute(
            "SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))).fetchall()]
        winner = random.choice(users) if users else None
        await db.execute("UPDATE giveaways SET status='closed',winner_id=? WHERE id=?", (winner, giveaway_id))
        await db.commit()
    chat_id, message_id, prize, _ = giveaway
    if winner:
        text = f"🏆 <b>Sorteo finalizado #{giveaway_id}</b>\n\n🎁 {escape(prize)}\n👑 Ganador: <a href='tg://user?id={winner}'>usuario {winner}</a>"
    else:
        text = f"🏁 <b>Sorteo finalizado #{giveaway_id}</b>\n\nNo hubo participantes."
    try:
        await bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML")
    except Exception:
        await bot.send_message(chat_id, text, parse_mode="HTML")


async def _finish_later(bot, giveaway_id: int, seconds: int):
    await asyncio.sleep(seconds)
    await _finish_giveaway(bot, giveaway_id)


async def process_expired_giveaways(bot):
    now = datetime.now(timezone.utc)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT id,ends_at FROM giveaways WHERE status='open'"
        )).fetchall()
    for giveaway_id, ends_at in rows:
        if datetime.fromisoformat(ends_at) <= now:
            await _finish_giveaway(bot, giveaway_id)


async def giveaway_recovery_loop(bot):
    """Finaliza sorteos vencidos incluso después de reiniciar el contenedor."""
    while True:
        try:
            await process_expired_giveaways(bot)
        except Exception:
            pass
        await asyncio.sleep(30)


@router.message(Command("sorteo"))
async def giveaway(message: Message, command: CommandObject):
    if not await _require_admin(message): return
    parts = (command.args or "").split(maxsplit=1)
    seconds = _duration_seconds(parts[0]) if parts else None
    if not seconds or len(parts) < 2:
        await message.answer("Uso: <code>/sorteo 10m Premio</code> (s, m, h o d).", parse_mode="HTML"); return
    ends = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO giveaways(chat_id,prize,created_by,ends_at) VALUES(?,?,?,?)",
                                  (message.chat.id, parts[1], message.from_user.id, ends.isoformat()))
        giveaway_id = cursor.lastrowid
        await db.commit()
    sent = await message.answer(
        f"🎉 <b>SORTEO #{giveaway_id}</b>\n\n🎁 Premio: <b>{escape(parts[1])}</b>\n⏳ Duración: {parts[0]}\n\nPulsa el botón para participar.",
        parse_mode="HTML", reply_markup=_giveaway_keyboard(giveaway_id))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE giveaways SET message_id=? WHERE id=?", (sent.message_id, giveaway_id)); await db.commit()
    # El bucle persistente finaliza el sorteo; así también sobrevive a reinicios.


@router.callback_query(F.data.startswith("giveaway:join:"))
async def join_giveaway(callback: CallbackQuery):
    giveaway_id = int(callback.data.rsplit(":", 1)[1])
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT status,chat_id FROM giveaways WHERE id=?", (giveaway_id,))).fetchone()
        if not row or row[0] != "open" or not callback.message or row[1] != callback.message.chat.id:
            await callback.answer("Este sorteo ya terminó.", show_alert=True); return
        cursor = await db.execute("INSERT OR IGNORE INTO giveaway_entries(giveaway_id,user_id) VALUES(?,?)", (giveaway_id, callback.from_user.id))
        count = (await (await db.execute("SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id=?", (giveaway_id,))).fetchone())[0]
        await db.commit()
    if cursor.rowcount == 0:
        await callback.answer("Ya estás participando ✅", show_alert=True)
    else:
        await callback.answer("¡Participación registrada! 🎉", show_alert=True)
        try: await callback.message.edit_reply_markup(reply_markup=_giveaway_keyboard(giveaway_id, count))
        except Exception: pass


@router.message(Command("finalizarsorteo"))
async def finish_giveaway(message: Message, command: CommandObject):
    if not await _require_admin(message): return
    try: giveaway_id = int(command.args or "")
    except ValueError:
        await message.answer("Uso: <code>/finalizarsorteo ID</code>", parse_mode="HTML"); return
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT chat_id FROM giveaways WHERE id=?", (giveaway_id,))).fetchone()
    if not row or row[0] != message.chat.id:
        await message.answer("No encontré ese sorteo abierto en este grupo."); return
    await _finish_giveaway(message.bot, giveaway_id)


@router.message(Command("rankactividad"))
async def activity_rank(message: Message):
    rows = await get_activity_ranking(message.chat.id)
    lines = ["🏆 <b>Usuarios más activos</b>", ""]
    for position, (user_id, messages) in enumerate(rows, 1):
        try: name = (await message.bot.get_chat_member(message.chat.id, user_id)).user.full_name
        except Exception: name = f"Usuario {user_id}"
        lines.append(f"{position}. <a href='tg://user?id={user_id}'>{escape(name)}</a> — {messages} mensajes")
    await message.answer("\n".join(lines) if rows else "Todavía no hay actividad registrada.", parse_mode="HTML")


@router.message(Command("actividad"))
async def activity_stats(message: Message):
    messages, users = await get_activity_total(message.chat.id)
    await message.answer(f"📊 <b>Actividad registrada</b>\n\n💬 Mensajes: <b>{messages}</b>\n👥 Usuarios activos: <b>{users}</b>", parse_mode="HTML")


@router.message(Command("copiarconfig"))
async def copy_config(message: Message, command: CommandObject):
    if not await _require_admin(message): return
    try: source = int(command.args or "")
    except ValueError:
        await message.answer("Úsalo en el grupo destino: <code>/copiarconfig ID_GRUPO_ORIGEN</code>", parse_mode="HTML"); return
    if not await is_admin(message.bot, source, message.from_user.id):
        await message.answer("Debes ser administrador también en el grupo de origen."); return
    target = message.chat.id
    if source == target:
        await message.answer("El grupo de origen y destino no pueden ser el mismo."); return
    async with aiosqlite.connect(DB_PATH) as db:
        source_row = await (await db.execute("SELECT * FROM group_settings WHERE chat_id=?", (source,))).fetchone()
        if not source_row:
            await message.answer("No encontré configuración guardada para ese grupo."); return
        columns = [row[1] for row in await (await db.execute("PRAGMA table_info(group_settings)")).fetchall()]
        values = list(source_row); values[columns.index("chat_id")] = target
        placeholders = ",".join("?" for _ in columns)
        await db.execute(f"INSERT OR REPLACE INTO group_settings({','.join(columns)}) VALUES({placeholders})", values)
        for table, cols in (("bad_words", "word"), ("group_notes", "name,content,created_by"),
                            ("custom_commands", "name,content,created_by"), ("content_locks", "content_type"),
                            ("link_whitelist", "domain"), ("user_whitelist", "user_id"),
                            ("level_roles", "level,role_name")):
            await db.execute(f"DELETE FROM {table} WHERE chat_id=?", (target,))
            await db.execute(f"INSERT INTO {table}(chat_id,{cols}) SELECT ?,{cols} FROM {table} WHERE chat_id=?", (target, source))
        await db.commit()
    await message.answer("✅ Configuración, notas, comandos, bloqueos y listas blancas copiados a este grupo.")
