from html import escape
import json
from types import SimpleNamespace

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ChatPermissions, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.database import (
    get_settings,
    get_bad_words,
    set_anti_link,
    set_antiflood,
    set_captcha_enabled,
    set_warn_limit,
    set_auto_mute_minutes,
    set_flood_limit,
    set_welcome_text,
    set_rules_text,
    set_farewell,
    set_progressive_sanctions,
    set_log_chat,
    set_welcome_media,
    add_bad_word,
    del_bad_word,
    add_warn,
    remove_warn,
    get_warns,
    reset_warns,
    get_logs,
    get_user_logs,
    add_log,
    get_open_reports,
    close_report,
    set_staff_nickname,
    remove_staff_nickname,
    get_staff_nickname,
    set_staff_role,
    remove_staff_role,
    get_staff_role,
    get_registered_staff,
    get_open_tickets,
    close_ticket,
    set_approval_enabled,
)
from app.services.admin_logs import send_admin_log
from app.services.group_tools import get_locks, list_whitelist, set_lock
from app.handlers.config_transfer import build_group_export
from app.services.filters import (
    is_admin,
    parse_duration_to_minutes,
    mute_until,
    parse_int,
    full_unrestrict_permissions,
)

router = Router()


class PanelEdit(StatesGroup):
    welcome = State()
    rules = State()
    farewell = State()

PROMOTE_PRESETS = {
    "helper": {
        "label": "Helper",
        "permissions": {
            "can_delete_messages": False,
            "can_invite_users": True,
            "can_restrict_members": False,
            "can_pin_messages": False,
            "can_manage_video_chats": False,
            "can_promote_members": False,
            "can_manage_topics": False,
            "can_post_stories": False,
            "can_edit_stories": False,
            "can_delete_stories": False,
            "can_change_info": False,
        },
    },
    "mod": {
        "label": "Moderador",
        "permissions": {
            "can_delete_messages": True,
            "can_invite_users": True,
            "can_restrict_members": True,
            "can_pin_messages": False,
            "can_manage_video_chats": False,
            "can_promote_members": False,
            "can_manage_topics": False,
            "can_post_stories": False,
            "can_edit_stories": False,
            "can_delete_stories": False,
            "can_change_info": False,
        },
    },
    "supermod": {
        "label": "SuperMod",
        "permissions": {
            "can_delete_messages": True,
            "can_invite_users": True,
            "can_restrict_members": True,
            "can_pin_messages": True,
            "can_manage_video_chats": True,
            "can_promote_members": False,
            "can_manage_topics": True,
            "can_post_stories": False,
            "can_edit_stories": False,
            "can_delete_stories": False,
            "can_change_info": False,
        },
    },
    "fulladmin": {
        "label": "Admin Total",
        "permissions": {
            "can_delete_messages": True,
            "can_invite_users": True,
            "can_restrict_members": True,
            "can_pin_messages": True,
            "can_manage_video_chats": True,
            "can_promote_members": True,
            "can_manage_topics": True,
            "can_post_stories": True,
            "can_edit_stories": True,
            "can_delete_stories": True,
            "can_change_info": True,
        },
    },
}


async def require_admin(message: Message, bot) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("❌ Este comando solo funciona en grupos.")
        return False

    # Cuando un admin habla en modo anónimo, Telegram envía el mensaje como el chat.
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return True

    if not message.from_user:
        return False

    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("⛔ Solo los administradores pueden usar este comando.")
        return False

    return True


async def require_admin_callback(callback: CallbackQuery) -> bool:
    if not callback.message or not callback.from_user:
        return False

    if not await is_admin(callback.bot, callback.message.chat.id, callback.from_user.id):
        await callback.answer("Solo admins.", show_alert=True)
        return False

    return True


