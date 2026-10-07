"""Single command entry points for the merged bot."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import OWNER_USER_ID
from app.handlers import features, media, automation, group_tools
from app.handlers.menu import menu_role
from nexora.runtime import runtime, COMMANDS, CALLBACKS
from nexora.comandos.utils import API_BASE, fetch_api_json_async

router = Router()

def choices(items, user_id=None):
    builder = InlineKeyboardBuilder()
    for label, action in items:
        builder.button(text=label, callback_data=f"unified:{user_id or 0}:{action}")
    builder.adjust(2)
    return builder.as_markup()

@router.message(Command("register"))
async def register(message):
    user = message.from_user
    existed = await features._is_registered(user.id)
    if API_BASE:
        status, result = await fetch_api_json_async(f"/register?ID_TG={user.id}")
        if status not in (200, 423):
            await message.answer("No pude conectar el registro de servicios. No se cambió tu saldo; intenta nuevamente.")
            return
        existed = existed and status == 423
    await features._init_user(user.id, user.full_name, message.chat.id)
    text = "Ya estás registrado." if existed else "Registro completado."
    text += " Tus créditos y soles se guardan por separado. Usa /perfil."
    if not API_BASE:
        text += " La cuenta de servicios estará disponible cuando se conecte la web."
    await message.answer(text)

@router.message(Command("perfil"))
async def profile(message):
    await message.answer("👤 Tu perfil — elige qué consultar:", reply_markup=choices([
        ("💳 Cuenta y créditos", "account"), ("💵 Soles y juegos", "economy"),
        ("📈 Actividad del grupo", "activity"), ("🎴 Tarjeta", "card")], message.from_user.id))

@router.message(Command("historial"))
async def history(message):
    await message.answer("📚 Tu historial:", reply_markup=choices([
        ("📥 Descargas", "downloads"), ("🧾 Servicios", "history")], message.from_user.id))

@router.message(Command("paneladmin"))
async def panel(message):
    role = await menu_role(message.bot, message.chat.id, message.from_user.id)
    if role == "user":
        await message.answer("Solo el dueño o administradores del grupo pueden abrir este panel.")
        return
    builder = InlineKeyboardBuilder()
    if message.chat.id < 0:
        for label, value in [("⚙️ Configuración", "panel:home"), ("🛡 Moderación", "center:home"),
                             ("🪄 Asistente", "setup:home"), ("⚡ Comandos del grupo", f"unified:{message.from_user.id}:custom")]:
            builder.button(text=label, callback_data=value)
    if role == "owner":
        for label, action in [("💳 Administración de servicios", "admin"), ("🌐 Panel web", "web")]:
            builder.button(text=label, callback_data=f"unified:{message.from_user.id}:{action}")
        builder.button(text="📥 Descargas", callback_data="downloads:panel")
    builder.adjust(1)
    await message.answer("🎛 Panel administrativo\n\nDueño: /ban, /unban, /bangg, /unbangg, /backup.\nGrupo: /bang y /unbang.", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("unified:"))
async def selected(callback):
    _, owner, action = callback.data.split(":", 2)
    if int(owner) not in (0, callback.from_user.id):
        await callback.answer("Abre tu propio /perfil o /historial.", show_alert=True)
        return
    await callback.answer()
    message = callback.message.model_copy(update={"from_user": callback.from_user, "reply_to_message": None}).as_(callback.bot)
    local = {"economy": features.profile, "activity": automation.level,
             "card": features.profile_card, "downloads": media.download_history,
             "register": register, "profile": profile, "historymenu": history}
    if action in local:
        await local[action](message)
    elif action == "paneladmin":
        await panel(message)
    elif action == "custom":
        if await menu_role(callback.bot, message.chat.id, callback.from_user.id) != "user":
            await group_tools.commands(message)
    elif action in {"account", "history", "catalog", "admin", "web"}:
        await runtime.invoke(callback, action)

@router.message(Command(*COMMANDS))
async def service_command(message):
    await runtime.invoke(message)

@router.callback_query(lambda event: any((event.data or "").startswith(prefix) for prefix in CALLBACKS))
async def service_callback(callback):
    await runtime.invoke(callback)

@router.message(lambda message: message.from_user and message.from_user.id == OWNER_USER_ID and not (message.text or "").startswith("/") and runtime.waiting_for_owner(message.from_user.id))
async def service_followup(message):
    await runtime.invoke(message)
