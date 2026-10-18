"""Guided group configuration and scoped support/history views."""
from html import escape
import re
from zoneinfo import ZoneInfo

from nexora import async_db as aiosqlite
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import DB_PATH
from app.handlers.admin import require_admin, require_admin_callback, resolve_target_user_id
from app.services.database import (get_settings, set_rules_text, set_welcome_text,
    set_log_chat, get_user_logs, set_antiraid, set_night_mode)
from app.services.group_tools import list_filters, upsert_filter
from app.services.templates import render_group_template

router = Router()


class Setup(StatesGroup):
    value = State()
    confirm = State()
    filter = State()
    night_schedule = State()
    raid_config = State()


def setup_keyboard(settings, filter_count: int):
    kb = InlineKeyboardBuilder()
    buttons = (
        ("1 · Bienvenida", "setup:edit:welcome"),
        ("2 · Reglas", "setup:edit:rules"),
        ("3 · Canal de logs", "setup:edit:logs"),
        ("4 · Protecciones", "panel:security"),
        (f"🧩 Respuestas automáticas ({filter_count})", "setup:filters"),
        (f"🌙 Modo nocturno: {'ON' if settings.get('night_mode_enabled') else 'OFF'}", "setup:toggle:night"),
        ("🕒 Ajustar horario nocturno", "setup:night:schedule"),
        (f"🚨 Anti-raid: {'ON' if settings.get('antiraid_enabled') else 'OFF'}", "setup:toggle:raid"),
        ("⚙️ Umbral anti-raid", "setup:raid:config"),
    )
    for label, callback in buttons:
        kb.button(text=label, callback_data=callback)
    kb.button(text="🏠 Menú", callback_data="mainmenu:home")
    kb.adjust(2)
    return kb.as_markup()


async def show_setup(callback, settings=None):
    chat_id = callback.message.chat.id
    settings = settings or await get_settings(chat_id)
    filters = await list_filters(chat_id)
    await callback.message.edit_text(
        f"🪄 <b>Configuración guiada · {escape(callback.message.chat.title or 'grupo')}</b>\n\n"
        "Ajusta lo esencial con botones. Para bienvenida y reglas puedes revisar antes de guardar.\n\n"
        f"📡 Canal de registros: <code>{settings.get('log_chat_id') or 'sin configurar'}</code>\n"
        f"⚡ Antiflood: <b>{'activo' if settings.get('antiflood') else 'inactivo'}</b>\n"
        f"🌙 Modo nocturno: <b>{'activo' if settings.get('night_mode_enabled') else 'inactivo'}</b>"
        + (f" · {escape(str(settings.get('night_mode_start')))}–{escape(str(settings.get('night_mode_end')))} ({escape(str(settings.get('night_mode_timezone')))})" if settings.get('night_mode_enabled') else "")
        + f"\n🚨 Anti-raid: <b>{'activo' if settings.get('antiraid_enabled') else 'inactivo'}</b>"
        + (f" · {settings.get('raid_join_threshold', 8)} ingresos/{settings.get('raid_window_seconds', 30)} s" if settings.get('antiraid_enabled') else "")
        + f"\n🧩 Respuestas automáticas: <b>{len(filters)}</b>",
        parse_mode="HTML", reply_markup=setup_keyboard(settings, len(filters)))


