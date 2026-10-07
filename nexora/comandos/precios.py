import html
from telegram import Update
from telegram.ext import ContextTypes

from nexora.comandos.request_catalog import REQUEST_COMMANDS
from nexora.comandos.utils import fetch_api_json_async

MAX_MESSAGE = 3600


async def _fetch_catalog_prices():
    _status, js = await fetch_api_json_async("/bot_catalog", timeout=12)
    if (js or {}).get("status") != "ok":
        return []
    commands = ((js or {}).get("data") or {}).get("commands") or []
    rows = []
    for cmd in commands:
        if not bool(cmd.get("is_active", True)):
            continue
        rows.append(
            {
                "slug": str(cmd.get("slug") or "").strip().lower(),
                "name": str(cmd.get("name") or cmd.get("slug") or "").strip(),
                "cost": int(cmd.get("cost") or 0),
                "category": str(cmd.get("category_name") or "SIN CATEGORIA").strip(),
            }
        )
    return sorted(rows, key=lambda item: (item["category"], item["slug"]))


async def precios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    catalog_rows = await _fetch_catalog_prices()
    if catalog_rows:
        pages = []
        texto = ["💳 <b>PRECIOS DEL BOT</b>", f"🧩 <b>Total:</b> <code>{len(catalog_rows)}</code> comandos activos", ""]
        current = None
        for row in catalog_rows:
            if row["category"] != current:
                current = row["category"]
                texto.append(f"\n<b>{html.escape(current)}</b>")
            line = f"• <code>/{html.escape(row['slug'])}</code> → <code>{row['cost']}</code> créditos"
            draft = "\n".join([*texto, line])
            if len(draft) > MAX_MESSAGE:
                pages.append("\n".join(texto))
                texto = [f"💳 <b>PRECIOS DEL BOT</b> · continuación", f"\n<b>{html.escape(current)}</b>", line]
            else:
                texto.append(line)
        if texto:
            pages.append("\n".join(texto))
        total_pages = len(pages)
        for idx, page in enumerate(pages, start=1):
            suffix = f"\n\n📖 Página <code>{idx}/{total_pages}</code>" if total_pages > 1 else ""
            await msg.reply_text(
                page + suffix,
                parse_mode="HTML",
                reply_to_message_id=msg.message_id if idx == 1 else None,
            )
        return

    if not REQUEST_COMMANDS:
        await msg.reply_text(
            "⚠️ No hay precios configurados.",
            reply_to_message_id=msg.message_id
        )
        return

    texto = []
    texto.append("💳 <b>PRECIOS DEL BOT</b>\n")

    for comando, precio, *_ in sorted(REQUEST_COMMANDS):
        texto.append(f"• <b>{html.escape(comando.upper())}</b> → <code>{precio}</code> créditos")

    await msg.reply_text(
        "\n".join(texto),
        parse_mode="HTML",
        reply_to_message_id=msg.message_id
    )
