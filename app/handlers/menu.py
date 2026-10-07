from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services.database import get_settings

router = Router()

SECTIONS = {
    "downloads": (
        "📥 <b>Música y videos</b>\n\n"
        "🎵 <code>/play canción</code> — busca, muestra opciones y descarga MP3\n"
        "🎬 <code>/playvideo nombre o enlace</code> — video de YouTube\n"
        "📄 <code>/playdoc nombre o enlace</code> — video como documento\n"
        "🎶 <code>/tiktok enlace</code> — descarga TikTok\n"
        "📸 <code>/instagram enlace</code> — Reel, foto o carrusel\n"
        "📘 <code>/facebook enlace</code> — descarga video\n\n"
        "También puedes enviar directamente un enlace de TikTok, Reel o YouTube Shorts.\n"
        "YouTube permite elegir calidad; TikTok e Instagram usan la mejor disponible."
        "\n📥 <code>/cola</code> — posición y progreso de descargas"
        "\n⭐ <code>/favoritos</code> — música y videos guardados"
        "\n📚 <code>/historial</code> — tus últimas descargas"
        "\n📊 <code>/estadisticasbot</code> — estadísticas generales"
    ),
    "economy": (
        "🎮 <b>Economía y juegos</b>\n\n"
        "👤 <code>/register</code> — registrarte\n"
        "💼 <code>/perfil</code> — soles, XP y nivel\n"
        "🎴 <code>/tarjeta</code> — tarjeta visual de perfil\n"
        "🎁 <code>/daily</code> — premio diario\n"
        "🎯 <code>/misiones</code> — objetivos y recompensas\n"
        "⛏ <code>/minar</code> — conseguir soles\n"
        "🎣 <code>/pescar</code> — conseguir soles\n"
        "🎰 <code>/tragamonedas</code> o <code>/ruleta</code>\n"
        "💸 <code>/transferir cantidad</code> — responde a una persona\n"
        "🛍 <code>/tienda</code> · <code>/comprar objeto</code>\n"
        "🎒 <code>/inventario</code> — ver tus objetos\n"
        "🏆 <code>/ranksoles</code>, <code>/ranknivel</code>, <code>/rankrep</code>"
    ),
    "general": (
        "⭐ <b>Comandos generales</b>\n\n"
        "🏓 <code>/ping</code> — comprobar velocidad\n"
        "🆔 <code>/id</code> — IDs de usuario y chat\n"
        "📜 <code>/rules</code> — reglas del grupo\n"
        "📊 <code>/stats</code> — estadísticas\n"
        "🚩 <code>/report motivo</code> — reportar respondiendo\n"
        "🎫 <code>/ticket motivo</code> — pedir ayuda\n"
        "📬 <code>/miscasos</code> — estado de tus tickets y sugerencias\n"
        "🎤 <code>/letra artista canción</code> — buscar letras\n"
        "🧮 <code>/calcular 2*(5+3)</code> — calculadora"
    ),
    "moderation": (
        "🚨 <b>Moderación</b>\n\n"
        "Responde al mensaje de la persona y usa:\n"
        "⚠️ <code>/warn motivo</code> · <code>/unwarn</code> · <code>/warns</code>\n"
        "🔇 <code>/mute 10m motivo</code> · <code>/unmute</code>\n"
        "⛔ <code>/bang motivo</code> · <code>/unbang ID</code>\n"
        "🎛 <code>/acciones</code> — botones rápidos\n"
        "📋 <code>/logs</code> · <code>/reports</code> · <code>/tickets</code>\n"
        "👤 ID, alias conocido o respuesta: <code>/bang ID motivo</code>, <code>/warn ID motivo</code>, <code>/mute ID 10m motivo</code>\n"
        "🗂 <code>/sanciones ID</code> — historial de este grupo\n"
        "💬 <code>/responderticket ID respuesta</code>"
    ),
    "settings": (
        "⚙️ <b>Configuración del grupo</b>\n\n"
        "Usa los botones inferiores para abrir el panel y el centro administrativo.\n"
        "🔗 <code>/antilink on|off</code>\n"
        "⚡ <code>/antiflood on|off</code>\n"
        "🛡 <code>/captcha on|off</code>\n"
        "👋 <code>/setwelcome texto {name}</code>\n"
        "🖼 <code>/setwelcomemedia</code> — responde a una foto/GIF\n"
        "📜 <code>/setrules texto</code>\n"
        "🧹 <code>/addbadword palabra</code> · <code>/delbadword palabra</code>\n"
        "📡 <code>/setlogchannel ID</code> — canal privado de registros\n"
        "📢 <code>/canalobligatorio @canal</code>\n"
        "📊 <code>/statssemanales on|off</code>\n"
        "📦 <code>/exportarconfig</code> · <code>/importarconfig</code>\n"
        "🧹 <code>/autolimpieza 15</code> — borrar mensajes de comandos\n"
        "🌐 <code>/idioma es|en</code> — idioma del menú\n"
        "Solo administradores. Cada grupo guarda su configuración por separado."
    ),
    "staff": (
        "🛡 <b>Staff y administración</b>\n\n"
        "👥 <code>/staff</code> · <code>/admins</code>\n"
        "⬆️ <code>/promotebtn</code> — promover con botones\n"
        "⬇️ <code>/demote</code> — quitar admin respondiendo\n"
        "🏷 <code>/staffnick Apodo</code>\n"
        "🎖 <code>/staffrole Rango</code>\n"
        "👤 <code>/infouser</code> — perfil de moderación"
    ),
    "grouptools": (
        "🧰 <b>Herramientas avanzadas del grupo</b>\n\n"
        "🗒 <code>/save nombre texto</code> · <code>/get nombre</code> · <code>/notes</code>\n"
        "⚡ <code>/setcmd nombre respuesta</code> · <code>/cmds</code>\n"
        "📌 <code>/pin</code> · <code>/unpin</code> · <code>/unpinall</code>\n"
        "🐢 <code>/slowmode 10</code> — 0 para apagar\n"
        "🔒 <code>/bloquear fotos</code> · <code>/desbloquear fotos</code> · <code>/bloqueos</code>\n"
        "🔗 <code>/whitelistlink youtube.com</code> · <code>/whitelistlinks</code>\n"
        "👤 <code>/whitelistuser ID</code> · <code>/whitelistusers</code>\n\n"
        "🎉 <code>/sorteo 10m Premio</code> · <code>/finalizarsorteo ID</code>\n"
        "📊 <code>/actividad</code> · <code>/rankactividad</code>\n"
        "⭐ <code>/perfil</code> · <code>/setrolnivel 5 Experto</code>\n"
        "🗓 <code>/programar 30m Mensaje</code> · <code>/programados</code>\n"
        "📊 <code>/encuesta Pregunta | Sí | No</code>\n"
        "📋 <code>/copiarconfig ID_ORIGEN</code> — usar en el grupo destino\n\n"
        "Cada grupo conserva su propia configuración. Los cambios son solo para administradores."
    ),
    "guide": (
        "📖 <b>Guía rápida para administradores</b>\n\n"
        "1️⃣ Agrega el bot como administrador y desactiva la privacidad en BotFather.\n"
        "2️⃣ Abre <code>/menu</code> y entra a Configuración para administrar el grupo.\n"
        "3️⃣ Configura los registros con <code>/setlogchannel ID</code>.\n"
        "4️⃣ Para moderar, responde al mensaje y usa <code>/acciones</code>.\n"
        "5️⃣ Revisa pendientes con el botón Centro administrativo dentro de <code>/menu</code>.\n\n"
        "🔐 <b>Herramientas privadas del dueño</b>\n"
        "• <code>/backup</code> — copia inmediata\n"
        "• <code>/estado</code> — salud, memoria, disco y grupos\n"
        "• <code>/exportargrupo ID</code> — exportar configuración\n"
        "• <code>/descargaslibres ID</code> — quitar límite temporal\n"
        "• <code>/quitarlibre ID</code> — retirar acceso libre\n"
        "• <code>/usuarioslibres</code> — consultar autorizados\n"
        "• <code>/paneldescargas</code> — límites y usuarios libres\n"
        "• Responde a una copia .db con <code>/restaurar</code>\n"
        "• <code>/cancelar</code> — cancelar cualquier operación"
    ),
}

