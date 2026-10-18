import html
import json
import os
import sqlite3
from nexora.db import connect as db_connect
from urllib import parse as _urlparse

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from nexora.comandos.utils import API_BASE, configured_admin_ids, default_asset_url, fetch_api_json_async
from nexora.storage import db_path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = db_path("multiplataforma.db")

CFG = {}
try:
    if os.path.exists(CONFIG_FILE_PATH):
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            CFG = json.load(f) or {}
except Exception:
    CFG = {}

ADMIN_IDS = configured_admin_ids()
LOGO = CFG.get("LOGO", {}) or {}
CMDS = CFG.get("CMDS", {}) or {}
ALLOWED_VIEW_ROLES = {"FUNDADOR", "CO-FUNDADOR", "SELLER"}

SECTIONS = {
    "diag": {
        "title": "Diagnóstico",
        "lines": [
            "<code>/status</code> · Estado de web, worker, base, keys y errores.",
            "<code>/paneladmin</code> · Abrir el panel web.",
            "<code>/errores</code> · Consultar los últimos errores.",
        ],
    },
    "usuarios": {
        "title": "Usuarios",
        "lines": [
            "<code>/user ID</code> · Ver el perfil del usuario.",
            "<code>/ban ID</code> · Bloquear con confirmación.",
            "<code>/unban ID</code> · Quitar el bloqueo.",
            "<code>/dm ID mensaje</code> · Enviar un mensaje directo.",
        ],
    },
    "planes": {
        "title": "Créditos y planes",
        "lines": [
            "<code>/cred ID|PLAN|CANTIDAD</code> · Sumar créditos.",
            "<code>/uncred ID|PLAN|CANTIDAD</code> · Restar créditos.",
            "<code>/setcred ID|PLAN|CANTIDAD</code> · Establecer créditos.",
            "<code>/sub ID|PLAN|DÍAS</code> · Sumar días.",
            "<code>/unsub ID|PLAN|DÍAS</code> · Restar días.",
            "<code>/setsub ID|PLAN|DÍAS</code> · Establecer días.",
            "<code>/setrol ID|ROL</code> · Cambiar rol.",
            "<code>/setantispam ID|SEGUNDOS</code> · Cambiar el anti-spam.",
        ],
    },
    "keys": {
        "title": "Keys",
        "lines": [
            "<code>/genkey dias 30</code> · Crear una key de 30 días.",
            "<code>/genkey creditos 100</code> · Crear una key de 100 créditos.",
            "<code>/genkey dias 30 3 10</code> · Crear 10 keys de 3 usos.",
            "<code>/keysinfo KEY</code> · Ver el estado de una key.",
            "<code>/keyslog</code> · Consultar los últimos canjes.",
        ],
    },
    "solicitudes": {
        "title": "Solicitudes",
        "lines": [
            "<code>/pending</code> o <code>/solicitudes</code> · Ver solicitudes pendientes.",
            "<code>/reply ID texto</code> · Responder y cobrar.",
            "<code>/rquick ID plantilla</code> · Responder con una plantilla.",
            "<code>/done ID</code> · Finalizar una solicitud.",
            "<code>/close ID motivo</code> · Cerrar sin cobrar.",
            "<code>/fail ID motivo</code> · Marcar como fallida.",
            "<code>/reopen ID</code> · Reabrir una solicitud.",
            "<code>/requestlog 20</code> · Ver el historial reciente.",
        ],
    },
    "catalogo": {
        "title": "Catálogo y ventas",
        "lines": [
            "<code>/menu</code> · Abrir el catálogo público.",
            "<code>/buy</code> · Abrir la tienda pública.",
            "<code>/precios</code> · Consultar los precios.",
            "<code>/ventas</code> · Ver el resumen de ventas.",
        ],
    },
    "global": {
        "title": "Mensajes globales",
        "lines": [
            "<code>/global mensaje</code> · Preparar un envío con vista previa.",
            "<code>/global --all mensaje</code> · Incluir usuarios baneados.",
            "También puedes responder a una foto, video o archivo con <code>/global</code>.",
        ],
    },
}

BUTTON_ROWS = [
    [("🩺 Diagnóstico", "diag"), ("👥 Usuarios", "usuarios")],
    [("💎 Créditos y planes", "planes"), ("🔑 Keys", "keys")],
    [("📨 Solicitudes", "solicitudes"), ("🛍️ Catálogo y ventas", "catalogo")],
    [("📢 Mensajes globales", "global")],
]


def _brand() -> str:
    raw = (CFG.get("BOT_NAME") or CFG.get("NAME") or "NEXORA ONE").strip() or "NEXORA ONE"
    return "NEXORA ONE" if raw.upper() in {"SPIDERSYN", "#SPIDERSYN"} else raw


