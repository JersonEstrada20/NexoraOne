from time import perf_counter

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import DEFAULT_RULES_TEXT
from app.services.admin_logs import send_admin_log
from app.services.database import add_log, add_report, add_ticket, get_settings, get_group_stats, accept_rules, get_activity_total
from app.services.filters import is_admin
from app.services.templates import render_group_template
from app.services.message_ui import field, heading, notice, section

router = Router()


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    start = perf_counter()
    reply = await message.reply("⏳ Comprobando respuesta…")
    ms = int((perf_counter() - start) * 1000)
    try:
        await reply.edit_text(
            f"{heading('🏓', 'Pong')}\n\n{field('⚡', 'Tiempo de respuesta aproximado', f'{ms} ms')}",
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.message(Command("id"))
async def cmd_id(message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        text = "\n".join([
            heading("🪪", "Identificación"),
            field("👤", "Usuario", user.full_name),
            field("🆔", "ID", user.id, code=True),
        ])
    elif message.from_user:
        text = "\n".join([
            heading("🪪", "Tu identificación"),
            field("👤", "Usuario", message.from_user.full_name),
            field("🆔", "Tu ID", message.from_user.id, code=True),
            field("💬", "ID del chat", message.chat.id, code=True),
        ])
    else:
        return
    await message.reply(text, parse_mode="HTML")


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(notice("ℹ️", "Este comando está pensado para grupos."), parse_mode="HTML")
        return

    settings = await get_settings(message.chat.id)
    builder = InlineKeyboardBuilder()
    rules = settings["rules_text"]
    if rules == DEFAULT_RULES_TEXT or "no se han configurado" in rules.lower():
        builder.button(text="⚙️ Configurar reglas", callback_data="panel:how_rules")
        await message.reply(
            notice("📜", "Todavía no hay reglas configuradas para este grupo."),
            parse_mode="HTML", reply_markup=builder.as_markup(),
        )
    else:
        builder.button(text="✅ Acepto las reglas", callback_data=f"rulesaccept:{message.chat.id}")
        rendered_rules = await render_group_template(message.bot, message.chat, message.from_user, rules)
        await message.reply(rendered_rules, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("rulesaccept:"))
async def rules_accept_callback(callback: CallbackQuery):
    chat_id = int(callback.data.split(":", 1)[1])
    if not callback.message or callback.message.chat.id != chat_id:
        await callback.answer("Estas reglas no pertenecen a este grupo.", show_alert=True)
        return
    await accept_rules(chat_id, callback.from_user.id)
    await add_log(chat_id, "RULES_ACCEPTED", user_id=callback.from_user.id)
    await callback.answer("✅ Reglas aceptadas", show_alert=True)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(notice("ℹ️", "Este comando solo funciona en grupos."), parse_mode="HTML")
        return

    settings = await get_settings(message.chat.id)
    stats = await get_group_stats(message.chat.id)
    activity_messages, activity_users = await get_activity_total(message.chat.id)
    try:
        members = await message.bot.get_chat_member_count(message.chat.id)
    except Exception:
        members = "No disponible"

    switch = lambda value: "🟢 Activo" if value else "⚪ Desactivado"
    text = "\n".join([
        heading("📊", f"Estado de {message.chat.title or 'este grupo'}"),
        "",
        section("🛡️", "Protección"),
        field("👥", "Miembros", members),
        field("🔗", "Anti-enlaces", switch(settings["anti_link"])),
        field("⚡", "Antiflood", switch(settings["antiflood"])),
        field("🤖", "Captcha", switch(settings["captcha_enabled"])),
        field("⚠️", "Límite de advertencias", settings["warn_limit"]),
        field("🔇", "Silencio automático", f"{settings['auto_mute_minutes']} min"),
        "",
        section("📈", "Actividad"),
        field("🚫", "Palabras bloqueadas", stats["bad_words_count"]),
        field("👤", "Usuarios advertidos", stats["warned_users_count"]),
        field("🧾", "Registros", stats["logs_count"]),
        field("🚩", "Reportes abiertos", stats["open_reports_count"]),
        field("🎫", "Tickets abiertos", stats["open_tickets_count"]),
        field("💬", "Mensajes registrados", activity_messages),
        field("🌟", "Usuarios activos", activity_users),
        field("📡", "Canal de registros", "🟢 Configurado" if settings.get("log_chat_id") else "⚪ Sin configurar"),
    ])
    builder = InlineKeyboardBuilder()
    builder.button(text="🎛️ Abrir panel", callback_data="panel:home")
    builder.adjust(1)
    await message.reply(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.message(Command("report"))
async def cmd_report(message: Message, command: CommandObject):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(notice("ℹ️", "Este comando solo funciona en grupos."), parse_mode="HTML")
        return

    if not message.from_user or not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply(notice("📝", "Responde al mensaje que quieres reportar usando /report motivo_opcional"), parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user
    if target_user.id == message.from_user.id:
        await message.reply(notice("⚠️", "No puedes reportarte a ti mismo."), parse_mode="HTML")
        return

    if await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.reply(notice("🛡️", "Los administradores ya tienen herramientas directas de moderación."), parse_mode="HTML")
        return

    reason = command.args.strip() if command.args else None
    target_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    if target_text:
        target_text = target_text[:300]

    report_id = await add_report(
        chat_id=message.chat.id,
        reporter_id=message.from_user.id,
        target_user_id=target_user.id,
        target_message_text=target_text or None,
        reason=reason,
    )
    await add_log(
        message.chat.id,
        "REPORT_CREATED",
        user_id=target_user.id,
        admin_id=message.from_user.id,
        reason=f"report_id={report_id}" + (f" | motivo={reason}" if reason else ""),
    )
    await message.reply(notice("🚩", "Reporte recibido", f"ID #{report_id} · Un administrador lo revisará."), parse_mode="HTML")
    await send_admin_log(
        message.bot, message.chat.id, f"🚩 Nuevo reporte #{report_id}",
        user_id=target_user.id, admin_id=message.from_user.id,
        detail=reason or "Sin motivo",
    )


@router.message(Command("ticket"))
async def cmd_ticket(message: Message, command: CommandObject):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(notice("ℹ️", "Este comando solo funciona en grupos."), parse_mode="HTML")
        return
    if not message.from_user:
        return
    if await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.reply(notice("🛡️", "Los administradores pueden gestionar el grupo sin abrir tickets."), parse_mode="HTML")
        return

    reason = command.args.strip() if command.args else None
    ticket_id = await add_ticket(message.chat.id, message.from_user.id, reason)
    await add_log(
        message.chat.id,
        "TICKET_CREATED",
        user_id=message.from_user.id,
        reason=f"ticket_id={ticket_id}" + (f" | motivo={reason}" if reason else ""),
    )
    await message.reply(notice("🎫", "Solicitud de ayuda recibida", f"Ticket #{ticket_id} · Un administrador lo revisará."), parse_mode="HTML")
    await send_admin_log(
        message.bot, message.chat.id, f"🎫 Nuevo ticket #{ticket_id}",
        user_id=message.from_user.id, detail=reason or "Sin detalle",
    )