def get_target_user(message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


def extract_user_id_from_args(args: str | None):
    if not args:
        return None

    raw = args.strip()
    if raw.startswith("@"):
        return None

    try:
        return int(raw)
    except Exception:
        return None


def split_once_args(args: str | None):
    if not args:
        return None, None

    parts = args.strip().split(maxsplit=1)
    first = parts[0] if parts else None
    rest = parts[1].strip() if len(parts) > 1 else None
    return first, rest


def normalize_staff_nickname(raw: str | None):
    if not raw:
        return None

    nickname = " ".join(raw.split()).strip()
    if not nickname:
        return None

    return nickname[:16]


def normalize_staff_role(raw: str | None):
    if not raw:
        return None

    role = " ".join(raw.split()).strip()
    if not role:
        return None

    return role[:24]


async def resolve_target_user_id(message: Message, args: str | None):
    target_user = get_target_user(message)
    if target_user:
        return target_user.id, target_user.full_name

    first = (args or "").split(maxsplit=1)
    target_user_id = extract_user_id_from_args(first[0] if first else None)
    if target_user_id:
        return target_user_id, str(target_user_id)

    if first and first[0].startswith("@"):
        from app.services.user_directory import resolve_username
        target_user_id = await resolve_username(message.bot, message.chat.id, first[0])
        if target_user_id:
            return target_user_id, first[0]
    return None, None


async def moderation_target(message, args):
    user_id, name = await resolve_target_user_id(message, args)
    remaining = args or ""
    if not get_target_user(message):
        parts = remaining.split(maxsplit=1)
        remaining = parts[1] if len(parts) > 1 else ""
    return (SimpleNamespace(id=user_id, full_name=name) if user_id else None), remaining


async def set_admin_custom_title_safe(message: Message, user_id: int, nickname: str | None):
    try:
        await message.bot.set_chat_administrator_custom_title(
            chat_id=message.chat.id,
            user_id=user_id,
            custom_title=nickname or ""
        )
        return True
    except Exception:
        return False


async def promote_user_with_preset(message: Message, user_id: int, preset_key: str):
    preset = PROMOTE_PRESETS[preset_key]
    await message.bot.promote_chat_member(
        chat_id=message.chat.id,
        user_id=user_id,
        **preset["permissions"],
    )


async def register_staff_member(chat_id: int, user_id: int, nickname: str | None = None):
    current_nickname = await get_staff_nickname(chat_id, user_id)
    if nickname is not None:
        await set_staff_nickname(chat_id, user_id, nickname)
        return

    if current_nickname is None:
        await set_staff_nickname(chat_id, user_id, "")


def promote_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    for key, preset in PROMOTE_PRESETS.items():
        builder.button(
            text=preset["label"],
            callback_data=f"promote:{user_id}:{key}"
        )
    builder.adjust(1)
    return builder.as_markup()


def panel_keyboard(settings: dict, section: str = "home"):
    builder = InlineKeyboardBuilder()
    if section == "home":
        builder.button(text="🛡 Seguridad", callback_data="panel:security")
        builder.button(text="👋 Bienvenida y reglas", callback_data="panel:content")
        builder.button(text="🚨 Sanciones", callback_data="panel:sanctions")
        builder.button(text="👥 Gestión", callback_data="panel:management")
        builder.button(text="🧰 Bloqueos y permisos", callback_data="panel:tools")
        builder.button(text="🔄 Actualizar", callback_data="panel:home")
        builder.button(text="📚 Menú general", callback_data="mainmenu:home")
        builder.button(text="❌ Cerrar", callback_data="panel:close")
        builder.adjust(2, 2, 2, 1)
    elif section == "security":
        builder.button(text=f"🔗 Anti-link: {'ON' if settings['anti_link'] else 'OFF'}", callback_data="panel:toggle_antilink")
        builder.button(text=f"⚡ Antiflood: {'ON' if settings['antiflood'] else 'OFF'}", callback_data="panel:toggle_antiflood")
        builder.button(text=f"🛡 Captcha: {'ON' if settings['captcha_enabled'] else 'OFF'}", callback_data="panel:toggle_captcha")
        builder.button(text=f"👤 Aprobación manual: {'ON' if settings.get('approval_enabled') else 'OFF'}", callback_data="panel:toggle_approval")
        builder.button(text="🏠 Inicio", callback_data="panel:home")
        builder.button(text="📚 Menú", callback_data="mainmenu:home")
        builder.adjust(1)
    elif section == "content":
        builder.button(text="👁 Ver bienvenida", callback_data="panel:preview_welcome")
        builder.button(text="✏️ Cambiar bienvenida", callback_data="panel:how_welcome")
        builder.button(text="👁 Ver reglas", callback_data="panel:preview_rules")
        builder.button(text="✏️ Cambiar reglas", callback_data="panel:how_rules")
        builder.button(text=f"👋 Despedida: {'ON' if settings['farewell_enabled'] else 'OFF'}", callback_data="panel:toggle_farewell")
        builder.button(text="✏️ Cambiar despedida", callback_data="panel:how_farewell")
        builder.button(text="🖼 Foto/GIF", callback_data="panel:how_media")
        builder.button(text="🗑 Quitar multimedia", callback_data="panel:del_media")
        builder.button(text="📊 Crear encuesta", callback_data="panel:how_poll")
        builder.button(text="🏠 Inicio", callback_data="panel:home")
        builder.button(text="📚 Menú", callback_data="mainmenu:home")
        builder.adjust(2, 2, 2, 2, 2)
    elif section == "sanctions":
        builder.button(text=f"📈 Progresivas: {'ON' if settings['progressive_sanctions'] else 'OFF'}", callback_data="panel:toggle_progressive")
        builder.button(text="⚠️ Warns", callback_data="panel:how_warns")
        builder.button(text="🔇 Mutes", callback_data="panel:how_mutes")
        builder.button(text="📋 Logs", callback_data="panel:open_logs")
        builder.button(text="📡 Canal de logs", callback_data="panel:how_logchannel")
        builder.button(text="🏠 Inicio", callback_data="panel:home")
        builder.button(text="📚 Menú", callback_data="mainmenu:home")
        builder.adjust(1, 2, 2, 2)
    elif section == "management":
        builder.button(text="👥 Staff", callback_data="center:staff")
        builder.button(text="🚩 Reportes", callback_data="center:reports")
        builder.button(text="🎫 Tickets", callback_data="center:tickets")
        builder.button(text="🎛 Centro completo", callback_data="center:home")
        builder.button(text="📦 Exportar configuración", callback_data="panel:export_config")
        builder.button(text="🏠 Inicio", callback_data="panel:home")
        builder.button(text="📚 Menú", callback_data="mainmenu:home")
        builder.adjust(2, 2, 2)
    elif section == "tools":
        for kind, label in (("fotos", "📷 Fotos"), ("videos", "🎬 Videos"), ("gifs", "🎞 GIF"),
                            ("stickers", "😀 Stickers"), ("audios", "🎵 Audios"),
                            ("documentos", "📄 Documentos"), ("encuestas", "📊 Encuestas")):
            builder.button(text=label, callback_data=f"panel:lock_{kind}")
        builder.button(text="🔗 Ver listas blancas", callback_data="panel:whitelists")
        builder.button(text="🏠 Inicio", callback_data="panel:home")
        builder.adjust(2, 2, 2, 1, 1, 1)
    return builder.as_markup()


def panel_home_text(settings: dict, bad_words: list[str]) -> str:
    return (
        "🎛 <b>Panel del grupo</b>\n\n"
        f"🔗 Anti-link: <b>{'ON' if settings['anti_link'] else 'OFF'}</b>\n"
        f"⚡ Antiflood: <b>{'ON' if settings['antiflood'] else 'OFF'}</b>\n"
        f"🛡 Captcha: <b>{'ON' if settings['captcha_enabled'] else 'OFF'}</b>\n"
        f"⚠️ Warns para auto-mute: <b>{settings['warn_limit']}</b>\n"
        f"🧹 Palabras bloqueadas: <b>{len(bad_words)}</b>\n\n"
        "Elige una sección para administrar el grupo."
    )


def control_center_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🛡 Staff", callback_data="center:staff")
    builder.button(text="👮 Admins", callback_data="center:admins")
    builder.button(text="🚩 Reportes", callback_data="center:reports")
    builder.button(text="🎫 Tickets", callback_data="center:tickets")
    builder.button(text="⚙️ Config", callback_data="center:settings")
    builder.button(text="⭐ Atajos", callback_data="center:shortcuts")
    builder.button(text="🎛 Panel del grupo", callback_data="panel:home")
    builder.button(text="📚 Menú general", callback_data="mainmenu:home")
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


def center_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Volver", callback_data="center:home")
    builder.button(text="🎛 Panel", callback_data="panel:home")
    builder.adjust(2)
    return builder.as_markup()


def center_reports_keyboard(reports: list[tuple]):
    builder = InlineKeyboardBuilder()
    for report_id, *_ in reports[:5]:
        builder.button(text=f"✅ Cerrar #{report_id}", callback_data=f"centerclose:report:{report_id}")
    builder.button(text="⬅️ Volver", callback_data="center:home")
    builder.adjust(1)
    return builder.as_markup()


def center_tickets_keyboard(tickets: list[tuple]):
    builder = InlineKeyboardBuilder()
    for ticket_id, *_ in tickets[:5]:
        builder.button(text=f"✅ Cerrar #{ticket_id}", callback_data=f"centerclose:ticket:{ticket_id}")
    builder.button(text="⬅️ Volver", callback_data="center:home")
    builder.adjust(1)
    return builder.as_markup()


async def build_staff_text(bot, chat_id: int):
    registered_staff = await get_registered_staff(chat_id)
    if not registered_staff:
        return (
            "🛡 <b>Staff registrado</b>\n\n"
            "No hay staff registrado todavía.\n"
            "Usa <code>/promote</code>, <code>/staffnick</code> o <code>/staffrole</code>."
        )

    admins = await bot.get_chat_administrators(chat_id)
    admin_map = {member.user.id: member for member in admins}
    lines = []

    for user_id, nickname, staff_role in registered_staff:
        member = admin_map.get(user_id)
        if member:
            user = member.user
            telegram_role = "Dueño" if getattr(member, "status", "") == "creator" else "Admin"
            line = f"• {user.full_name} ({user_id}) - {telegram_role}"
        else:
            line = f"• Usuario {user_id} - ya no es admin"

        if staff_role:
            line += f" | rango: {staff_role}"
        if nickname:
            line += f" | apodo: {nickname}"
        lines.append(line)

    return "🛡 <b>Staff registrado</b>\n\n" + "\n".join(lines)


async def build_admins_text(bot, chat_id: int):
    admins = await bot.get_chat_administrators(chat_id)
    lines = []

    for member in admins:
        user = member.user
        telegram_role = "Dueño" if getattr(member, "status", "") == "creator" else "Admin"
        title = getattr(member, "custom_title", None)
        staff_role = await get_staff_role(chat_id, user.id)
        nickname = await get_staff_nickname(chat_id, user.id)

        line = f"• {user.full_name} ({user.id}) - {telegram_role}"
        if title:
            line += f" | título: {title}"
        if staff_role:
            line += f" | rango staff: {staff_role}"
        if nickname:
            line += f" | apodo staff: {nickname}"
        lines.append(line)

    return "👮 <b>Admins de Telegram</b>\n\n" + "\n".join(lines)


async def build_reports_text(chat_id: int):
    reports = await get_open_reports(chat_id, limit=10)
    if not reports:
        return "🚩 <b>Reportes abiertos</b>\n\nNo hay reportes abiertos.", center_back_keyboard()

    lines = []
    for report_id, reporter_id, target_user_id, target_message_text, reason, created_at in reports:
        line = f"• #{report_id} [{created_at}] reportero: {reporter_id} | usuario: {target_user_id}"
        if reason:
            line += f" | motivo: {reason}"
        if target_message_text:
            sanitized = " ".join(target_message_text.split())
            line += f" | msg: {sanitized[:70]}"
        lines.append(line)

    return (
        "🚩 <b>Reportes abiertos</b>\n\n"
        + "\n".join(lines)
        + "\n\nPuedes cerrarlos desde los botones o con <code>/closereport ID</code>.",
        center_reports_keyboard(reports)
    )


async def build_tickets_text(chat_id: int):
    tickets = await get_open_tickets(chat_id, limit=10)
    if not tickets:
        return "🎫 <b>Tickets abiertos</b>\n\nNo hay tickets abiertos.", center_back_keyboard()

    lines = []
    for ticket_id, user_id, reason, created_at in tickets:
        line = f"• #{ticket_id} [{created_at}] usuario: {user_id}"
        if reason:
            line += f" | motivo: {reason[:100]}"
        lines.append(line)

    return (
        "🎫 <b>Tickets abiertos</b>\n\n"
        + "\n".join(lines)
        + "\n\nPuedes cerrarlos desde los botones o con <code>/closeticket ID</code>.",
        center_tickets_keyboard(tickets)
    )


async def build_settings_text(chat_id: int):
    settings = await get_settings(chat_id)
    bad_words = await get_bad_words(chat_id)
    return (
        "<b>⚙️ Configuración actual</b>\n\n"
        + format_settings_text(settings, bad_words)
    )


def build_shortcuts_text():
    return """
⭐ <b>Atajos útiles</b>

• Responde + <code>/warn spam</code>
• Responde + <code>/mute 10m flood</code>
• Responde + <code>/bang estafa</code>
• Responde + <code>/acciones</code>
• Responde + <code>/promotebtn</code>
• <code>/menu</code> para abrir todos los controles
• <code>/staff</code> y <code>/admins</code>
• <code>/reports</code> y <code>/tickets</code>
• <code>/stats</code> para ver el estado del grupo
""".strip()


def user_actions_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Warn", callback_data=f"useract:warn:{user_id}")
    builder.button(text="➖ Unwarn", callback_data=f"useract:unwarn:{user_id}")
    builder.button(text="🔇 10m", callback_data=f"useract:mute10:{user_id}")
    builder.button(text="🔕 1h", callback_data=f"useract:mute60:{user_id}")
    builder.button(text="🔊 Unmute", callback_data=f"useract:unmute:{user_id}")
    builder.button(text="⛔ Ban", callback_data=f"useract:ban:{user_id}")
    builder.button(text="📄 Perfil", callback_data=f"useract:profile:{user_id}")
    builder.button(text="🆔 Ver ID", callback_data=f"useract:id:{user_id}")
    builder.button(text="❌ Cerrar", callback_data=f"useract:close:{user_id}")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


async def build_user_actions_text(chat_id: int, user_id: int, display_name: str | None = None):
    warns = await get_warns(chat_id, user_id)
    name = escape(display_name or f"Usuario {user_id}")
    return (
        "🎯 <b>Acciones rápidas</b>\n\n"
        f"👤 {name}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"⚠️ Warns actuales: <b>{warns}</b>\n\n"
        "Usa los botones para moderar rápido."
    )


async def build_user_profile_text(bot, chat_id: int, user_id: int, display_name: str | None = None):
    warns = await get_warns(chat_id, user_id)
    logs = await get_user_logs(chat_id, user_id, limit=5)
    staff_role = await get_staff_role(chat_id, user_id)
    nickname = await get_staff_nickname(chat_id, user_id)
    name = escape(display_name or f"Usuario {user_id}")

    is_user_admin = await is_admin(bot, chat_id, user_id)

    lines = [
        "📄 <b>Perfil de moderación</b>",
        "",
        f"👤 {name}",
        f"🆔 <code>{user_id}</code>",
        f"🛡 Estado: {'Admin' if is_user_admin else 'Miembro'}",
        f"⚠️ Warns: <b>{warns}</b>",
    ]

    if staff_role:
        lines.append(f"🏷 Rango staff: {escape(staff_role)}")
    if nickname:
        lines.append(f"✨ Apodo staff: {escape(nickname)}")

    if logs:
        lines.append("")
        lines.append("<b>Últimos movimientos</b>")
        for _, admin_id, action, reason, created_at in logs:
            line = f"• [{created_at}] {escape(action)}"
            if admin_id:
                line += f" | admin: {admin_id}"
            if reason:
                line += f" | {escape(reason[:80])}"
            lines.append(line)
    else:
        lines.append("")
        lines.append("Sin historial reciente en logs.")

    return "\n".join(lines)


def format_settings_text(settings: dict, bad_words: list[str]) -> str:
    return (
        "⚙️ Panel de configuración del grupo\n\n"
        f"🔗 Anti-link: {'ON' if settings['anti_link'] else 'OFF'}\n"
        f"⚡ Antiflood: {'ON' if settings['antiflood'] else 'OFF'}\n"
        f"🛡 Captcha: {'ON' if settings['captcha_enabled'] else 'OFF'}\n"
        f"🚨 Límite de warns: {settings['warn_limit']}\n"
        f"🔇 Auto mute: {settings['auto_mute_minutes']} min\n"
        f"📨 Flood: {settings['flood_max_messages']} mensajes / {settings['flood_window_seconds']} seg\n"
        f"👋 Bienvenida: {settings['welcome_text']}\n"
        f"📜 Reglas: {settings['rules_text']}\n"
        f"🧹 Palabras bloqueadas: {', '.join(bad_words) if bad_words else 'ninguna'}\n\n"
        "Usa los botones para activar o desactivar funciones rápidas."
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    settings = await get_settings(message.chat.id)
    bad_words = await get_bad_words(message.chat.id)
    await message.reply(format_settings_text(settings, bad_words))


@router.message(Command("setlogchannel"))
async def cmd_set_log_channel(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return
    value = (command.args or "").strip().lower()
    if value == "off":
        await set_log_chat(message.chat.id, None)
        await message.reply("✅ Canal de logs desactivado.")
        return
    try:
        log_chat_id = int(value)
    except ValueError:
        await message.reply("Usa /setlogchannel -1001234567890 o /setlogchannel off")
        return
    try:
        if not await is_admin(message.bot, log_chat_id, message.from_user.id):
            await message.reply("Solo puedes conectar un canal que administras.")
            return
        await message.bot.send_message(log_chat_id, f"✅ Canal conectado con {message.chat.title} · ID {message.chat.id}.")
    except Exception:
        await message.reply("❌ No pude escribir en ese canal. Agrega el bot como administrador y revisa el ID.")
        return
    await set_log_chat(message.chat.id, log_chat_id)
    await add_log(message.chat.id, "SET_LOG_CHANNEL", admin_id=message.from_user.id, reason=str(log_chat_id))
    await message.reply(f"✅ Canal de logs configurado: {log_chat_id}")


@router.message(Command("setwelcomemedia"))
async def cmd_set_welcome_media(message: Message):
    if not await require_admin(message, message.bot):
        return
    replied = message.reply_to_message
    if not replied:
        await message.reply("Envía una foto o GIF y respóndelo con /setwelcomemedia")
        return
    if replied.photo:
        file_id, media_type = replied.photo[-1].file_id, "photo"
    elif replied.animation:
        file_id, media_type = replied.animation.file_id, "animation"
    else:
        await message.reply("Solo se admite una foto o un GIF/animación de Telegram.")
        return
    await set_welcome_media(message.chat.id, file_id, media_type)
    await message.reply("✅ Multimedia de bienvenida guardada para este grupo.")


@router.message(Command("delwelcomemedia"))
async def cmd_del_welcome_media(message: Message):
    if not await require_admin(message, message.bot):
        return
    await set_welcome_media(message.chat.id, None, None)
    await message.reply("✅ Multimedia de bienvenida eliminada.")


@router.message(Command("staff"))
async def cmd_staff(message: Message):
    if not await require_admin(message, message.bot):
        return

    registered_staff = await get_registered_staff(message.chat.id)
    if not registered_staff:
        await message.reply(
            "🛡 No hay staff registrado todavía.\n\n"
            "Usa /promote para agregar admins al staff o /staffnick y /staffrole para organizarlos."
        )
        return

    admins = await message.bot.get_chat_administrators(message.chat.id)
    admin_map = {member.user.id: member for member in admins}
    lines = []

    for user_id, nickname, staff_role in registered_staff:
        member = admin_map.get(user_id)
        if member:
            user = member.user
            telegram_role = "Dueño" if getattr(member, "status", "") == "creator" else "Admin"
            display_name = user.full_name
            title = getattr(member, "custom_title", None)
            line = f"• {display_name} (`{user_id}`) - {telegram_role}"
            if staff_role:
                line += f" | rango: {staff_role}"
            if nickname:
                line += f" | apodo: {nickname}"
            elif title:
                line += f" | título: {title}"
        else:
            line = f"• Usuario `{user_id}` - ya no es admin"
            if staff_role:
                line += f" | rango: {staff_role}"
            if nickname:
                line += f" | apodo: {nickname}"
        lines.append(line)

    await message.reply(
        "🛡 Staff registrado:\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


@router.message(Command("admins"))
async def cmd_admins(message: Message):
    if not await require_admin(message, message.bot):
        return

    admins = await message.bot.get_chat_administrators(message.chat.id)
    lines = []

    for member in admins:
        user = member.user
        telegram_role = "Dueño" if getattr(member, "status", "") == "creator" else "Admin"
        title = getattr(member, "custom_title", None)
        staff_role = await get_staff_role(message.chat.id, user.id)
        nickname = await get_staff_nickname(message.chat.id, user.id)

        line = f"• {user.full_name} (`{user.id}`) - {telegram_role}"
        if title:
            line += f" | título: {title}"
        if staff_role:
            line += f" | rango staff: {staff_role}"
        if nickname:
            line += f" | apodo staff: {nickname}"
        lines.append(line)

    await message.reply(
        "👮 Admins de Telegram:\n\n" + "\n".join(lines),
        parse_mode="Markdown"
    )


@router.message(Command("promotebtn"))
@router.message(Command("staffadd"))
async def cmd_promotebtn(message: Message):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    if not user:
        await message.reply("Responde al usuario que quieres promover y usa /promotebtn")
        return

    if await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("Ese usuario ya es administrador.")
        return

    await message.reply(
        f"Selecciona el nivel de permisos para {user.full_name}:",
        reply_markup=promote_keyboard(user.id)
    )


@router.message(Command("acciones"))
@router.message(Command("modpanel"))
@router.message(Command("mod"))
async def cmd_user_actions(message: Message):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    if not user:
        await message.reply("Responde al mensaje del usuario y usa /acciones")
        return

    text = await build_user_actions_text(message.chat.id, user.id, user.full_name)
    await message.reply(
        text,
        parse_mode="HTML",
        reply_markup=user_actions_keyboard(user.id)
    )


@router.message(Command("infouser"))
async def cmd_user_profile(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    target_user = get_target_user(message)
    target_user_id = target_user.id if target_user else extract_user_id_from_args(command.args)
    display_name = target_user.full_name if target_user else None

    if not target_user_id:
        await message.reply("Responde al usuario con /perfil o usa /perfil 123456789")
        return

    text = await build_user_profile_text(message.bot, message.chat.id, target_user_id, display_name)
    await message.reply(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("promote:"))
async def promote_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    if not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Acción inválida.", show_alert=True)
        return

    try:
        target_user_id = int(parts[1])
    except Exception:
        await callback.answer("Usuario inválido.", show_alert=True)
        return

    preset_key = parts[2]
    if preset_key not in PROMOTE_PRESETS:
        await callback.answer("Perfil inválido.", show_alert=True)
        return

    if await is_admin(callback.bot, callback.message.chat.id, target_user_id):
        await callback.answer("Ese usuario ya es admin.", show_alert=True)
        return

    try:
        await callback.bot.promote_chat_member(
            chat_id=callback.message.chat.id,
            user_id=target_user_id,
            **PROMOTE_PRESETS[preset_key]["permissions"],
        )
        await register_staff_member(callback.message.chat.id, target_user_id)
    except Exception as exc:
        await callback.answer("No pude promover.", show_alert=True)
        await callback.message.reply(
            "❌ No pude promover al usuario. Revisa permisos del bot.\n\n"
            f"Detalle: {exc}"
        )
        return

    await add_log(
        callback.message.chat.id,
        "PROMOTE_ADMIN_PRESET",
        user_id=target_user_id,
        admin_id=callback.from_user.id,
        reason=f"preset={preset_key}"
    )

    try:
        await callback.message.edit_text(
            f"✅ Usuario promovido con perfil {PROMOTE_PRESETS[preset_key]['label']}."
        )
    except Exception:
        pass

    await callback.answer("Permisos aplicados")


@router.callback_query(F.data.startswith("useract:"))
async def user_actions_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    if not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Acción inválida.", show_alert=True)
        return

    action = parts[1]
    try:
        target_user_id = int(parts[2])
    except Exception:
        await callback.answer("Usuario inválido.", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if action == "close":
        try:
            await callback.message.edit_text("✅ Panel cerrado.")
        except Exception:
            pass
        await callback.answer()
        return

    if action == "id":
        warns = await get_warns(chat_id, target_user_id)
        await callback.answer(f"ID: {target_user_id} | warns: {warns}", show_alert=True)
        return

    if action == "profile":
        text = await build_user_profile_text(callback.bot, chat_id, target_user_id)
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=user_actions_keyboard(target_user_id)
            )
        except Exception:
            pass
        await callback.answer("Perfil actualizado")
        return

    if await is_admin(callback.bot, chat_id, target_user_id):
        await callback.answer("No puedo aplicar esto a otro admin.", show_alert=True)
        return

    action_text = None

    try:
        if action == "warn":
            settings = await get_settings(chat_id)
            warns = await add_warn(chat_id, target_user_id)
            await add_log(
                chat_id,
                "WARN_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id,
                reason=f"warns={warns}"
            )
            action_text = f"⚠️ Warn aplicado. Ahora tiene {warns} warn(s)."

            if warns >= settings["warn_limit"]:
                await callback.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=target_user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_until(settings["auto_mute_minutes"])
                )
                await add_log(
                    chat_id,
                    "AUTO_MUTE_BY_WARNS_BUTTON",
                    user_id=target_user_id,
                    admin_id=callback.from_user.id,
                    reason=f"{settings['auto_mute_minutes']} min"
                )
                action_text += f"\n🔇 Auto mute por {settings['auto_mute_minutes']} min."

        elif action == "unwarn":
            warns = await remove_warn(chat_id, target_user_id)
            await add_log(
                chat_id,
                "UNWARN_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id,
                reason=f"warns={warns}"
            )
            action_text = f"➖ Warn removido. Ahora tiene {warns} warn(s)."

        elif action == "mute10":
            await callback.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=mute_until(10)
            )
            await add_log(
                chat_id,
                "MUTE_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id,
                reason="10 min"
            )
            action_text = "🔇 Usuario silenciado por 10 minutos."

        elif action == "mute60":
            await callback.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=mute_until(60)
            )
            await add_log(
                chat_id,
                "MUTE_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id,
                reason="60 min"
            )
            action_text = "🔕 Usuario silenciado por 1 hora."

        elif action == "unmute":
            await callback.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user_id,
                permissions=full_unrestrict_permissions()
            )
            await add_log(
                chat_id,
                "UNMUTE_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id
            )
            action_text = "🔊 Usuario desmuteado."

        elif action == "ban":
            await callback.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
            await add_log(
                chat_id,
                "BAN_BUTTON",
                user_id=target_user_id,
                admin_id=callback.from_user.id
            )
            action_text = "⛔ Usuario baneado."
        else:
            await callback.answer("Acción inválida.", show_alert=True)
            return
    except Exception as exc:
        await callback.answer("No pude aplicar la acción.", show_alert=True)
        try:
            await callback.message.reply(f"❌ Falló la acción rápida.\n\nDetalle: {exc}")
        except Exception:
            pass
        return

    text = await build_user_actions_text(chat_id, target_user_id)
    if action_text:
        text += f"\n\n{action_text}"

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=user_actions_keyboard(target_user_id)
        )
    except Exception:
        pass

    await callback.answer("Acción aplicada")


