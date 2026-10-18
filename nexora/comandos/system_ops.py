import json
import os
from html import escape

from telegram import Update
from telegram.ext import ContextTypes
from nexora.comandos.bot_errors import api_error_text
from nexora.comandos.utils import API_BASE, INTERNAL_API_KEY, fetch_api_json_async, is_admin_id
from app.services.message_ui import field, heading, section

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")

CFG = {}
try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            CFG = json.load(f) or {}
except Exception:
    CFG = {}

PANEL_URL = (
    os.environ.get("NEXORA_PANEL_URL")
    or os.environ.get("SPIDERSYN_PANEL_URL")
    or CFG.get("PANEL_URL")
    or (f"{API_BASE}/admin/panel" if API_BASE else "")
).rstrip("/")
def _is_admin(user_id: int) -> bool:
    return is_admin_id(user_id)


def _api_error_message(action: str, status: int, data) -> str:
    return api_error_text(action, status, data)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not user or not _is_admin(user.id):
        await msg.reply_text("🔒 No tienes permisos para usar /status.", reply_to_message_id=msg.message_id)
        return
    if not API_BASE:
        await msg.reply_text("⚠️ API_BASE no está configurado.", reply_to_message_id=msg.message_id)
        return

    st, data = await fetch_api_json_async("/health", timeout=15)
    if st != 200 or not isinstance(data, dict):
        await msg.reply_text(_api_error_message("consultar /status", st, data), parse_mode="HTML", reply_to_message_id=msg.message_id)
        return
    storage = data.get("storage") or {}
    items = storage.get("items") or []
    metrics = data.get("metrics") or {}
    usuarios = metrics.get("usuarios") or {}
    keys = metrics.get("keys") or {}
    solicitudes = metrics.get("solicitudes") or {}
    errores = metrics.get("errores") or {}
    catalogo = metrics.get("catalogo") or {}
    config_state = {
        "api_base": "OK" if API_BASE else "FALTA",
        "panel": "OK" if PANEL_URL else "FALTA",
        "key": "OK" if INTERNAL_API_KEY else "FALTA",
    }
    worker_online = bool(data.get("worker_online", True))
    lines = [
        heading("🧭", "Estado de NEXORA ONE"),
        "",
        section("🌐", "Servicios"),
        field("✅" if st == 200 else "⚠️", "Web", f"{st} · {data.get('status', 'error')}", code=True),
        field("🤖" if worker_online else "⚠️", "Worker", "En línea" if worker_online else "Sin heartbeat"),
        field("🔗", "API interna", API_BASE or "Sin configurar", code=True),
        f"🖥️ <b>Panel:</b> <a href=\"{escape(PANEL_URL, quote=True)}\">Abrir panel</a>" if PANEL_URL else "🖥️ <b>Panel:</b> Sin configurar",
        "",
        section("🗄️", "Almacenamiento"),
        field("📁", "Directorio", storage.get("data_dir", "—"), code=True),
        field("🔐", "Configuración", f"API {config_state['api_base']} · Panel {config_state['panel']} · Clave {config_state['key']}"),
    ]
    for item in items:
        available = item.get("exists") and item.get("in_data_dir")
        lines.append(field("✅" if available else "⚠️", item.get("name", "Base de datos"), f"{item.get('size', 0)} bytes"))
    lines.extend([
        "",
        section("📊", "Actividad"),
        field("👥", "Usuarios", f"{usuarios.get('total', 0)} total · {usuarios.get('activos', 0)} activos · {usuarios.get('baneados', 0)} baneados"),
        field("🔑", "Keys", f"{keys.get('total', 0)} total · {keys.get('disponibles', 0)} disponibles · {keys.get('canjes', 0)} canjes"),
        field("📨", "Solicitudes", f"{solicitudes.get('pending', 0)} pendientes · {solicitudes.get('resolved', 0)} resueltas · {solicitudes.get('failed', 0)} fallidas"),
        field("🛍️", "Catálogo", f"{catalogo.get('commands', 0)} comandos · {catalogo.get('active_commands', 0)} activos · {catalogo.get('categories', 0)} categorías · {catalogo.get('buy_packages', 0)} paquetes /buy"),
        field("🧯", "Errores", f"{errores.get('ultimos_15m', 0)} en 15 min · {errores.get('ultimos_24h', 0)} en 24 h"),
    ])
    await msg.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True, reply_to_message_id=msg.message_id)


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not user or not _is_admin(user.id):
        await msg.reply_text("🔒 No tienes permisos para usar /paneladmin.", reply_to_message_id=msg.message_id)
        return
    if not PANEL_URL:
        await msg.reply_text("⚠️ Panel URL no está configurada.", reply_to_message_id=msg.message_id)
        return
    await msg.reply_text(
        f"🖥️ <b>Panel de administración</b>\n\n"
        f"<a href=\"{escape(PANEL_URL, quote=True)}\">Abrir NEXORA ONE</a>",
        parse_mode="HTML", disable_web_page_preview=True, reply_to_message_id=msg.message_id,
    )
