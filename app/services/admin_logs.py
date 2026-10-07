from html import escape

from app.services.database import get_settings


async def send_admin_log(bot, group_id: int, action: str, user_id: int | None = None,
                         admin_id: int | None = None, detail: str | None = None):
    settings = await get_settings(group_id)
    log_chat_id = settings.get("log_chat_id")
    if not log_chat_id:
        return False
    try:
        group_title = (await bot.get_chat(group_id)).title or "Sin nombre"
    except Exception:
        group_title = "Grupo desconocido"
    text = (
        "🧾 <b>Registro administrativo</b>\n\n"
        f"Grupo: <b>{escape(group_title)}</b>\n"
        f"ID del grupo: <code>{group_id}</code>\n"
        f"Acción: <b>{escape(action)}</b>\n"
        f"Usuario: <code>{user_id or '-'}</code>\n"
        f"Administrador: <code>{admin_id or '-'}</code>"
    )
    if detail:
        text += f"\nDetalle: {escape(detail[:500])}"
    try:
        await bot.send_message(log_chat_id, text, parse_mode="HTML")
        return True
    except Exception:
        return False