def _get_panel_settings() -> dict[str, str]:
    conn = db_connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS panel_settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
        """
    )
    cur.execute("SELECT key, value FROM panel_settings")
    rows = {row["key"]: row["value"] for row in cur.fetchall()}
    conn.close()
    return rows


def _admin_image_url() -> str:
    try:
        settings = _get_panel_settings()
    except Exception:
        settings = {}
    return (
        (settings.get("FT_CMDSADMIN") or "").strip()
        or (settings.get("FT_CMDS") or "").strip()
        or (LOGO.get("FT_CMDSADMIN") or "").strip()
        or (LOGO.get("FT_CMDS") or "").strip()
        or (CMDS.get("FT_CMDSADMIN") or "").strip()
        or default_asset_url("ft_cmdsadmin.png")
        or ""
    )


async def _role_for_user(user_id: int) -> str:
    if user_id in ADMIN_IDS:
        return "ADMIN"
    if not API_BASE:
        return ""
    st, js = await fetch_api_json_async(f"/tg_info?ID_TG={_urlparse.quote(str(user_id))}", timeout=15)
    if st != 200:
        return ""
    return str(((js.get("data") or {}).get("ROL_TG") or "")).upper().strip()


async def _can_view(user_id: int) -> tuple[bool, str]:
    role = await _role_for_user(user_id)
    return (user_id in ADMIN_IDS) or (role in ALLOWED_VIEW_ROLES), role


def _keyboard(active: str = "home") -> InlineKeyboardMarkup:
    rows = []
    for row in BUTTON_ROWS:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{'✅ ' if key == active else ''}{label}".strip(),
                    callback_data=f"adminmenu:{key}",
                )
                for label, key in row
            ]
        )
    if active != "home":
        rows.append([InlineKeyboardButton("↩️ Menú principal", callback_data="adminmenu:home")])
    return InlineKeyboardMarkup(rows)


def _home_text(role: str) -> str:
    return "\n".join(
        [
            f"🛡️ <b>{html.escape(_brand())} · ADMINISTRACIÓN</b>",
            f"👤 <i>Rol: {html.escape(role or 'SIN ROL')}</i>",
            "",
            "Elige una sección para ver sus acciones. También puedes usar los comandos directamente:",
            "<code>/paneladmin</code>",
            "",
            "⚡ <b>Accesos rápidos</b>",
            "📨 Solicitudes: <code>/pending</code> → <code>/rquick ID plantilla</code> → <code>/done ID</code>",
            "💎 Asignar plan: <code>/setsub ID|PREMIUM|30</code>",
            "🪙 Asignar créditos: <code>/cred ID|PREMIUM|100</code>",
            "🩺 Diagnóstico: <code>/status</code> · fallos: <code>/errores</code>",
        ]
    )


def _render(section: str = "home", role: str = "ADMIN") -> str:
    if section == "home" or section not in SECTIONS:
        return _home_text(role)
    data = SECTIONS[section]
    lines = [
        f"🧭 <b>{html.escape(_brand())} · {html.escape(data['title']).upper()}</b>",
        f"👤 <i>Rol: {html.escape(role or 'SIN ROL')}</i>",
        "",
        *(f"🔹 {line}" for line in data["lines"]),
    ]
    return "\n".join(lines)


async def _send_admin_menu(update: Update, section: str = "home") -> None:
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    allowed, role = await _can_view(user.id)
    if not allowed:
        await msg.reply_text(
            "Acceso denegado. Solo FUNDADOR / CO-FUNDADOR / SELLER o ADMIN_ID.",
            reply_to_message_id=msg.message_id,
        )
        return

    text = _render(section, role)
    markup = _keyboard(section)
    image_url = _admin_image_url()
    if image_url:
        try:
            await msg.reply_photo(
                photo=image_url,
                caption=text[:1024],
                parse_mode="HTML",
                reply_markup=markup,
                reply_to_message_id=msg.message_id,
            )
            if len(text) > 1024:
                await msg.reply_text(text[1024:], parse_mode="HTML", disable_web_page_preview=True)
            return
        except Exception:
            pass

    await msg.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=markup,
        reply_to_message_id=msg.message_id,
    )


async def admin_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _send_admin_menu(update, "home")


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if not query or not query.message or not user:
        return
    allowed, role = await _can_view(user.id)
    if not allowed:
        await query.answer("Acceso denegado.", show_alert=True)
        return
    await query.answer()

    section = (query.data or "adminmenu:home").split(":", 1)[-1] or "home"
    text = _render(section, role)
    markup = _keyboard(section)
    try:
        if query.message.photo:
            await query.edit_message_caption(caption=text[:1024], parse_mode="HTML", reply_markup=markup)
        else:
            await query.edit_message_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup,
            )
    except BadRequest as exc:
        if "Message is not modified" in str(exc):
            return
        await query.message.reply_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=markup,
        )
