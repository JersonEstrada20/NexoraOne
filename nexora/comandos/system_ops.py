import json
import os

from telegram import Update
from telegram.ext import ContextTypes
from nexora.comandos.bot_errors import api_error_text
from nexora.comandos.utils import API_BASE, INTERNAL_API_KEY, fetch_api_json_async, is_admin_id

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
        await msg.reply_text("No tienes permisos para usar /status.", reply_to_message_id=msg.message_id)
        return
    if not API_BASE:
        await msg.reply_text("API_BASE no está configurado.", reply_to_message_id=msg.message_id)
        return

    st, data = await fetch_api_json_async("/health", timeout=15)
    if st != 200 or not isinstance(data, dict):
        await msg.reply_text(_api_error_message("consultar /status", st, data), parse_mode="HTML", reply_to_message_id=msg.message_id)
        return
    storage = (data or {}).get("storage") or {}
    items = storage.get("items") or []
    metrics = (data or {}).get("metrics") or {}
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
    lines = [
        "<b>NEXORA ONE ⇒ STATUS</b>",
        f"Web: <code>{st}</code> · {(data or {}).get('status', 'error')}",
        "Worker: <code>OK</code> · este comando respondió",
        f"Data dir: <code>{storage.get('data_dir', '—')}</code>",
        f"API_BASE: <code>{API_BASE or 'NO CONFIG'}</code>",
        f"Panel: <code>{PANEL_URL or 'NO CONFIG'}</code>",
        f"Config: API <code>{config_state['api_base']}</code> · Panel <code>{config_state['panel']}</code> · Key <code>{config_state['key']}</code>",
        "",
        "<b>DB</b>",
    ]
    for item in items:
        mark = "OK" if item.get("exists") and item.get("in_data_dir") else "WARN"
        lines.append(f"{mark} · {item.get('name')} · {item.get('size', 0)} bytes")
    lines.extend(
        [
            "",
            "<b>Usuarios</b>",
            f"Total: <code>{usuarios.get('total', 0)}</code> · Activos: <code>{usuarios.get('activos', 0)}</code> · Baneados: <code>{usuarios.get('baneados', 0)}</code>",
            "",
            "<b>Keys</b>",
            f"Total: <code>{keys.get('total', 0)}</code> · Disponibles: <code>{keys.get('disponibles', 0)}</code> · Canjes: <code>{keys.get('canjes', 0)}</code>",
            "",
            "<b>Solicitudes</b>",
            f"Pendientes: <code>{solicitudes.get('pending', 0)}</code> · Resueltas: <code>{solicitudes.get('resolved', 0)}</code> · Fallidas: <code>{solicitudes.get('failed', 0)}</code>",
            "",
            "<b>Catálogo</b>",
            f"Comandos: <code>{catalogo.get('commands', 0)}</code> · Activos: <code>{catalogo.get('active_commands', 0)}</code> · Categorías: <code>{catalogo.get('categories', 0)}</code> · /buy: <code>{catalogo.get('buy_packages', 0)}</code>",
            "",
            "<b>Errores</b>",
            f"15m: <code>{errores.get('ultimos_15m', 0)}</code> · 24h: <code>{errores.get('ultimos_24h', 0)}</code>",
        ]
    )
    await msg.reply_text("\n".join(lines), parse_mode="HTML", reply_to_message_id=msg.message_id)


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not user or not _is_admin(user.id):
        await msg.reply_text("No tienes permisos para usar /paneladmin.", reply_to_message_id=msg.message_id)
        return
    if not PANEL_URL:
        await msg.reply_text("Panel URL no está configurada.", reply_to_message_id=msg.message_id)
        return
    await msg.reply_text(f"<b>Panel:</b>\n{PANEL_URL}", parse_mode="HTML", reply_to_message_id=msg.message_id)
