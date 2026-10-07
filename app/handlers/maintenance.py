import asyncio
import html
import json
import os
import secrets
import sqlite3
from nexora.db import remote_enabled
import tempfile
from pathlib import Path

from nexora import async_db as aiosqlite
from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import BACKUP_CHAT_ID, DB_PATH, OWNER_USER_ID
from app.handlers.media import cancel_user_download, clear_user_media_requests
from app.services.backups import run_backup
from app.services.diagnostics import database_check, disk_status, memory_mb, self_test, uptime_text

router = Router()
PENDING_RESTORES: dict[str, dict] = {}


async def _downloads_panel_content():
    async with aiosqlite.connect(DB_PATH) as db:
        policy = await (await db.execute(
            "SELECT max_downloads,window_seconds,parallel_downloads FROM download_policy WHERE id=1"
        )).fetchone()
        users = await (await db.execute(
            "SELECT user_id,note FROM download_exemptions ORDER BY created_at DESC LIMIT 8"
        )).fetchall()
    maximum, window, parallel = policy or (3, 600, 3)
    lines = [
        "📥 <b>Panel de descargas</b>", "",
        f"🚦 Límite general: <b>{maximum}</b> cada <b>{max(1, window // 60)} min</b>",
        f"⚙️ Descargas simultáneas: <b>{parallel}</b>",
        f"👑 Dueño <code>{OWNER_USER_ID}</code>: <b>sin límites</b>", "",
    ]
    if users:
        lines.append("Toca un usuario para quitarle el acceso libre:")
        for user_id, note in users:
            detail = f" · {html.escape(note[:30])}" if note else ""
            lines.append(f"• <code>{user_id}</code>{detail}")
    else:
        lines.append("No hay usuarios adicionales con acceso libre.")
    builder = InlineKeyboardBuilder()
    builder.button(text="3 / 10 min", callback_data="downloads:policy:3:600")
    builder.button(text="5 / 10 min", callback_data="downloads:policy:5:600")
    builder.button(text="10 / 10 min", callback_data="downloads:policy:10:600")
    builder.button(text="➕ Cómo agregar", callback_data="downloads:addhelp")
    for user_id, _ in users:
        builder.button(text=f"🗑 Quitar {user_id}", callback_data=f"downloads:revoke:{user_id}")
    builder.button(text="🔄 Actualizar", callback_data="downloads:panel")
    builder.adjust(3, 1, *([1] * len(users)), 1)
    return "\n".join(lines), builder.as_markup()


async def _show_downloads_panel(message: Message):
    text, markup = await _downloads_panel_content()
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception:
        await message.reply(text, parse_mode="HTML", reply_markup=markup)


async def is_owner(bot, user_id: int) -> bool:
    if not BACKUP_CHAT_ID:
        return False
    try:
        member = await bot.get_chat_member(BACKUP_CHAT_ID, user_id)
        return member.status == ChatMemberStatus.CREATOR
    except Exception:
        return False


async def require_owner(message: Message) -> bool:
    if await is_owner(message.bot, message.from_user.id):
        return True
    await message.reply("🔒 Este comando es exclusivo del dueño del bot.")
    return False


@router.message(Command("cancelar"))
async def cancel_everything(message: Message, state: FSMContext):
    await state.clear()
    download = cancel_user_download(message.from_user.id)
    selections = clear_user_media_requests(message.from_user.id)
    details = []
    if download:
        details.append("descarga")
    if selections:
        details.append("búsqueda/selección")
    suffix = f" ({', '.join(details)})" if details else ""
    await message.reply(f"✅ Operación cancelada{suffix}.")


@router.message(Command("backup"))
async def backup_now(message: Message):
    if not await require_owner(message):
        return
    status = await message.reply("🗄 Creando copia privada…")
    try:
        await run_backup(message.bot)
        await status.edit_text("✅ Copia e índice enviados al canal privado.")
    except Exception as exc:
        await status.edit_text(f"❌ No pude enviar la copia: {str(exc).splitlines()[-1][:200]}")


@router.message(Command("estado", "diagnostico"))
async def owner_status(message: Message):
    if not await require_owner(message):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        groups = (await (await db.execute("SELECT COUNT(*) FROM group_settings")).fetchone())[0]
    free, total = await asyncio.to_thread(disk_status)
    errors = await self_test(message.bot)
    db_health = await asyncio.to_thread(database_check)
    health = "✅ Correcto" if not errors else "⚠️ " + "; ".join(errors)
    await message.reply(
        "🩺 <b>Estado de NEXORA ONE</b>\n\n"
        f"⏱ Encendido: <b>{uptime_text()}</b>\n"
        f"🧠 Memoria: <b>{memory_mb():.1f} MB</b>\n"
        f"💽 Disco libre: <b>{free // 1024 // 1024} MB</b> de {total // 1024 // 1024} MB\n"
        f"👥 Grupos configurados: <b>{groups}</b>\n"
        f"🗃 Base de datos: <b>{db_health}</b>\n"
        f"🔎 Diagnóstico: <b>{health}</b>",
        parse_mode="HTML",
    )