EN_SECTIONS = {
    "downloads": "📥 <b>Music and videos</b>\n\n<code>/play song</code> · <code>/playvideo search</code> · <code>/playdoc search</code>\n<code>/tiktok link</code> · <code>/instagram link</code> · <code>/facebook link</code>\n<code>/cola</code> queue · <code>/historial</code> history · <code>/favoritos</code> favorites",
    "economy": "🎮 <b>Economy and games</b>\n\n<code>/register</code> register · <code>/perfil</code> wallet · <code>/daily</code> reward\n<code>/minar</code> mine · <code>/pescar</code> fish · <code>/ruleta</code> roulette\n<code>/transferir</code> transfer · <code>/tienda</code> shop · <code>/inventario</code> inventory",
    "general": "⭐ <b>General commands</b>\n\n<code>/ping</code> · <code>/id</code> · <code>/rules</code> · <code>/stats</code>\n<code>/report</code> · <code>/ticket</code> · <code>/letra artist song</code> · <code>/calcular expression</code>",
    "moderation": "🚨 <b>Moderation</b>\n\nReply to a user: <code>/warn reason</code> · <code>/mute 10m</code> · <code>/bang reason</code>\n<code>/unwarn</code> · <code>/unmute</code> · <code>/unbang ID</code> · <code>/acciones</code>\nUse the administrative buttons below for the full control center.",
    "settings": "⚙️ <b>Group settings</b>\n\nUse the administrative buttons below.\n<code>/antilink on|off</code> · <code>/antiflood on|off</code> · <code>/captcha on|off</code>\n<code>/setwelcome text</code> · <code>/setrules text</code> · <code>/setlogchannel ID</code>\n<code>/canalobligatorio @channel</code> · <code>/autolimpieza 15</code> · <code>/idioma es|en</code>",
    "staff": "🛡 <b>Staff</b>\n\n<code>/staff</code> · <code>/admins</code> · <code>/promotebtn</code> · <code>/demote</code>\n<code>/staffnick Name</code> · <code>/staffrole Role</code> · <code>/infouser</code>",
    "grouptools": "🧰 <b>Advanced group tools</b>\n\nNotes: <code>/save</code> · <code>/get</code> · <code>/notes</code>\nCustom commands: <code>/setcmd</code> · <code>/cmds</code>\nGiveaways: <code>/sorteo 10m Prize</code> · Levels: <code>/perfil</code>\nSchedules: <code>/programar 30m Message</code> · Polls: <code>/encuesta Question | Yes | No</code>\nConfiguration: <code>/exportarconfig</code> · <code>/importarconfig</code>",
    "guide": "📖 <b>Administrator guide</b>\n\n1. Add the bot as administrator.\n2. Disable privacy mode in BotFather.\n3. Open <code>/menu</code> and choose Settings.\n4. Configure a log channel.\n5. Use the administrative buttons to review reports and tickets.",
}


