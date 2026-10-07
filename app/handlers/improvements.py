"""Guided group configuration and scoped support/history views."""
from nexora import async_db as aiosqlite
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import DB_PATH
from app.handlers.admin import require_admin, require_admin_callback, resolve_target_user_id
from app.services.database import (get_settings, set_rules_text, set_welcome_text,
    set_log_chat, get_user_logs)
from app.services.templates import render_group_template

router = Router()


class Setup(StatesGroup):
    value = State()
    confirm = State()


@router.callback_query(F.data == "setup:home")
async def setup_home(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.clear()
    settings = await get_settings(callback.message.chat.id)
    kb = InlineKeyboardBuilder()
    for label, action in (("1 · Bienvenida", "welcome"), ("2 · Reglas", "rules"),
                          ("3 · Canal de logs", "logs")):
        kb.button(text=label, callback_data=f"setup:edit:{action}")
    kb.button(text="4 · Protecciones", callback_data="panel:security")
    kb.button(text="🏠 Menú", callback_data="mainmenu:home")
    kb.adjust(1)
    await callback.message.edit_text(
        f"🪄 Configuración de {callback.message.chat.title}\n\n"
        "Elige cada paso. Los textos se previsualizan antes de guardar.\n"
        f"Canal de logs: {settings.get('log_chat_id') or 'sin configurar'}\n"
        f"Antiflood: {'activo' if settings.get('antiflood') else 'inactivo'}",
        reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("setup:edit:"))
async def setup_edit(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    key = callback.data.rsplit(":", 1)[1]
    if key not in {"welcome", "rules", "logs"}:
        return
    await state.set_state(Setup.value)
    await state.update_data(key=key, chat_id=callback.message.chat.id)
    prompt = "Envía el ID del canal de logs (-100…)." if key == "logs" else "Envía el texto. Puedes usar {group}, {name} e {id}."
    await callback.message.reply(prompt + " Usa /cancelar para salir.")
    await callback.answer()


@router.message(Command("cancelar"), Setup.value)
@router.message(Command("cancelar"), Setup.confirm)
async def setup_cancel(message, state: FSMContext):
    await state.clear()
    await message.reply("✅ Configuración cancelada.")


@router.message(Setup.value, F.text)
async def setup_value(message, state: FSMContext):
    if not await require_admin(message, message.bot):
        return
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id:
        return
    value = message.text.strip()
    limit = 1000 if data["key"] == "welcome" else 3500
    if not value or len(value) > limit:
        await message.reply(f"Escribe entre 1 y {limit} caracteres.")
        return
    if data["key"] == "logs":
        if not value.startswith("-100") or not value[1:].isdigit():
            await message.reply("Usa un ID de canal válido: -100…")
            return
        try:
            admin = await message.bot.get_chat_member(int(value), message.from_user.id)
            bot_member = await message.bot.get_chat_member(int(value), message.bot.id)
            if admin.status not in {"creator", "administrator"} or not getattr(bot_member, "can_post_messages", False):
                raise ValueError()
        except Exception:
            await message.reply("Necesitas administrar ese canal y el bot debe tener permiso para publicar allí.")
            return
        preview = f"Canal de logs: {value}"
    else:
        preview = await render_group_template(message.bot, message.chat, message.from_user, value)
    await state.update_data(value=value)
    await state.set_state(Setup.confirm)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Guardar", callback_data="setup:save")
    kb.button(text="❌ Cancelar", callback_data="setup:home")
    await message.reply("👁 Vista previa\n\n" + preview, reply_markup=kb.as_markup())


@router.callback_query(F.data == "setup:save", Setup.confirm)
async def setup_save(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    data = await state.get_data()
    if data.get("chat_id") != callback.message.chat.id:
        return
    if data["key"] == "rules":
        await set_rules_text(data["chat_id"], data["value"])
    elif data["key"] == "welcome":
        await set_welcome_text(data["chat_id"], data["value"])
    else:
        from app.services.filters import is_admin
        if not await is_admin(callback.bot, int(data["value"]), callback.from_user.id):
            await callback.answer("Ya no tienes permisos en ese canal.", show_alert=True)
            return
        await set_log_chat(data["chat_id"], int(data["value"]))
    await state.clear()
    await setup_home(callback, state)


@router.message(Command("sanciones"))
async def sanctions(message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return
    user_id, _ = await resolve_target_user_id(message, command.args)
    if not user_id:
        await message.reply("Responde con /sanciones o usa /sanciones ID o @usuario.")
        return
    rows = await get_user_logs(message.chat.id, user_id, 30)
    rows = [r for r in rows if any(word in r[2] for word in ("BAN", "WARN", "MUTE"))]
    lines = [f"📋 Sanciones de {user_id} en este grupo"]
    for _, admin_id, action, reason, created in rows:
        lines.append(f"{created} · {action}\nAdmin: {admin_id or 'automático'} · {reason or 'sin motivo'}")
    await message.reply("\n\n".join(lines)[:4000] if rows else "No hay sanciones registradas en este grupo.")


@router.message(Command("miscasos"))
async def my_cases(message):
    async with aiosqlite.connect(DB_PATH) as db:
        tickets = await (await db.execute("SELECT id,status,reason FROM tickets WHERE user_id=? AND chat_id=? ORDER BY id DESC LIMIT 8", (message.from_user.id, message.chat.id))).fetchall()
        suggestions = await (await db.execute("SELECT id,status,text FROM suggestions WHERE user_id=? AND source_chat_id=? ORDER BY id DESC LIMIT 8", (message.from_user.id, message.chat.id))).fetchall()
        replies = await (await db.execute("SELECT kind,case_id,text FROM case_replies WHERE user_id=? AND chat_id=? ORDER BY id DESC LIMIT 5", (message.from_user.id, message.chat.id))).fetchall()
    lines = ["📬 Tus casos de este chat"]
    labels = {"open": "abierto", "closed": "cerrado", "answered": "respondido", "reviewed": "revisado"}
    for kind, rows in (("Ticket", tickets), ("Sugerencia", suggestions)):
        for case_id, status, text in rows:
            lines.append(f"{kind} #{case_id} · {labels.get(status, status)}\n{(text or '')[:160]}")
    for kind, case_id, text in replies:
        lines.append(f"💬 Respuesta · {kind} #{case_id}\n{text[:200]}")
    await message.reply("\n\n".join(lines)[:4000] if len(lines) > 1 else "No tienes casos en este chat.")


@router.message(Command("responderticket"))
async def reply_ticket(message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.reply("Uso: /responderticket ID respuesta")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT user_id,status FROM tickets WHERE id=? AND chat_id=?", (int(parts[0]), message.chat.id))).fetchone()
    if not row or row[1] != "open":
        await message.reply("El ticket no está abierto en este grupo.")
        return
    try:
        await message.bot.send_message(row[0], f"💬 Respuesta al ticket #{parts[0]} · {message.chat.title}\n\n{parts[1][:3000]}")
    except Exception:
        await message.reply("No pude entregar la respuesta. El usuario debe iniciar el bot en privado. El ticket sigue abierto.")
        return
    from app.services.database import add_log
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO case_replies(kind,case_id,chat_id,user_id,admin_id,text) VALUES('ticket',?,?,?,?,?)",
                         (int(parts[0]), message.chat.id, row[0], message.from_user.id, parts[1][:3000]))
        await db.commit()
    await add_log(message.chat.id, "TICKET_REPLY", user_id=row[0], admin_id=message.from_user.id, reason=f"Ticket #{parts[0]}: {parts[1][:1000]}")
    await message.reply(f"✅ Respuesta entregada al ticket #{parts[0]}. Puedes cerrarlo con /closeticket {parts[0]}.")
