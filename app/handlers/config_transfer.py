import io
import json
from datetime import datetime

from nexora import async_db as aiosqlite
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from app.config import DB_PATH
from app.services.filters import is_admin

router = Router()
TABLES = {
    "bad_words": ["word"],
    "group_notes": ["name", "content", "created_by"],
    "custom_commands": ["name", "content", "created_by"],
    "content_locks": ["content_type"],
    "link_whitelist": ["domain"],
    "user_whitelist": ["user_id"],
    "level_roles": ["level", "role_name"],
}


async def _admin(message: Message):
    if message.chat.type == "private" or not message.from_user:
        await message.answer("Este comando se usa en un grupo."); return False
    if not await is_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("🔒 Solo administradores."); return False
    return True


async def build_group_export(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        columns = [row[1] for row in await (await db.execute("PRAGMA table_info(group_settings)")).fetchall()]
        row = await (await db.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,))).fetchone()
        settings = dict(zip(columns, row)) if row else {"chat_id": chat_id}
        settings.pop("chat_id", None)
        payload = {"format": "doxertube-group-config-v1", "settings": settings, "tables": {}}
        for table, fields in TABLES.items():
            rows = await (await db.execute(f"SELECT {','.join(fields)} FROM {table} WHERE chat_id=?", (chat_id,))).fetchall()
            payload["tables"][table] = [dict(zip(fields, item)) for item in rows]
    return payload


@router.message(Command("exportarconfig"))
async def export_config(message: Message):
    if not await _admin(message): return
    payload = await build_group_export(message.chat.id)
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    await message.answer_document(
        BufferedInputFile(raw, filename=f"config-grupo-{message.chat.id}-{stamp}.json"),
        caption="📦 Configuración exportada: reglas, notas, comandos, roles, bloqueos y listas blancas.")


@router.message(Command("importarconfig"))
async def import_config(message: Message):
    if not await _admin(message): return
    document = message.reply_to_message.document if message.reply_to_message and message.reply_to_message.document else None
    if not document or not (document.file_name or "").lower().endswith(".json"):
        await message.answer("Responde al archivo JSON con <code>/importarconfig</code>.", parse_mode="HTML"); return
    if document.file_size and document.file_size > 2 * 1024 * 1024:
        await message.answer("El archivo es demasiado grande."); return
    stream = io.BytesIO()
    await message.bot.download(document, destination=stream)
    try:
        payload = json.loads(stream.getvalue().decode("utf-8"))
    except Exception:
        await message.answer("❌ El archivo JSON no es válido."); return
    if payload.get("format") != "doxertube-group-config-v1" or not isinstance(payload.get("settings"), dict):
        await message.answer("❌ Este archivo no pertenece al exportador de NEXORA ONE."); return
    async with aiosqlite.connect(DB_PATH) as db:
        valid_columns = {row[1] for row in await (await db.execute("PRAGMA table_info(group_settings)")).fetchall()} - {"chat_id"}
        settings = {key: value for key, value in payload["settings"].items() if key in valid_columns}
        await db.execute("INSERT OR IGNORE INTO group_settings(chat_id) VALUES(?)", (message.chat.id,))
        if settings:
            await db.execute(f"UPDATE group_settings SET {','.join(f'{key}=?' for key in settings)} WHERE chat_id=?", (*settings.values(), message.chat.id))
        for table, fields in TABLES.items():
            await db.execute(f"DELETE FROM {table} WHERE chat_id=?", (message.chat.id,))
            for item in payload.get("tables", {}).get(table, []):
                if not isinstance(item, dict) or not all(field in item for field in fields): continue
                await db.execute(
                    f"INSERT OR IGNORE INTO {table}(chat_id,{','.join(fields)}) VALUES({','.join('?' for _ in range(len(fields)+1))})",
                    (message.chat.id, *(item[field] for field in fields)))
        await db.commit()
    await message.answer("✅ Configuración importada correctamente en este grupo.")