@router.callback_query(F.data == "setup:home")
async def setup_home(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.clear()
    await show_setup(callback)
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


@router.callback_query(F.data.startswith("setup:toggle:"))
async def setup_toggle(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.clear()
    chat_id = callback.message.chat.id
    settings = await get_settings(chat_id)
    target = callback.data.rsplit(":", 1)[1]
    if target == "raid":
        enabled = not settings.get("antiraid_enabled", False)
        await set_antiraid(chat_id, enabled, settings.get("raid_join_threshold", 8), settings.get("raid_window_seconds", 30))
        notice = (
            f"🚨 Anti-raid activado: CAPTCHA al detectar {settings.get('raid_join_threshold', 8)} ingresos "
            f"en {settings.get('raid_window_seconds', 30)} s."
            if enabled else "🚨 Anti-raid desactivado."
        )
    elif target == "night":
        enabled = not settings.get("night_mode_enabled", False)
        await set_night_mode(
            chat_id, enabled,
            settings.get("night_mode_start", "22:00"),
            settings.get("night_mode_end", "07:00"),
            settings.get("night_mode_timezone", "America/Santiago"),
        )
        notice = (
            f"🌙 Modo nocturno activado: {settings.get('night_mode_start', '22:00')}–"
            f"{settings.get('night_mode_end', '07:00')} ({settings.get('night_mode_timezone', 'America/Santiago')})."
            if enabled else "🌙 Modo nocturno desactivado."
        )
    else:
        await callback.answer("Esta opción ya no está disponible.", show_alert=True)
        return
    await callback.answer(notice[:180])
    await show_setup(callback)


@router.callback_query(F.data == "setup:filters")
async def setup_filters(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.clear()
    rows = await list_filters(callback.message.chat.id)
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Crear respuesta", callback_data="setup:filter:add")
    kb.button(text="↩️ Configuración", callback_data="setup:home")
    kb.adjust(2)
    if rows:
        lines = [f"• <code>{escape(trigger)}</code> · {kind} → {escape(response[:50])}" for trigger, kind, response in rows[:20]]
        text = "🧩 <b>Respuestas automáticas</b>\n\n" + "\n".join(lines)
        if len(rows) > 20:
            text += f"\n\nY {len(rows) - 20} más. Usa /filters para ver la lista completa."
        text += "\n\nPara borrar una, usa <code>/stop frase</code>."
    else:
        text = "🧩 <b>Respuestas automáticas</b>\n\nTodavía no hay respuestas. Crea una para que el bot responda cuando un miembro escriba una frase."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "setup:filter:add")
async def setup_filter_add(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.set_state(Setup.filter)
    await state.update_data(chat_id=callback.message.chat.id)
    await callback.message.reply(
        "Envía <code>frase | respuesta</code>. Ejemplo: <code>horario | Abrimos de lunes a viernes.</code>\n"
        "Para enviar foto, audio, video o GIF, usa /filter respondiendo al contenido.\nUsa /cancelar para volver.",
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "setup:night:schedule")
async def setup_night_schedule(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.set_state(Setup.night_schedule)
    settings = await get_settings(callback.message.chat.id)
    await state.update_data(chat_id=callback.message.chat.id, timezone=settings.get("night_mode_timezone", "America/Santiago"))
    await callback.message.reply(
        "Envía hora de inicio y fin en formato 24 h, más una zona horaria opcional.\n"
        f"Ejemplo: <code>22:00 07:00 {escape(settings.get('night_mode_timezone', 'America/Santiago'))}</code>\n"
        "Al guardar, el modo nocturno queda activado. Usa /cancelar para salir.",
        parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "setup:raid:config")
async def setup_raid_config(callback, state: FSMContext):
    if not await require_admin_callback(callback):
        return
    await state.set_state(Setup.raid_config)
    await state.update_data(chat_id=callback.message.chat.id)
    settings = await get_settings(callback.message.chat.id)
    await callback.message.reply(
        f"Envía cantidad de ingresos y ventana en segundos, por ejemplo <code>{settings.get('raid_join_threshold', 8)} {settings.get('raid_window_seconds', 30)}</code>.\n"
        "Rangos: 3–100 ingresos y 10–300 segundos. Usa /cancelar para salir.",
        parse_mode="HTML")
    await callback.answer()


@router.message(Command("cancelar"), Setup.value)
@router.message(Command("cancelar"), Setup.confirm)
@router.message(Command("cancelar"), Setup.filter)
@router.message(Command("cancelar"), Setup.night_schedule)
@router.message(Command("cancelar"), Setup.raid_config)
async def setup_cancel(message, state: FSMContext):
    await state.clear()
    if message.chat.type in {"group", "supergroup"}:
        await message.reply("✅ Configuración cancelada. Abre el panel guiado cuando quieras continuar.")
    else:
        await message.reply("✅ Configuración cancelada.")


@router.message(Setup.filter, F.text)
async def setup_filter_value(message, state: FSMContext):
    if not await require_admin(message, message.bot):
        return
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id:
        return
    if "|" not in message.text:
        await message.reply("Separa la frase y la respuesta con <code>|</code>. Ejemplo: <code>horario | Abrimos a las 9.</code>", parse_mode="HTML")
        return
    trigger, response = (part.strip() for part in message.text.split("|", 1))
    if not trigger or len(trigger) > 64 or not response or len(response) > 4096:
        await message.reply("La frase debe tener 1–64 caracteres y la respuesta 1–4096 caracteres.")
        return
    await upsert_filter(message.chat.id, trigger, "contains", response, message.from_user.id)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🧩 Ver respuestas", callback_data="setup:filters")
    kb.button(text="🪄 Panel guiado", callback_data="setup:home")
    kb.adjust(2)
    await message.reply(
        f"✅ Guardé la respuesta para <code>{escape(trigger)}</code>. Se activa si la frase aparece en un mensaje.",
        parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(Setup.night_schedule, F.text)
async def setup_night_schedule_value(message, state: FSMContext):
    if not await require_admin(message, message.bot):
        return
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id:
        return
    parts = message.text.split()
    if len(parts) not in {2, 3} or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value) for value in parts[:2]):
        await message.reply("Formato inválido. Usa <code>22:00 07:00 America/Santiago</code>.", parse_mode="HTML")
        return
    start, end = parts[:2]
    timezone = parts[2] if len(parts) == 3 else data.get("timezone", "America/Santiago")
    try:
        ZoneInfo(timezone)
    except (KeyError, ValueError):
        await message.reply("Zona horaria inválida. Ejemplo: <code>America/Santiago</code>.", parse_mode="HTML")
        return
    if start == end:
        await message.reply("La hora inicial y final no pueden ser iguales.")
        return
    await set_night_mode(message.chat.id, True, start, end, timezone)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🪄 Volver al panel guiado", callback_data="setup:home")
    await message.reply(
        f"✅ Modo nocturno activado de <b>{start} a {end}</b> ({escape(timezone)}).",
        parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(Setup.raid_config, F.text)
async def setup_raid_config_value(message, state: FSMContext):
    if not await require_admin(message, message.bot):
        return
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id:
        return
    parts = message.text.split()
    try:
        threshold, window = map(int, parts)
    except (ValueError, TypeError):
        await message.reply("Envía dos números, por ejemplo <code>8 30</code>.", parse_mode="HTML")
        return
    if not 3 <= threshold <= 100 or not 10 <= window <= 300:
        await message.reply("Usa 3–100 ingresos y una ventana de 10–300 segundos.")
        return
    settings = await get_settings(message.chat.id)
    await set_antiraid(message.chat.id, settings.get("antiraid_enabled", False), threshold, window)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="🪄 Volver al panel guiado", callback_data="setup:home")
    status = "activa" if settings.get("antiraid_enabled") else "configurado, pero apagado"
    await message.reply(
        f"✅ Umbral anti-raid {status}: {threshold} ingresos en {window} segundos.",
        reply_markup=kb.as_markup())


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