def menu_keyboard(section: str = "home", language: str = "es", role: str = "admin"):
    builder = InlineKeyboardBuilder()
    buttons_es = [
        ("📥 Música y videos", "downloads"), ("🎮 Economía y juegos", "economy"),
        ("⭐ Generales", "general"), ("🚨 Moderación", "moderation"),
        ("⚙️ Configuración", "settings"), ("🛡 Staff", "staff"),
        ("🧰 Herramientas de grupo", "grouptools"),
        ("📖 Guía de admins", "guide"),
    ]
    buttons_en = [
        ("📥 Music and videos", "downloads"), ("🎮 Economy and games", "economy"),
        ("⭐ General", "general"), ("🚨 Moderation", "moderation"),
        ("⚙️ Settings", "settings"), ("🛡 Staff", "staff"),
        ("🧰 Group tools", "grouptools"), ("📖 Admin guide", "guide"),
    ]
    buttons = buttons_en if language == "en" else buttons_es
    for label, key in buttons:
        if role == "user" and key in {"moderation", "settings", "staff", "grouptools", "guide"}:
            continue
        builder.button(text=label, callback_data=f"mainmenu:{key}")
    if section == "home":
        builder.button(text="💳 Servicios", callback_data="unified:0:catalog")
        builder.button(text="📝 Registrarme", callback_data="unified:0:register")
        builder.button(text="👤 Mi perfil", callback_data="unified:0:profile")
        builder.button(text="📚 Mi historial", callback_data="unified:0:historymenu")
        if role != "user":
            builder.button(text="🎛 Paneladmin", callback_data="unified:0:paneladmin")
        builder.button(text="💡 Send suggestion" if language == "en" else "💡 Enviar sugerencia", callback_data="suggest:start")
    if role != "user" and section in {"settings", "moderation", "staff", "grouptools"}:
        builder.button(text="🎛 Paneladmin", callback_data="unified:0:paneladmin")
    if section == "downloads" and role == "owner":
        builder.button(text="📥 Download panel" if language == "en" else "📥 Panel de descargas", callback_data="downloads:panel")
    if role == "owner" and section == "home":
        builder.button(text="👑 Control de descargas", callback_data="downloads:panel")
    if role != "user" and section == "settings":
        builder.button(text="🪄 Configuración guiada", callback_data="setup:home")
    if section != "home":
        builder.button(text="🏠 Home" if language == "en" else "🏠 Inicio", callback_data="mainmenu:home")
        builder.adjust(2, 2, 2, 1, 1, 1)
    else:
        builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


