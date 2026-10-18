from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
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
        "🌙 <code>/noche on 22:00 07:00 America/Santiago</code> · <code>/noche off</code>\n"
        "🚨 <code>/antiraid on 8 30</code> · <code>/antiraid off</code>\n"
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
        "⚡ <code>/setcmd nombre respuesta</code> · <code>/mycmds</code>\n"
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

SECTIONS["grouptools"] += (
    "\n\n🧩 <b>Comandos personalizados</b>\n"
    "<code>/setcmd nombre texto</code> crea una respuesta. Para guardar foto, audio, video, GIF, "
    "documento, sticker o formato, responde al mensaje con <code>/setcmd nombre</code>; conserva el original en el grupo.\n"
    "Lista: <code>/mycmds</code> · Borrar: <code>/delcmd nombre</code>."
    "\n\n🧩 <b>Respuestas automáticas</b>\n"
    "<code>/filter palabra respuesta</code> busca en el mensaje; <code>/filter exact:hola respuesta</code> exige coincidencia exacta; <code>/filter prefix:/ayuda respuesta</code> busca al inicio.\n"
    "También puedes responder a una foto, video, GIF, audio o sticker con <code>/filter palabra</code>. Lista: <code>/filters</code> · borrar: <code>/stop palabra</code>."
)
SECTIONS["general"] += (
    "\n\n💳 <b>Cuenta y créditos</b>\n"
    "<code>/me</code> · <code>/me ID</code> · responde al mensaje de alguien con <code>/me</code>."
)