@router.message(Command("exportargrupo"))
async def export_group(message: Message, command: CommandObject):
    if not await require_owner(message):
        return
    try:
        group_id = int((command.args or "").strip())
    except ValueError:
        await message.reply("Uso: <code>/exportargrupo -1001234567890</code>", parse_mode="HTML")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        settings = await (await db.execute("SELECT * FROM group_settings WHERE chat_id=?", (group_id,))).fetchone()
        words = await (await db.execute("SELECT word FROM bad_words WHERE chat_id=? ORDER BY word", (group_id,))).fetchall()
    if not settings:
        await message.reply("❌ No encontré configuraciones para ese ID.")
        return
    payload = {"group_id": group_id, "settings": dict(settings), "bad_words": [row[0] for row in words]}
    path = Path(tempfile.gettempdir()) / f"grupo-{group_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        await message.answer_document(FSInputFile(path), caption=f"⚙️ Configuración del grupo {group_id}")
    finally:
        path.unlink(missing_ok=True)


def _target_user_id(message: Message, command: CommandObject) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    try:
        return int((command.args or "").split()[0])
    except (ValueError, IndexError):
        return None


@router.message(Command("descargaslibres"))
async def grant_free_downloads(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_USER_ID:
        await message.reply("🔒 Este comando es exclusivo del dueño del bot.")
        return
    user_id = _target_user_id(message, command)
    if not user_id:
        await message.reply(
            "Responde al mensaje de una persona con <code>/descargaslibres</code> "
            "o usa <code>/descargaslibres ID</code>.", parse_mode="HTML"
        )
        return
    if message.reply_to_message:
        note = (command.args or "").strip()[:200] or None
    else:
        note_parts = (command.args or "").split(maxsplit=1)
        note = note_parts[1][:200] if len(note_parts) > 1 else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO download_exemptions (user_id,granted_by,note,created_at) "
            "VALUES (?,?,?,CURRENT_TIMESTAMP)",
            (user_id, message.from_user.id, note),
        )
        await db.commit()
    await message.reply(
        f"✅ El usuario <code>{user_id}</code> ya tiene descargas libres sin límite de tiempo.",
        parse_mode="HTML",
    )


@router.message(Command("paneldescargas"))
async def downloads_panel_command(message: Message):
    if message.from_user.id != OWNER_USER_ID:
        await message.reply("🔒 Este panel es exclusivo del dueño del bot.")
        return
    await _show_downloads_panel(message)


@router.callback_query(F.data == "downloads:panel")
async def downloads_panel_callback(callback: CallbackQuery):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Panel exclusivo del dueño.", show_alert=True)
        return
    await _show_downloads_panel(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("downloads:policy:"))
async def downloads_policy_callback(callback: CallbackQuery):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Panel exclusivo del dueño.", show_alert=True)
        return
    _, _, maximum, window = callback.data.split(":", 3)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE download_policy SET max_downloads=?,window_seconds=? WHERE id=1",
            (int(maximum), int(window)),
        )
        await db.commit()
    await _show_downloads_panel(callback.message)
    await callback.answer("✅ Límite actualizado")