HOME = (
    "🤖 <b>NEXORA ONE — Menú principal</b>\n\n"
    "Elige una categoría. Los botones muestran todos los comandos y ejemplos de uso."
)
HOME_EN = "🤖 <b>NEXORA ONE — Main menu</b>\n\nChoose a category to view its commands and controls."


@router.message(Command("menu"))
async def main_menu(message: Message):
    language = (await get_settings(message.chat.id)).get("language", "es")
    home = HOME_EN if language == "en" else HOME
    role = await menu_role(message.bot, message.chat.id, message.from_user.id)
    await message.reply(home, parse_mode="HTML", reply_markup=menu_keyboard(language=language, role=role))


async def menu_role(bot, chat_id, user_id):
    from app.config import OWNER_USER_ID
    from app.services.filters import is_admin
    if user_id == OWNER_USER_ID:
        return "owner"
    if chat_id < 0 and await is_admin(bot, chat_id, user_id):
        return "admin"
    return "user"


@router.callback_query(F.data.startswith("mainmenu:"))
async def menu_callback(callback: CallbackQuery):
    section = callback.data.split(":", 1)[1]
    role = await menu_role(callback.bot, callback.message.chat.id, callback.from_user.id)
    if role == "user" and section in {"moderation", "settings", "staff", "grouptools", "guide"}:
        await callback.answer("Esta sección es para administradores del grupo.", show_alert=True)
        return
    language = (await get_settings(callback.message.chat.id)).get("language", "es")
    home = HOME_EN if language == "en" else HOME
    sections = EN_SECTIONS if language == "en" else SECTIONS
    text = home if section == "home" else sections.get(section, home)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=menu_keyboard(section, language, role))
    await callback.answer()