EN_SECTIONS = {
    "downloads": (
        "📥 <b>Music and videos</b>\n\n"
        "🎵 <code>/play song</code> — search and download audio\n"
        "🎬 <code>/playvideo name or link</code> — find or download a video\n"
        "📄 <code>/playdoc name or link</code> — send video as a document\n"
        "🎶 <code>/tiktok link</code> · 📸 <code>/instagram link</code> · 📘 <code>/facebook link</code>\n\n"
        "You can also send a TikTok, Reel, or YouTube Shorts link directly.\n"
        "📥 <code>/cola</code> — queue and progress\n"
        "⭐ <code>/favoritos</code> — saved media\n"
        "📚 <code>/historial</code> — recent downloads\n"
        "📊 <code>/estadisticasbot</code> — download statistics"
    ),
    "economy": (
        "🎮 <b>Economy and games</b>\n\n"
        "👤 <code>/register</code> — create your account\n"
        "💼 <code>/perfil</code> — balance, XP, and level\n"
        "🎴 <code>/tarjeta</code> — profile card\n"
        "🎁 <code>/daily</code> — daily reward\n"
        "🎯 <code>/misiones</code> — goals and rewards\n"
        "⛏ <code>/minar</code> · 🎣 <code>/pescar</code> — earn soles\n"
        "🎰 <code>/tragamonedas</code> or <code>/ruleta</code>\n"
        "💸 <code>/transferir amount</code> — reply to a user\n"
        "🛍 <code>/tienda</code> · <code>/comprar item</code>\n"
        "🎒 <code>/inventario</code> — your items\n"
        "🏆 <code>/ranksoles</code> · <code>/ranknivel</code> · <code>/rankrep</code>"
    ),
    "general": (
        "⭐ <b>General commands</b>\n\n"
        "🏓 <code>/ping</code> — check response time\n"
        "🆔 <code>/id</code> — user and chat IDs\n"
        "📜 <code>/rules</code> — group rules\n"
        "📊 <code>/stats</code> — group statistics\n"
        "🚩 <code>/report reason</code> — reply to a message to report it\n"
        "🎫 <code>/ticket reason</code> — ask for help\n"
        "📬 <code>/miscasos</code> — check tickets and suggestions\n"
        "🎤 <code>/letra artist song</code> — find lyrics\n"
        "🧮 <code>/calcular 2*(5+3)</code> — calculator\n\n"
        "💡 Use the suggestion button below to send an idea.\n"
        "💳 <code>/me</code> · <code>/me ID</code> — check your account or another user"
    ),
    "moderation": (
        "🚨 <b>Moderation</b>\n\n"
        "Reply to a user and use:\n"
        "⚠️ <code>/warn reason</code> · <code>/unwarn</code> · <code>/warns</code>\n"
        "🔇 <code>/mute 10m reason</code> · <code>/unmute</code>\n"
        "⛔ <code>/bang reason</code> · <code>/unbang ID</code>\n"
        "🎛 <code>/acciones</code> — quick actions\n"
        "📋 <code>/logs</code> · <code>/reports</code> · <code>/tickets</code>\n"
        "You can also target a user by ID: <code>/warn ID reason</code> or <code>/mute ID 10m reason</code>.\n"
        "🗂 <code>/sanciones ID</code> — group moderation history\n"
        "💬 <code>/responderticket ID reply</code>"
    ),
    "settings": (
        "⚙️ <b>Group settings</b>\n\n"
        "Only group admins can change these settings. Each group has its own configuration.\n"
        "🔗 <code>/antilink on|off</code> · ⚡ <code>/antiflood on|off</code> · 🛡 <code>/captcha on|off</code>\n"
        "👋 <code>/setwelcome text {name}</code> · 🖼 <code>/setwelcomemedia</code> — reply with a photo or GIF\n"
        "📜 <code>/setrules text</code> · 🧹 <code>/addbadword word</code> · <code>/delbadword word</code>\n"
        "🌙 <code>/noche on 22:00 07:00 America/Santiago</code> · <code>/noche off</code>\n"
        "🚨 <code>/antiraid on 8 30</code> · <code>/antiraid off</code>\n"
        "📡 <code>/setlogchannel ID</code> · 📢 <code>/canalobligatorio @channel</code>\n"
        "📊 <code>/statssemanales on|off</code> · 🧹 <code>/autolimpieza 15</code>\n"
        "📦 <code>/exportarconfig</code> · <code>/importarconfig</code>\n"
        "🌐 <code>/idioma es|en</code> — change this menu's language"
    ),
    "staff": (
        "🛡 <b>Staff and administration</b>\n\n"
        "👥 <code>/staff</code> · <code>/admins</code> — list the team\n"
        "⬆️ <code>/promotebtn</code> — promote with buttons\n"
        "⬇️ <code>/demote</code> — reply to the admin to remove their role\n"
        "🏷 <code>/staffnick Name</code> — set a staff nickname\n"
        "🎖 <code>/staffrole Role</code> — set a staff role\n"
        "👤 <code>/infouser</code> — moderation profile"
    ),
    "grouptools": (
        "🧰 <b>Advanced group tools</b>\n\n"
        "🗒 Notes: <code>/save name text</code> · <code>/get name</code> · <code>/notes</code>\n"
        "⚡ Custom commands: <code>/setcmd name reply</code> · <code>/mycmds</code> · <code>/delcmd name</code>\n"
        "🧩 Auto replies: <code>/filter</code> · <code>/filters</code> · <code>/stop word</code>\n"
        "📌 <code>/pin</code> · <code>/unpin</code> · <code>/unpinall</code> · 🐢 <code>/slowmode 10</code>\n"
        "🔒 <code>/bloquear photos</code> · <code>/desbloquear photos</code> · <code>/bloqueos</code>\n"
        "🔗 <code>/whitelistlink youtube.com</code> · <code>/whitelistlinks</code>\n"
        "👤 <code>/whitelistuser ID</code> · <code>/whitelistusers</code>\n\n"
        "🎉 <code>/sorteo 10m Prize</code> · <code>/finalizarsorteo ID</code>\n"
        "📊 <code>/actividad</code> · <code>/rankactividad</code> · ⭐ <code>/perfil</code>\n"
        "🗓 <code>/programar 30m Message</code> · <code>/programados</code>\n"
        "📊 <code>/encuesta Question | Yes | No</code>\n"
        "📋 <code>/copiarconfig SOURCE_ID</code> — run this in the destination group"
    ),
    "guide": (
        "📖 <b>Quick guide for group admins</b>\n\n"
        "1️⃣ Add the bot as an administrator and grant the permissions it needs.\n"
        "2️⃣ Open <code>/menu</code> and choose Group settings.\n"
        "3️⃣ Set up logs with <code>/setlogchannel ID</code>.\n"
        "4️⃣ Reply to a user's message and use <code>/acciones</code> to moderate.\n"
        "5️⃣ Review open reports and tickets in the admin panel.\n\n"
        "🔐 <b>Private owner tools</b>\n"
        "• <code>/backup</code> — create a backup now\n"
        "• <code>/estado</code> — service health, memory, disk, and groups\n"
        "• <code>/exportargrupo ID</code> — export a group configuration\n"
        "• <code>/descargaslibres ID</code> · <code>/quitarlibre ID</code>\n"
        "• <code>/usuarioslibres</code> · <code>/paneldescargas</code>\n"
        "• Reply to a .db file with <code>/restaurar</code>\n"
        "• <code>/cancelar</code> — cancel an operation"
    ),
}