@router.callback_query(F.data.startswith("panel:"))
async def panel_callbacks(callback: CallbackQuery, state: FSMContext):
    if not await require_admin_callback(callback):
        return

    if not callback.message:
        return

    action = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id
    settings = await get_settings(chat_id)

    if action == "tools":
        locks = sorted(await get_locks(chat_id))
        await callback.message.edit_text(
            "🧰 <b>Bloqueos y permisos</b>\n\n"
            + ("🔒 Activos: " + ", ".join(locks) if locks else "🔓 No hay contenido bloqueado.")
            + "\n\nPulsa un tipo para activarlo o desactivarlo.",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "tools"))
        await callback.answer(); return

    if action.startswith("lock_"):
        kind = action.removeprefix("lock_")
        locks = await get_locks(chat_id)
        await set_lock(chat_id, kind, kind not in locks)
        locks = sorted(await get_locks(chat_id))
        await callback.message.edit_text(
            "🧰 <b>Bloqueos y permisos</b>\n\n"
            + ("🔒 Activos: " + ", ".join(locks) if locks else "🔓 No hay contenido bloqueado."),
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "tools"))
        await callback.answer("Configuración actualizada"); return

    if action == "whitelists":
        domains = await list_whitelist("link_whitelist", chat_id)
        users = await list_whitelist("user_whitelist", chat_id)
        text = ("🔗 <b>Listas blancas</b>\n\n"
                f"Dominios: <b>{len(domains)}</b>\nUsuarios: <b>{len(users)}</b>\n\n"
                "Añade con <code>/whitelistlink dominio.com</code> o respondiendo con <code>/whitelistuser</code>.")
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=panel_keyboard(settings, "tools"))
        await callback.answer(); return

    if action == "export_config":
        payload = await build_group_export(chat_id)
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        await callback.bot.send_document(
            chat_id,
            BufferedInputFile(raw, filename=f"config-grupo-{chat_id}.json"),
            caption="📦 Copia manual de la configuración del grupo.")
        await callback.answer("Copia creada"); return

    if action == "toggle_approval":
        await set_approval_enabled(chat_id, not settings.get("approval_enabled"))
        settings = await get_settings(chat_id)
        await callback.message.edit_text(
            "🛡 <b>Seguridad</b>\n\nLa aprobación manual tiene prioridad sobre el captcha.",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "security"))
        await callback.answer("Aprobación manual actualizada"); return

    if action == "how_poll":
        await callback.message.edit_text(
            "📊 <b>Crear encuesta</b>\n\n"
            "Usa: <code>/encuesta Pregunta | Opción 1 | Opción 2</code>\n"
            "Anónima: <code>/encuestaanonima Pregunta | Sí | No</code>",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "content"))
        await callback.answer(); return

    if action == "close":
        await callback.message.edit_text("✅ Panel cerrado.")
        await callback.answer()
        return

    section_texts = {
        "security": "🛡 <b>Seguridad</b>\n\nActiva o desactiva las protecciones del grupo.",
        "content": "👋 <b>Bienvenida y reglas</b>\n\nConsulta una vista previa o mira cómo cambiar los textos.",
        "sanctions": (
            "🚨 <b>Sanciones</b>\n\n"
            f"⚠️ Límite de warns: <b>{settings['warn_limit']}</b>\n"
            f"🔇 Auto-mute: <b>{settings['auto_mute_minutes']} minutos</b>"
        ),
        "management": "👥 <b>Gestión</b>\n\nRevisa staff, reportes, tickets y el centro administrativo.",
    }
    if action in section_texts:
        await callback.message.edit_text(
            section_texts[action], parse_mode="HTML",
            reply_markup=panel_keyboard(settings, action)
        )
        await callback.answer()
        return

    if action == "preview_welcome":
        preview = settings["welcome_text"].replace("{name}", callback.from_user.full_name)
        await callback.message.edit_text(
            f"👁 <b>Vista previa de bienvenida</b>\n\n{escape(preview)}",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "content")
        )
        await callback.answer()
        return
    if action == "preview_rules":
        await callback.message.edit_text(
            f"👁 <b>Reglas actuales</b>\n\n{escape(settings['rules_text'])}",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "content")
        )
        await callback.answer()
        return
    if action == "how_welcome":
        await state.set_state(PanelEdit.welcome)
        await state.update_data(chat_id=chat_id)
        await callback.message.edit_text(
            "✏️ <b>Cambiar bienvenida</b>\n\nEnvía ahora el nuevo texto. Puedes usar <code>{name}</code>.\n\nEscribe /cancelar para salir.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    if action == "how_rules":
        await state.set_state(PanelEdit.rules)
        await state.update_data(chat_id=chat_id)
        await callback.message.edit_text(
            "✏️ <b>Cambiar reglas</b>\n\nEnvía ahora todas las reglas en un solo mensaje.\n\nEscribe /cancelar para salir.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    if action == "how_farewell":
        await state.set_state(PanelEdit.farewell)
        await state.update_data(chat_id=chat_id)
        await callback.message.edit_text(
            "✏️ <b>Cambiar despedida</b>\n\nEnvía el nuevo texto. Puedes usar <code>{name}</code>.\n\nEscribe /cancelar para salir.",
            parse_mode="HTML"
        )
        await callback.answer()
        return
    if action == "toggle_farewell":
        new_value = not settings["farewell_enabled"]
        await set_farewell(chat_id, enabled=new_value)
        settings = await get_settings(chat_id)
        await callback.message.edit_text(
            "👋 <b>Bienvenida y reglas</b>\n\nDespedida actualizada.",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "content")
        )
        await callback.answer(f"Despedida {'ON' if new_value else 'OFF'}")
        return
    if action == "toggle_progressive":
        new_value = not settings["progressive_sanctions"]
        await set_progressive_sanctions(chat_id, new_value)
        settings = await get_settings(chat_id)
        await callback.message.edit_text(
            "🚨 <b>Sanciones</b>\n\nCon sanciones progresivas: segundo warn = mute de 10 minutos; al límite configurado se aplica el auto-mute.",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "sanctions")
        )
        await callback.answer(f"Sanciones progresivas {'ON' if new_value else 'OFF'}")
        return
    if action == "how_logchannel":
        await callback.message.edit_text(
            "📡 <b>Canal privado de logs</b>\n\n1. Crea un canal privado.\n2. Agrega el bot como administrador.\n3. Obtén su ID y usa en este grupo:\n<code>/setlogchannel -1001234567890</code>\n\nPara desactivar: <code>/setlogchannel off</code>",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "sanctions")
        )
        await callback.answer()
        return
    if action == "how_media":
        await callback.message.edit_text(
            "🖼 <b>Foto o GIF de bienvenida</b>\n\nEnvía una foto o GIF al grupo, respóndelo con <code>/setwelcomemedia</code> y quedará guardado.\n\nVariables disponibles: <code>{name}</code>, <code>{username}</code>, <code>{group}</code>, <code>{members}</code>, <code>{id}</code>.",
            parse_mode="HTML", reply_markup=panel_keyboard(settings, "content")
        )
        await callback.answer()
        return
    if action == "del_media":
        await set_welcome_media(chat_id, None, None)
        settings = await get_settings(chat_id)
        await callback.message.edit_text("✅ Multimedia de bienvenida eliminada.", reply_markup=panel_keyboard(settings, "content"))
        await callback.answer()
        return
    if action in {"how_warns", "how_mutes", "open_logs"}:
        help_text = {
            "how_warns": "⚠️ Responde a un usuario con <code>/warn motivo</code>. Configura el límite con <code>/setwarnlimit 3</code>.",
            "how_mutes": "🔇 Responde con <code>/mute 10m motivo</code>. Configura el auto-mute con <code>/setautomute 60</code>.",
            "open_logs": "📋 Consulta las acciones recientes con <code>/logs</code>.",
        }[action]
        await callback.message.edit_text(help_text, parse_mode="HTML", reply_markup=panel_keyboard(settings, "sanctions"))
        await callback.answer()
        return

    if action == "toggle_antilink":
        new_value = not settings["anti_link"]
        await set_anti_link(chat_id, new_value)
        await add_log(chat_id, "SET_ANTILINK", admin_id=callback.from_user.id, reason=f"anti_link={new_value}")
        await callback.answer(f"Anti-link {'ON' if new_value else 'OFF'}")

    elif action == "toggle_antiflood":
        new_value = not settings["antiflood"]
        await set_antiflood(chat_id, new_value)
        await add_log(chat_id, "SET_ANTIFLOOD", admin_id=callback.from_user.id, reason=f"antiflood={new_value}")
        await callback.answer(f"Antiflood {'ON' if new_value else 'OFF'}")

    elif action == "toggle_captcha":
        new_value = not settings["captcha_enabled"]
        await set_captcha_enabled(chat_id, new_value)
        await add_log(chat_id, "SET_CAPTCHA", admin_id=callback.from_user.id, reason=f"captcha={new_value}")
        await callback.answer(f"Captcha {'ON' if new_value else 'OFF'}")

    elif action == "home":
        await callback.answer("Panel actualizado")

    settings = await get_settings(chat_id)
    bad_words = await get_bad_words(chat_id)

    try:
        await callback.message.edit_text(
            panel_home_text(settings, bad_words) if action == "home" else section_texts["security"],
            parse_mode="HTML",
            reply_markup=panel_keyboard(settings, "home" if action == "home" else "security")
        )
    except Exception:
        pass