@router.callback_query(F.data.startswith("downloads:revoke:"))
async def downloads_revoke_callback(callback: CallbackQuery):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Panel exclusivo del dueño.", show_alert=True)
        return
    user_id = int(callback.data.rsplit(":", 1)[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM download_exemptions WHERE user_id=?", (user_id,))
        await db.commit()
    await _show_downloads_panel(callback.message)
    await callback.answer("✅ Acceso libre retirado")


@router.callback_query(F.data == "downloads:addhelp")
async def downloads_add_help(callback: CallbackQuery):
    if callback.from_user.id != OWNER_USER_ID:
        await callback.answer("Panel exclusivo del dueño.", show_alert=True)
        return
    await callback.answer(
        "Responde al usuario con /descargaslibres o usa /descargaslibres ID nota",
        show_alert=True,
    )


@router.message(Command("quitarlibre"))
async def revoke_free_downloads(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_USER_ID:
        await message.reply("🔒 Este comando es exclusivo del dueño del bot.")
        return
    user_id = _target_user_id(message, command)
    if not user_id:
        await message.reply("Responde al usuario con <code>/quitarlibre</code> o usa <code>/quitarlibre ID</code>.", parse_mode="HTML")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM download_exemptions WHERE user_id=?", (user_id,))
        await db.commit()
    if cursor.rowcount:
        await message.reply(f"✅ Se quitó el acceso libre a <code>{user_id}</code>.", parse_mode="HTML")
    else:
        await message.reply("ℹ️ Ese usuario no estaba en la lista libre.")


@router.message(Command("usuarioslibres"))
async def list_free_downloads(message: Message):
    if message.from_user.id != OWNER_USER_ID:
        await message.reply("🔒 Este comando es exclusivo del dueño del bot.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT user_id,note,created_at FROM download_exemptions ORDER BY created_at DESC"
        )).fetchall()
    if not rows:
        await message.reply("📭 No hay usuarios con descargas libres.")
        return
    lines = ["♾ <b>Usuarios con descargas libres</b>", ""]
    for user_id, note, created_at in rows[:50]:
        detail = f" — {html.escape(note)}" if note else ""
        lines.append(f"• <code>{user_id}</code>{detail} · {created_at}")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(Command("misdescargas"))
async def my_download_access(message: Message):
    if message.from_user.id == OWNER_USER_ID:
        await message.reply(
            "👑 <b>Cuenta del dueño</b>\n\nTienes descargas ilimitadas permanentemente.",
            parse_mode="HTML",
        )
        return
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT note,created_at FROM download_exemptions WHERE user_id=?", (message.from_user.id,)
        )).fetchone()
    if row:
        note = f"\n📝 {html.escape(row[0])}" if row[0] else ""
        await message.reply(
            f"♾ <b>Tienes descargas libres</b>\n\nNo se aplica el límite de 3 cada 10 minutos.{note}",
            parse_mode="HTML",
        )
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            policy = await (await db.execute(
                "SELECT max_downloads,window_seconds FROM download_policy WHERE id=1"
            )).fetchone()
        maximum, window = policy or (3, 600)
        await message.reply(
            f"🚦 Tu límite actual es de {maximum} descargas cada {max(1, window // 60)} minutos."
        )


def _validate_restore(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La base está dañada.")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "group_settings" not in tables:
            raise ValueError("No parece una copia válida de NEXORA ONE.")
    finally:
        connection.close()


@router.message(Command("restaurar"))
async def prepare_restore(message: Message):
    if not await require_owner(message):
        return
    if remote_enabled():
        await message.reply("🛑 En Turso la restauración requiere mantenimiento con bot y web pausados. No se reemplazan archivos locales. Conserva el respaldo y solicita la restauración al dueño.")
        return
    document = message.reply_to_message.document if message.reply_to_message else None
    if not document or not (document.file_name or "").endswith(".db"):
        await message.reply("Responde a una copia <code>.db</code> con <code>/restaurar</code>.", parse_mode="HTML")
        return
    if document.file_size and document.file_size > 100 * 1024 * 1024:
        await message.reply("❌ La copia supera el límite seguro de 100 MB.")
        return
    path = Path(tempfile.gettempdir()) / f"restore-{secrets.token_hex(6)}.db"
    await message.bot.download(document, destination=path)
    try:
        await asyncio.to_thread(_validate_restore, path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        await message.reply(f"❌ Copia rechazada: {exc}")
        return
    token = secrets.token_hex(5)
    PENDING_RESTORES[token] = {"path": path, "user_id": message.from_user.id}
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Confirmar restauración", callback_data=f"restore:yes:{token}")
    keyboard.button(text="❌ Cancelar", callback_data=f"restore:no:{token}")
    keyboard.adjust(1)
    await message.reply(
        "⚠️ La copia es válida. Se guardará primero el estado actual. ¿Confirmas la restauración?",
        reply_markup=keyboard.as_markup(),
    )


@router.callback_query(F.data.startswith("restore:"))
async def restore_callback(callback: CallbackQuery):
    if remote_enabled():
        await callback.answer("Restauración remota: requiere mantenimiento con ambos servicios pausados.", show_alert=True)
        return
    _, action, token = callback.data.split(":", 2)
    pending = PENDING_RESTORES.pop(token, None)
    if not pending or pending["user_id"] != callback.from_user.id or not await is_owner(callback.bot, callback.from_user.id):
        await callback.answer("Solicitud vencida o no autorizada.", show_alert=True)
        return
    path = pending["path"]
    if action == "no":
        path.unlink(missing_ok=True)
        await callback.message.edit_text("✅ Restauración cancelada.")
        await callback.answer()
        return
    await run_backup(callback.bot)
    await asyncio.to_thread(os.replace, path, DB_PATH)
    await callback.message.edit_text("✅ Base restaurada. Reinicia el servicio en Northflank para aplicar todo limpiamente.")
    await callback.answer("Restauración completada")