def menu_keyboard(section: str = "home", language: str = "es", role: str = "admin"):
    builder = InlineKeyboardBuilder()
    buttons_es = [
        ("📥 Música y videos", "downloads"), ("🎮 Economía y juegos", "economy"),
        ("⭐ Ayuda y utilidades", "general"), ("🚨 Moderación", "moderation"),
        ("⚙️ Ajustes del grupo", "settings"), ("🛡 Equipo admin", "staff"),
        ("🧰 Herramientas de grupo", "grouptools"),
        ("📖 Guía de admins", "guide"),
    ]
    buttons_en = [
        ("📥 Music and videos", "downloads"), ("🎮 Economy and games", "economy"),
        ("⭐ Help and tools", "general"), ("🚨 Moderation", "moderation"),
        ("⚙️ Group settings", "settings"), ("🛡 Admin team", "staff"),
        ("🧰 Group tools", "grouptools"), ("📖 Admin guide", "guide"),
    ]
    buttons = buttons_en if language == "en" else buttons_es
    if section != "home":
        buttons = []
    if section == "home":
        home_actions = (
            [("💳 Services", "unified:0:catalog"), ("📝 Register", "unified:0:register"),
             ("🛍️ Store", "unified:0:buy"), ("👤 My profile", "unified:0:profile"),
             ("📚 My history", "unified:0:historymenu")]
            if language == "en" else
            [("💳 Consultas y servicios", "unified:0:catalog"), ("📝 Crear cuenta gratis", "unified:0:register"),
             ("🛍️ Tienda", "unified:0:buy"), ("👤 Mi perfil", "unified:0:profile"),
             ("📚 Mi historial", "unified:0:historymenu")]
        )
        for label, callback_data in home_actions:
            builder.button(text=label, callback_data=callback_data)
        for label, key in buttons:
            if role == "user" and key in {"moderation", "settings", "staff", "grouptools", "guide"}:
                continue
            builder.button(text=label, callback_data=f"mainmenu:{key}")
        if role != "user":
            label = "🎛 Admin panel" if language == "en" else "🎛 Panel de administración"
            builder.button(text=label, callback_data="unified:0:paneladmin")
    if section == "general":
        label = "💡 Send suggestion" if language == "en" else "💡 Enviar sugerencia"
        builder.button(text=label, callback_data="suggest:start")
    if role != "user" and section in {"moderation", "staff", "grouptools"}:
        builder.button(text="\U0001f39b Admin panel" if language == "en" else "\U0001f39b Panel de administración", callback_data="unified:0:paneladmin")
    if section == "downloads" and role == "owner":
        builder.button(text="📥 Download panel" if language == "en" else "📥 Panel de descargas", callback_data="downloads:panel")
    if role != "user" and section == "settings":
        builder.button(text="\U0001fa84 Guided setup" if language == "en" else "\U0001fa84 Configuración guiada", callback_data="setup:home")
    if section != "home":
        builder.button(text="↩️ All categories" if language == "en" else "↩️ Volver a categorías", callback_data="mainmenu:home")
        builder.adjust(2)
    else:
        builder.adjust(2)
    return builder.as_markup()


HOME = (
    "✨ <b>NEXORA ONE</b>\n"
    "Tu espacio para servicios, juegos y herramientas de comunidad.\n\n"
    "<b>¿Qué quieres hacer?</b>\n"
    "Elige un acceso rápido o abre una categoría. Para usar los servicios, crea tu cuenta gratis con /register."
)
HOME_EN = (
    "✨ <b>NEXORA ONE</b>\n"
    "Your space for services, games, and community tools.\n\n"
    "<b>What would you like to do?</b>\n"
    "Choose a quick action or open a category. Create your free account to use services with /register."
)
WELCOME = (
    "¡Hola, {name}! 👋\n\n"
    "Soy <b>NEXORA ONE</b>: servicios, juegos, multimedia y herramientas para tu comunidad.\n\n"
    "Usa los accesos rápidos o explora las categorías. Para usar los servicios, crea tu cuenta gratis con /register."
)
WELCOME_EN = (
    "Hi, {name}! 👋\n\n"
    "I am <b>NEXORA ONE</b>: services, games, media, and tools for your community.\n\n"
    "Use a quick action or browse the categories. Create your free account to use services with /register."
)


@router.message(Command("menu"))
async def main_menu(message: Message):
    language = (await get_settings(message.chat.id)).get("language", "es")
    home = HOME_EN if language == "en" else HOME
    role = await menu_role(message.bot, message.chat.id, message.from_user.id)
    await message.reply(home, parse_mode="HTML", reply_markup=menu_keyboard(language=language, role=role))


@router.message(CommandStart())
async def start(message: Message):
    language = (await get_settings(message.chat.id)).get("language", "es")
    role = await menu_role(message.bot, message.chat.id, message.from_user.id)
    template = WELCOME_EN if language == "en" else WELCOME
    name = (message.from_user.first_name or "").strip() or "amigo"
    await message.reply(
        template.format(name=escape(name)),
        parse_mode="HTML",
        reply_markup=menu_keyboard(language=language, role=role),
    )


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
    if section != "home" and section not in SECTIONS:
        await callback.answer("Esta opción ya no está disponible. Abre /start para ver el menú actualizado.", show_alert=True)
        return
    role = await menu_role(callback.bot, callback.message.chat.id, callback.from_user.id)
    if role == "user" and section in {"moderation", "settings", "staff", "grouptools", "guide"}:
        await callback.answer("Esta sección es para administradores del grupo.", show_alert=True)
        return
    language = (await get_settings(callback.message.chat.id)).get("language", "es")
    home = HOME_EN if language == "en" else HOME
    sections = EN_SECTIONS if language == "en" else SECTIONS
    text = home if section == "home" else sections[section]
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=menu_keyboard(section, language, role))
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            await callback.answer("Ya estás viendo esta sección.")
        else:
            await callback.answer("No pude abrir esta sección. Vuelve a /start e inténtalo otra vez.", show_alert=True)
        return
    await callback.answer()
