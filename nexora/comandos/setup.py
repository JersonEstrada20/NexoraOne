import html
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from nexora.comandos.utils import API_BASE, INTERNAL_API_KEY, configured_admin_ids, fetch_api_json

OWNER_ID = 7454664711


def _panel_url() -> str:
    return (
        os.environ.get("NEXORA_PANEL_URL")
        or os.environ.get("SPIDERSYN_PANEL_URL")
        or (f"{API_BASE}/admin/panel" if API_BASE else "")
    ).rstrip("/")


def _ok(value: bool) -> str:
    return "OK" if value else "FALTA"


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if user.id != OWNER_ID:
        await msg.reply_text("Solo el dueño principal puede usar /setup.", reply_to_message_id=msg.message_id)
        return

    health_status = "sin API"
    runtime = {}
    if API_BASE:
        st, data = fetch_api_json("/health", timeout=15)
        health_status = f"{st} · {(data or {}).get('status', 'error')}"
        runtime = (data or {}).get("runtime") or {}

    admin_ids = ", ".join(str(x) for x in sorted(configured_admin_ids()))
    panel = _panel_url()
    lines = [
        "<b>NEXORA ONE ⇒ SETUP DUEÑO</b>",
        "",
        f"Owner: <code>{OWNER_ID}</code>",
        f"Admin IDs: <code>{html.escape(admin_ids or '—')}</code>",
        f"API base: <code>{html.escape(API_BASE or 'NO CONFIG')}</code>",
        f"Panel: <code>{html.escape(panel or 'NO CONFIG')}</code>",
        f"Internal key: <code>{_ok(bool(INTERNAL_API_KEY))}</code>",
        f"Health: <code>{html.escape(health_status)}</code>",
        f"Worker visto: <code>{html.escape(runtime.get('last_worker_seen') or '—')}</code>",
        f"Conflicto polling: <code>{html.escape(runtime.get('last_polling_conflict') or '—')}</code>",
        "",
        "<b>Desde el panel puedes configurar:</b>",
        "Links: OWNER_LINK, GRUPO_LINK, CANAL_LINK.",
        "Fotos: FT_START, FT_BUY, FT_CMDS, FT_CMDSADMIN.",
        "Sistema: volumen /data, errores y auditoria.",
    ]

    buttons = []
    if panel:
        buttons.append([InlineKeyboardButton("Abrir ajustes", url=f"{panel}?section=ajustes")])
        buttons.append([InlineKeyboardButton("Ver sistema", url=f"{panel}?section=sistema")])
    await msg.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        reply_to_message_id=msg.message_id,
    )
