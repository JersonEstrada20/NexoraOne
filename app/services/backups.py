import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from aiogram.types import FSInputFile, BufferedInputFile

from app.config import BACKUP_CHAT_ID, DB_PATH
from nexora.db import snapshot, remote_enabled

BACKUP_DIR = Path(DB_PATH).resolve().parent / "backups"


def _create_backup() -> tuple[Path, Path]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = BACKUP_DIR / f"doxertube-{datetime.now():%Y%m%d-%H%M%S}.db"
    snapshot(DB_PATH, destination)

    index_path = destination.with_suffix(".groups.json")
    index_db = sqlite3.connect(destination)
    index_db.row_factory = sqlite3.Row
    try:
        rows = index_db.execute(
            "SELECT * FROM group_settings ORDER BY chat_id"
        ).fetchall()
        groups = {str(row["chat_id"]): dict(row) for row in rows}
    finally:
        index_db.close()
    index_path.write_text(
        json.dumps({"created_at": datetime.now().isoformat(), "groups": groups},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    backups = sorted(BACKUP_DIR.glob("doxertube-*.db"), key=lambda path: path.stat().st_mtime)
    for old in backups[:-7]:
        old.with_suffix(".groups.json").unlink(missing_ok=True)
        old.unlink(missing_ok=True)
    return destination, index_path


async def run_backup(bot):
    path, index_path = await asyncio.to_thread(_create_backup)
    if BACKUP_CHAT_ID:
        await bot.send_document(
            BACKUP_CHAT_ID, FSInputFile(path),
            caption="🗄 Copia completa y privada de NEXORA ONE."
        )
        await bot.send_document(
            BACKUP_CHAT_ID, FSInputFile(index_path),
            caption="🔎 Índice de configuraciones. Busca aquí el ID del grupo."
        )
        from nexora.comandos.utils import API_BASE, INTERNAL_API_KEY
        if API_BASE and not remote_enabled():
            import aiohttp
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=90)) as session:
                async with session.get(API_BASE + "/internal/db-backup.zip", headers={"X-Internal-Api-Key": INTERNAL_API_KEY}) as response:
                    response.raise_for_status()
                    archive = await response.read()
            if not archive.startswith(b"PK"):
                raise RuntimeError("El respaldo de servicios no es un ZIP válido")
            await bot.send_document(BACKUP_CHAT_ID, BufferedInputFile(archive, filename="nexora-servicios.zip"), caption="🔐 Respaldo privado de cuentas, créditos y servicios. No compartir.")
    return path


async def backup_loop(bot):
    await asyncio.sleep(60)
    while True:
        try:
            await run_backup(bot)
        except Exception:
            logging.exception("No se pudo crear o enviar la copia automática")
        await asyncio.sleep(24 * 60 * 60)
