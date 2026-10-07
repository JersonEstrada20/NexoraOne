import asyncio
import logging
import shutil
import sqlite3
from nexora.db import connect as db_connect, remote_enabled
from pathlib import Path
from time import monotonic

from app.config import BACKUP_CHAT_ID, DB_PATH

STARTED_AT = monotonic()


def uptime_text() -> str:
    seconds = int(monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def memory_mb() -> float:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except OSError:
        pass
    return 0.0


def database_check() -> str:
    connection = db_connect(DB_PATH)
    try:
        if remote_enabled():
            return "ok" if connection.execute("SELECT 1").fetchone()[0] == 1 else "error"
        return connection.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        connection.close()


def disk_status() -> tuple[int, int]:
    usage = shutil.disk_usage(Path(DB_PATH).resolve().parent)
    return usage.free, usage.total


async def self_test(bot) -> list[str]:
    errors = []
    try:
        await bot.get_me()
    except Exception as exc:
        errors.append(f"Telegram: {exc}")
    try:
        result = await asyncio.to_thread(database_check)
        if result != "ok":
            errors.append(f"Base de datos: {result}")
    except Exception as exc:
        errors.append(f"Base de datos: {exc}")
    try:
        free, _ = await asyncio.to_thread(disk_status)
        if free < 50 * 1024 * 1024:
            errors.append(f"Espacio bajo: {free // 1024 // 1024} MB libres")
    except Exception as exc:
        errors.append(f"Disco: {exc}")
    return errors


async def diagnostics_loop(bot):
    await asyncio.sleep(5 * 60)
    while True:
        errors = await self_test(bot)
        if errors:
            message = "🚨 <b>Autodiagnóstico de NEXORA ONE</b>\n\n" + "\n".join(f"• {error}" for error in errors)
            logging.error("Autodiagnóstico: %s", "; ".join(errors))
            if BACKUP_CHAT_ID:
                try:
                    await bot.send_message(BACKUP_CHAT_ID, message, parse_mode="HTML")
                except Exception:
                    logging.exception("No se pudo enviar la alerta de diagnóstico")
        await asyncio.sleep(24 * 60 * 60)