@router.message(Command("cancelar"), PanelEdit.welcome)
@router.message(Command("cancelar"), PanelEdit.rules)
@router.message(Command("cancelar"), PanelEdit.farewell)
async def cancel_panel_edit(message: Message, state: FSMContext):
    await state.clear()
    await message.reply("✅ Edición cancelada. Abre /menu cuando quieras continuar.")


@router.message(PanelEdit.welcome, F.text)
async def save_panel_welcome(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id or not await require_admin(message, message.bot):
        return
    text = message.text.strip()
    if not 1 <= len(text) <= 1000:
        await message.reply("El texto debe tener entre 1 y 1000 caracteres.")
        return
    await set_welcome_text(data["chat_id"], text)
    await state.clear()
    await message.reply("✅ Bienvenida guardada para este grupo. Usa /menu para verla.")


@router.message(PanelEdit.rules, F.text)
async def save_panel_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id or not await require_admin(message, message.bot):
        return
    text = message.text.strip()
    if not 1 <= len(text) <= 3500:
        await message.reply("Las reglas deben tener entre 1 y 3500 caracteres.")
        return
    await set_rules_text(data["chat_id"], text)
    await state.clear()
    await message.reply("✅ Reglas guardadas. Los miembros pueden consultarlas con /rules.")


@router.message(PanelEdit.farewell, F.text)
async def save_panel_farewell(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("chat_id") != message.chat.id or not await require_admin(message, message.bot):
        return
    text = message.text.strip()
    if not 1 <= len(text) <= 1000:
        await message.reply("El texto debe tener entre 1 y 1000 caracteres.")
        return
    await set_farewell(data["chat_id"], text=text, enabled=True)
    await state.clear()
    await message.reply("✅ Despedida guardada y activada para este grupo.")


@router.callback_query(F.data.startswith("center:"))
async def center_callbacks(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    if not callback.message:
        return

    action = callback.data.split(":", 1)[1]

    if action == "home":
        text = "🎛 <b>Centro de Control</b>\n\nElige una sección rápida del bot."
        markup = control_center_keyboard()
    elif action == "staff":
        text = await build_staff_text(callback.bot, callback.message.chat.id)
        markup = center_back_keyboard()
    elif action == "admins":
        text = await build_admins_text(callback.bot, callback.message.chat.id)
        markup = center_back_keyboard()
    elif action == "reports":
        text, markup = await build_reports_text(callback.message.chat.id)
    elif action == "tickets":
        text, markup = await build_tickets_text(callback.message.chat.id)
    elif action == "settings":
        text = await build_settings_text(callback.message.chat.id)
        markup = center_back_keyboard()
    elif action == "shortcuts":
        text = build_shortcuts_text()
        markup = center_back_keyboard()
    else:
        await callback.answer("Sección inválida.", show_alert=True)
        return

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("centerclose:"))
async def center_close_callbacks(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    if not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Acción inválida.", show_alert=True)
        return

    kind = parts[1]
    item_id = parse_int(parts[2], minimum=1)
    if item_id is None:
        await callback.answer("ID inválido.", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if kind == "report":
        closed = await close_report(chat_id, item_id, callback.from_user.id)
        if not closed:
            await callback.answer("Ese reporte ya no está abierto.", show_alert=True)
            return

        await add_log(
            chat_id,
            "REPORT_CLOSED_BUTTON",
            admin_id=callback.from_user.id,
            reason=f"report_id={item_id}"
        )
        text, markup = await build_reports_text(chat_id)
        notice = f"✅ Reporte #{item_id} cerrado."
    elif kind == "ticket":
        closed = await close_ticket(chat_id, item_id, callback.from_user.id)
        if not closed:
            await callback.answer("Ese ticket ya no está abierto.", show_alert=True)
            return

        await add_log(
            chat_id,
            "TICKET_CLOSED_BUTTON",
            admin_id=callback.from_user.id,
            reason=f"ticket_id={item_id}"
        )
        text, markup = await build_tickets_text(chat_id)
        notice = f"✅ Ticket #{item_id} cerrado."
    else:
        await callback.answer("Acción inválida.", show_alert=True)
        return

    text += f"\n\n{notice}"

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        pass

    await callback.answer("Cerrado")


@router.message(Command("antilink"))
async def cmd_antilink(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args or command.args.lower() not in ("on", "off"):
        await message.reply("Uso: /antilink on o /antilink off")
        return

    enabled = command.args.lower() == "on"
    await set_anti_link(message.chat.id, enabled)
    await add_log(message.chat.id, "SET_ANTILINK", admin_id=message.from_user.id, reason=f"anti_link={enabled}")
    await message.reply(f"✅ Anti-link {'activado' if enabled else 'desactivado'}.")


@router.message(Command("antiflood"))
async def cmd_antiflood(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args or command.args.lower() not in ("on", "off"):
        await message.reply("Uso: /antiflood on o /antiflood off")
        return

    enabled = command.args.lower() == "on"
    await set_antiflood(message.chat.id, enabled)
    await add_log(message.chat.id, "SET_ANTIFLOOD", admin_id=message.from_user.id, reason=f"antiflood={enabled}")
    await message.reply(f"✅ Antiflood {'activado' if enabled else 'desactivado'}.")


@router.message(Command("captcha"))
async def cmd_captcha(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args or command.args.lower() not in ("on", "off"):
        await message.reply("Uso: /captcha on o /captcha off")
        return

    enabled = command.args.lower() == "on"
    await set_captcha_enabled(message.chat.id, enabled)
    await add_log(message.chat.id, "SET_CAPTCHA", admin_id=message.from_user.id, reason=f"captcha={enabled}")
    await message.reply(f"✅ Captcha {'activado' if enabled else 'desactivado'}.")


@router.message(Command("setwarnlimit"))
async def cmd_setwarnlimit(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /setwarnlimit 3")
        return

    value = parse_int(command.args, minimum=1, maximum=20)
    if value is None:
        await message.reply("❌ Número inválido. Usa un valor entre 1 y 20.")
        return

    await set_warn_limit(message.chat.id, value)
    await add_log(message.chat.id, "SET_WARN_LIMIT", admin_id=message.from_user.id, reason=f"warn_limit={value}")
    await message.reply(f"✅ Nuevo límite de warns: {value}")


@router.message(Command("setautomute"))
async def cmd_setautomute(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /setautomute 60")
        return

    value = parse_int(command.args, minimum=1, maximum=10080)
    if value is None:
        await message.reply("❌ Número inválido. Usa minutos entre 1 y 10080.")
        return

    await set_auto_mute_minutes(message.chat.id, value)
    await add_log(message.chat.id, "SET_AUTO_MUTE", admin_id=message.from_user.id, reason=f"minutes={value}")
    await message.reply(f"✅ Auto mute configurado en {value} minutos.")


@router.message(Command("setflood"))
async def cmd_setflood(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /setflood 5 10")
        return

    parts = command.args.split()
    if len(parts) != 2:
        await message.reply("Uso: /setflood 5 10")
        return

    max_messages = parse_int(parts[0], minimum=2, maximum=50)
    window_seconds = parse_int(parts[1], minimum=2, maximum=120)

    if max_messages is None or window_seconds is None:
        await message.reply("❌ Valores inválidos. Ejemplo válido: /setflood 5 10")
        return

    await set_flood_limit(message.chat.id, max_messages, window_seconds)
    await add_log(
        message.chat.id,
        "SET_FLOOD_LIMIT",
        admin_id=message.from_user.id,
        reason=f"{max_messages} mensajes / {window_seconds} seg"
    )
    await message.reply(f"✅ Flood configurado: {max_messages} mensajes en {window_seconds} segundos.")


@router.message(Command("setwelcome"))
async def cmd_setwelcome(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /setwelcome Bienvenido {name}")
        return

    await set_welcome_text(message.chat.id, command.args.strip())
    await add_log(message.chat.id, "SET_WELCOME", admin_id=message.from_user.id)
    await message.reply("✅ Mensaje de bienvenida actualizado.")


@router.message(Command("setrules"))
async def cmd_setrules(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /setrules Regla 1... Regla 2...")
        return

    await set_rules_text(message.chat.id, command.args.strip())
    await add_log(message.chat.id, "SET_RULES", admin_id=message.from_user.id)
    await message.reply("✅ Reglas actualizadas.")


@router.message(Command("addbadword"))
async def cmd_addbadword(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /addbadword palabra")
        return

    word = command.args.strip().lower()
    inserted = await add_bad_word(message.chat.id, word)
    if not inserted:
        await message.reply(f"ℹ️ La palabra `{word}` ya estaba bloqueada.", parse_mode="Markdown")
        return

    await add_log(message.chat.id, "ADD_BAD_WORD", admin_id=message.from_user.id, reason=word)
    await message.reply(f"✅ Palabra bloqueada agregada: {word}")


@router.message(Command("delbadword"))
async def cmd_delbadword(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    if not command.args:
        await message.reply("Uso: /delbadword palabra")
        return

    word = command.args.strip().lower()
    await del_bad_word(message.chat.id, word)
    await add_log(message.chat.id, "DEL_BAD_WORD", admin_id=message.from_user.id, reason=word)
    await message.reply(f"✅ Palabra bloqueada eliminada: {word}")


@router.message(Command("badwords"))
async def cmd_badwords(message: Message):
    if not await require_admin(message, message.bot):
        return

    words = await get_bad_words(message.chat.id)
    if not words:
        await message.reply("🧹 No hay palabras bloqueadas en este grupo.")
        return

    await message.reply("🧹 Palabras bloqueadas:\n\n" + "\n".join(f"• {word}" for word in words))


@router.message(Command("promote"))
async def cmd_promote(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    if not user:
        await message.reply("Responde al usuario que quieres volver admin. Opcional: /promote Apodo")
        return

    if await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("Ese usuario ya es administrador.")
        return

    nickname = normalize_staff_nickname(command.args)

    try:
        await promote_user_with_preset(message, user.id, "mod")
    except Exception as exc:
        await message.reply(f"❌ No pude promoverlo. Revisa que el bot tenga permiso para agregar admins.\n\nDetalle: {exc}")
        return

    await register_staff_member(message.chat.id, user.id, nickname)

    title_applied = False
    if nickname:
        title_applied = await set_admin_custom_title_safe(message, user.id, nickname)

    await add_log(
        message.chat.id,
        "PROMOTE_ADMIN",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=f"nickname={nickname}" if nickname else None
    )

    text = f"✅ {user.full_name} ahora es parte del staff."
    if nickname:
        text += f"\n🏷 Apodo guardado: {nickname}"
        if not title_applied:
            text += "\nℹ️ Guardé el apodo internamente, pero Telegram no permitió aplicarlo como título visible."
    await message.reply(text)


@router.message(Command("demote"))
@router.message(Command("staffdel"))
async def cmd_demote(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    target_user_id, target_name = await resolve_target_user_id(message, command.args)
    if not target_user_id:
        await message.reply("Uso: responde al admin con /demote o usa /demote 123456789")
        return

    if message.from_user and target_user_id == message.from_user.id:
        await message.reply("No te voy a quitar admin a ti mismo desde aquí.")
        return

    try:
        await message.bot.promote_chat_member(
            chat_id=message.chat.id,
            user_id=target_user_id,
            can_change_info=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_restrict_members=False,
            can_pin_messages=False,
            can_promote_members=False,
            can_manage_video_chats=False,
            can_post_stories=False,
            can_edit_stories=False,
            can_delete_stories=False,
            can_manage_topics=False,
            is_anonymous=False,
        )
    except Exception as exc:
        await message.reply(f"❌ No pude quitarle admin. Revisa que el bot tenga permiso para administrar admins.\n\nDetalle: {exc}")
        return

    await remove_staff_nickname(message.chat.id, target_user_id)
    await add_log(
        message.chat.id,
        "DEMOTE_ADMIN",
        user_id=target_user_id,
        admin_id=message.from_user.id
    )
    await message.reply(f"✅ Admin removido: {target_name}")


@router.message(Command("staffnick"))
async def cmd_staffnick(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    if not user:
        await message.reply("Responde al admin al que quieres ponerle apodo. Ejemplo: /staffnick Soporte")
        return

    if not await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("Ese usuario todavía no es administrador.")
        return

    nickname = normalize_staff_nickname(command.args)
    if not nickname:
        await message.reply("Uso: /staffnick Apodo")
        return

    await set_staff_nickname(message.chat.id, user.id, nickname)
    title_applied = await set_admin_custom_title_safe(message, user.id, nickname)

    await add_log(
        message.chat.id,
        "SET_STAFF_NICK",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=nickname
    )

    text = f"✅ Apodo actualizado para {user.full_name}: {nickname}"
    if not title_applied:
        text += "\nℹ️ El apodo quedó guardado en el bot, pero Telegram no dejó aplicarlo como título visible."
    await message.reply(text)


@router.message(Command("unstaffnick"))
async def cmd_unstaffnick(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    target_user_id, target_name = await resolve_target_user_id(message, command.args)
    if not target_user_id:
        await message.reply("Uso: responde al admin con /unstaffnick o usa /unstaffnick 123456789")
        return

    await remove_staff_nickname(message.chat.id, target_user_id)
    await set_admin_custom_title_safe(message, target_user_id, None)

    await add_log(
        message.chat.id,
        "REMOVE_STAFF_NICK",
        user_id=target_user_id,
        admin_id=message.from_user.id
    )
    await message.reply(f"✅ Apodo removido para {target_name}")


@router.message(Command("staffrole"))
async def cmd_staffrole(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    if not user:
        await message.reply("Responde al admin al que quieres ponerle rango. Ejemplo: /staffrole Moderador")
        return

    if not await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("Ese usuario todavía no es administrador.")
        return

    role_name = normalize_staff_role(command.args)
    if not role_name:
        await message.reply("Uso: /staffrole Moderador")
        return

    await set_staff_role(message.chat.id, user.id, role_name)
    await add_log(
        message.chat.id,
        "SET_STAFF_ROLE",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=role_name
    )
    await message.reply(f"✅ Rango actualizado para {user.full_name}: {role_name}")


@router.message(Command("unstaffrole"))
async def cmd_unstaffrole(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    target_user_id, target_name = await resolve_target_user_id(message, command.args)
    if not target_user_id:
        await message.reply("Uso: responde al admin con /unstaffrole o usa /unstaffrole 123456789")
        return

    await remove_staff_role(message.chat.id, target_user_id)
    await add_log(
        message.chat.id,
        "REMOVE_STAFF_ROLE",
        user_id=target_user_id,
        admin_id=message.from_user.id
    )
    await message.reply(f"✅ Rango removido para {target_name}")


@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user, reason_args = await moderation_target(message, command.args)
    if not user:
        await message.reply("Usa /warn ID motivo, /warn @usuario motivo o responde con /warn motivo.")
        return

    if await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("⛔ No puedo advertir a otro administrador.")
        return

    if not reason_args:
        builder = InlineKeyboardBuilder()
        for label, reason_key in (("📢 Spam", "spam"), ("🤬 Insultos", "insultos"),
                                  ("🔗 Enlaces", "enlaces"), ("⚠️ Conducta", "conducta")):
            builder.button(text=label, callback_data=f"warnreason:{user.id}:{reason_key}")
        builder.adjust(2)
        await message.reply(f"⚠️ Elige el motivo del warn para {user.full_name}:", reply_markup=builder.as_markup())
        return

    settings = await get_settings(message.chat.id)
    warns = await add_warn(message.chat.id, user.id)
    reason = reason_args.strip()

    await add_log(
        message.chat.id,
        "WARN",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=f"warns={warns}" + (f" | motivo={reason}" if reason else "")
    )
    await send_admin_log(message.bot, message.chat.id, "WARN", user.id, message.from_user.id,
                         f"warns={warns}" + (f" | {reason}" if reason else ""))

    if settings.get("progressive_sanctions") and warns == 2 and warns < settings["warn_limit"]:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id, user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False), until_date=mute_until(10)
        )
        await add_log(message.chat.id, "PROGRESSIVE_MUTE", user_id=user.id,
                      admin_id=message.from_user.id, reason="10 min")
        await send_admin_log(message.bot, message.chat.id, "PROGRESSIVE_MUTE", user.id,
                             message.from_user.id, "10 minutos")
        await message.reply(f"📈 {user.full_name} recibió su segundo warn y fue silenciado 10 minutos.")
        return

    if warns >= settings["warn_limit"]:
        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until(settings["auto_mute_minutes"])
        )

        await add_log(
            message.chat.id,
            "AUTO_MUTE_BY_WARNS",
            user_id=user.id,
            admin_id=message.from_user.id,
            reason=f"{settings['auto_mute_minutes']} min"
        )

        await message.reply(
            f"🚨 {user.full_name} ahora tiene {warns} warn(s) y fue silenciado automáticamente "
            f"por {settings['auto_mute_minutes']} minutos."
            + (f"\n📝 Motivo: {reason}" if reason else "")
        )
        return

    await message.reply(
        f"⚠️ {user.full_name} ahora tiene {warns} warn(s)."
        + (f"\n📝 Motivo: {reason}" if reason else "Sin motivo especificado."),
        reply_markup=_moderation_result_keyboard(user.id, "warn"),
    )


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user, _ = await moderation_target(message, command.args)
    if not user:
        await message.reply("Usa /unwarn ID, /unwarn @usuario o responde a su mensaje.")
        return

    warns = await remove_warn(message.chat.id, user.id)
    await add_log(
        message.chat.id,
        "UNWARN",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=f"warns={warns}"
    )
    await message.reply(f"✅ {user.full_name} ahora tiene {warns} warn(s).")


@router.message(Command("warns"))
async def cmd_warns(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user, _ = await moderation_target(message, command.args)
    if not user:
        await message.reply("Usa /warns ID, /warns @usuario o responde a su mensaje.")
        return

    warns = await get_warns(message.chat.id, user.id)
    await message.reply(f"📌 {user.full_name} tiene {warns} warn(s).")


@router.message(Command("clearwarns"))
async def cmd_clearwarns(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user, _ = await moderation_target(message, command.args)
    if not user:
        await message.reply("Usa /clearwarns ID, /clearwarns @usuario o responde a su mensaje.")
        return

    await reset_warns(message.chat.id, user.id)
    await add_log(message.chat.id, "CLEAR_WARNS", user_id=user.id, admin_id=message.from_user.id)
    await message.reply(f"✅ Warns reiniciados para {user.full_name}.")


@router.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user, remaining = await moderation_target(message, command.args)
    if not user:
        await message.reply("Usa /mute ID 10m motivo, /mute @usuario 10m motivo o responde con /mute 10m motivo.")
        return

    if await is_admin(message.bot, message.chat.id, user.id):
        await message.reply("⛔ No puedo silenciar a otro administrador.")
        return

    duration_raw, reason = split_once_args(remaining)

    if not duration_raw:
        await message.reply("Uso: /mute 10m o /mute 1h o /mute 1d")
        return

    minutes = parse_duration_to_minutes(duration_raw)
    if minutes is None or minutes < 1 or minutes > 525600:
        await message.reply("❌ Formato inválido. Usa por ejemplo: /mute 10m")
        return

    await message.bot.restrict_chat_member(
        chat_id=message.chat.id,
        user_id=user.id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=mute_until(minutes)
    )

    await add_log(
        message.chat.id,
        "MUTE",
        user_id=user.id,
        admin_id=message.from_user.id,
        reason=f"{minutes} min" + (f" | motivo={reason}" if reason else "")
    )

    await message.reply(
        f"🔇 {user.full_name} fue silenciado por {duration_raw}."
        + (f"\n📝 Motivo: {reason}" if reason else "")
    )


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    target_user_id, target_name = await resolve_target_user_id(message, command.args)

    if not target_user_id:
        await message.reply("Uso: responde al usuario con /unmute o usa /unmute 123456789")
        return

    await message.bot.restrict_chat_member(
        chat_id=message.chat.id,
        user_id=target_user_id,
        permissions=full_unrestrict_permissions()
    )

    await add_log(
        message.chat.id,
        "UNMUTE",
        user_id=target_user_id,
        admin_id=message.from_user.id
    )

    await message.reply(f"🔊 Usuario desmuteado: {target_name}")


@router.message(Command("bang"))
async def cmd_ban(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user = get_target_user(message)
    parts = (command.args or "").split(maxsplit=1)
    user_id = user.id if user else (int(parts[0]) if parts and parts[0].isdigit() else None)
    target_name = user.full_name if user else str(user_id)
    if not user_id and parts and parts[0].startswith("@"):
        from app.services.user_directory import resolve_username
        user_id = await resolve_username(message.bot, message.chat.id, parts[0])
        target_name = parts[0]
    if not user_id:
        await message.reply("Uso: /bang 123456789 motivo, /bang @usuario motivo o responde con /bang. Si no conozco ese @usuario, utiliza su ID.")
        return

    if await is_admin(message.bot, message.chat.id, user_id):
        await message.reply("⛔ No puedo banear a otro administrador.")
        return

    reason = (command.args or "").strip() if user else (parts[1].strip() if len(parts) > 1 else "")
    if not reason:
        builder = InlineKeyboardBuilder()
        for label, reason_key in (("🤖 Bot/Spam", "spam"), ("💰 Estafa", "estafa"),
                                  ("🤬 Acoso", "acoso"), ("🔞 Contenido", "contenido")):
            builder.button(text=label, callback_data=f"banreason:{user_id}:{reason_key}")
        builder.adjust(2)
        await message.reply(f"⛔ Elige el motivo del ban para {target_name}:", reply_markup=builder.as_markup())
        return

    await message.bot.ban_chat_member(message.chat.id, user_id)
    await add_log(
        message.chat.id,
        "BAN",
        user_id=user_id,
        admin_id=message.from_user.id,
        reason=reason
    )
    await message.reply(
        f"⛔ {target_name} fue baneado."
        + (f"\n📝 Motivo: {reason}" if reason else "Sin motivo especificado."),
        reply_markup=_moderation_result_keyboard(user_id, "ban"),
    )


@router.message(Command("unbang"))
async def cmd_unban(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    user_id, _ = await resolve_target_user_id(message, command.args)
    if not user_id:
        await message.reply("Responde a un mensaje anterior del usuario con /unbang o usa /unbang 123456789")
        return

    await message.bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
    await add_log(message.chat.id, "UNBAN", user_id=user_id, admin_id=message.from_user.id)
    await message.reply(f"✅ Usuario desbaneado: {user_id}")


def _moderation_result_keyboard(user_id: int, action: str):
    builder = InlineKeyboardBuilder()
    if action == "warn":
        builder.button(text="➖ Quitar warn", callback_data=f"modresult:unwarn:{user_id}")
        builder.button(text="📄 Ver perfil", callback_data=f"useract:profile:{user_id}")
    else:
        builder.button(text="🔓 Desbanear", callback_data=f"modresult:unban:{user_id}")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data.startswith("warnreason:"))
async def warn_reason_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return
    _, user_id_text, reason = callback.data.split(":", 2)
    user_id = int(user_id_text)
    if await is_admin(callback.bot, callback.message.chat.id, user_id):
        await callback.answer("No puedo advertir a un administrador.", show_alert=True)
        return
    warns = await add_warn(callback.message.chat.id, user_id)
    settings = await get_settings(callback.message.chat.id)
    await add_log(callback.message.chat.id, "WARN_BUTTON", user_id=user_id,
                  admin_id=callback.from_user.id, reason=reason)
    if warns >= settings["warn_limit"]:
        await callback.bot.restrict_chat_member(
            callback.message.chat.id, user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=mute_until(settings["auto_mute_minutes"]),
        )
    await callback.message.edit_text(
        f"⚠️ Warn aplicado\n\nUsuario: <code>{user_id}</code>\nMotivo: <b>{reason}</b>\nTotal: <b>{warns}</b>",
        parse_mode="HTML", reply_markup=_moderation_result_keyboard(user_id, "warn"),
    )
    await callback.answer("Warn aplicado")


@router.callback_query(F.data.startswith("banreason:"))
async def ban_reason_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return
    _, user_id_text, reason = callback.data.split(":", 2)
    user_id = int(user_id_text)
    if await is_admin(callback.bot, callback.message.chat.id, user_id):
        await callback.answer("No puedo banear a un administrador.", show_alert=True)
        return
    await callback.bot.ban_chat_member(callback.message.chat.id, user_id)
    await add_log(callback.message.chat.id, "BAN_BUTTON", user_id=user_id,
                  admin_id=callback.from_user.id, reason=reason)
    await callback.message.edit_text(
        f"⛔ Usuario baneado\n\nID: <code>{user_id}</code>\nMotivo: <b>{reason}</b>",
        parse_mode="HTML", reply_markup=_moderation_result_keyboard(user_id, "ban"),
    )
    await callback.answer("Usuario baneado")


@router.callback_query(F.data.startswith("modresult:"))
async def moderation_result_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return
    _, action, user_id_text = callback.data.split(":", 2)
    user_id = int(user_id_text)
    if action == "unwarn":
        warns = await remove_warn(callback.message.chat.id, user_id)
        await add_log(callback.message.chat.id, "UNWARN_BUTTON", user_id=user_id, admin_id=callback.from_user.id)
        await callback.answer(f"Warn retirado. Ahora tiene {warns}.", show_alert=True)
    elif action == "unban":
        await callback.bot.unban_chat_member(callback.message.chat.id, user_id, only_if_banned=True)
        await add_log(callback.message.chat.id, "UNBAN_BUTTON", user_id=user_id, admin_id=callback.from_user.id)
        await callback.answer("Usuario desbaneado.", show_alert=True)


@router.message(Command("purge", "limpiar"))
async def purge_messages(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return
    if message.reply_to_message:
        start_id = message.reply_to_message.message_id
        count = message.message_id - start_id + 1
    else:
        count = parse_int(command.args or "", minimum=1, maximum=100)
        if count is None:
            await message.reply("Responde al primer mensaje con <code>/purge</code> o usa <code>/limpiar 20</code>.", parse_mode="HTML")
            return
        start_id = max(1, message.message_id - count + 1)
    if count > 100:
        await message.reply("❌ Telegram permite borrar hasta 100 mensajes por operación.")
        return
    ids = list(range(start_id, message.message_id + 1))
    try:
        await message.bot.delete_messages(message.chat.id, ids)
        await add_log(message.chat.id, "PURGE", admin_id=message.from_user.id, reason=f"{len(ids)} mensajes")
    except Exception:
        await message.reply("❌ No pude borrar todos los mensajes. Revisa que tenga permiso para eliminar.")


@router.message(Command("logs"))
async def cmd_logs(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    limit = 10
    if command.args:
        maybe_limit = parse_int(command.args, minimum=1, maximum=30)
        if maybe_limit is None:
            await message.reply("Uso: /logs o /logs 10")
            return
        limit = maybe_limit

    logs = await get_logs(message.chat.id, limit=limit)
    if not logs:
        await message.reply("📝 No hay logs todavía.")
        return

    lines = []
    for row in logs:
        user_id, admin_id, action, reason, created_at = row
        line = f"• [{created_at}] {action}"
        if user_id:
            line += f" | user: {user_id}"
        if admin_id:
            line += f" | admin: {admin_id}"
        if reason:
            line += f" | {reason}"
        lines.append(line)

    await message.reply("🧾 Últimos logs:\n\n" + "\n".join(lines))


@router.message(Command("reports"))
async def cmd_reports(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    limit = 10
    if command.args:
        maybe_limit = parse_int(command.args, minimum=1, maximum=30)
        if maybe_limit is None:
            await message.reply("Uso: /reports o /reports 10")
            return
        limit = maybe_limit

    reports = await get_open_reports(message.chat.id, limit=limit)
    if not reports:
        await message.reply("🚩 No hay reportes abiertos.")
        return

    lines = []
    for report_id, reporter_id, target_user_id, target_message_text, reason, created_at in reports:
        line = (
            f"• #{report_id} [{created_at}] reportero: {reporter_id} | "
            f"usuario: {target_user_id}"
        )
        if reason:
            line += f" | motivo: {reason}"
        if target_message_text:
            sanitized = " ".join(target_message_text.split())
            line += f" | msg: {sanitized[:80]}"
        lines.append(line)

    await message.reply(
        "🚩 Reportes abiertos:\n\n" + "\n".join(lines) + "\n\nUsa /closereport ID para cerrarlo."
    )


@router.message(Command("closereport"))
async def cmd_closereport(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    report_id = parse_int(command.args or "", minimum=1)
    if report_id is None:
        await message.reply("Uso: /closereport 12")
        return

    closed = await close_report(message.chat.id, report_id, message.from_user.id)
    if not closed:
        await message.reply("No encontré un reporte abierto con ese ID.")
        return

    await add_log(
        message.chat.id,
        "REPORT_CLOSED",
        admin_id=message.from_user.id,
        reason=f"report_id={report_id}"
    )
    await message.reply(f"✅ Reporte #{report_id} cerrado.")


@router.message(Command("tickets"))
async def cmd_tickets(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    limit = 10
    if command.args:
        maybe_limit = parse_int(command.args, minimum=1, maximum=30)
        if maybe_limit is None:
            await message.reply("Uso: /tickets o /tickets 10")
            return
        limit = maybe_limit

    tickets = await get_open_tickets(message.chat.id, limit=limit)
    if not tickets:
        await message.reply("🎫 No hay tickets abiertos.")
        return

    lines = []
    for ticket_id, user_id, reason, created_at in tickets:
        line = f"• #{ticket_id} [{created_at}] usuario: {user_id}"
        if reason:
            line += f" | motivo: {reason[:100]}"
        lines.append(line)

    await message.reply(
        "🎫 Tickets abiertos:\n\n" + "\n".join(lines) + "\n\nUsa /closeticket ID para cerrarlo."
    )


@router.message(Command("closeticket"))
async def cmd_closeticket(message: Message, command: CommandObject):
    if not await require_admin(message, message.bot):
        return

    ticket_id = parse_int(command.args or "", minimum=1)
    if ticket_id is None:
        await message.reply("Uso: /closeticket 15")
        return

    closed = await close_ticket(message.chat.id, ticket_id, message.from_user.id)
    if not closed:
        await message.reply("No encontré un ticket abierto con ese ID.")
        return

    await add_log(
        message.chat.id,
        "TICKET_CLOSED",
        admin_id=message.from_user.id,
        reason=f"ticket_id={ticket_id}"
    )
    await message.reply(f"✅ Ticket #{ticket_id} cerrado.")
