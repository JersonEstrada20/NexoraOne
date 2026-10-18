import re
from datetime import datetime, time as clock_time
from zoneinfo import ZoneInfo

from nexora import async_db as aiosqlite

from app.config import DB_PATH


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9_áéíóúñ-]", "", (value or "").lower().lstrip("/"))[:32]


async def upsert_text(table: str, chat_id: int, name: str, content: str, user_id: int):
    if table not in {"group_notes", "custom_commands"}:
        raise ValueError("Tabla no permitida")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"""INSERT INTO {table}(chat_id,name,content,created_by) VALUES(?,?,?,?)
            ON CONFLICT(chat_id,name) DO UPDATE SET content=excluded.content,
            created_by=excluded.created_by,created_at=CURRENT_TIMESTAMP""",
            (chat_id, name, content, user_id),
        )
        await db.commit()


async def get_text(table: str, chat_id: int, name: str):
    if table not in {"group_notes", "custom_commands"}:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            f"SELECT content FROM {table} WHERE chat_id=? AND name=?", (chat_id, name)
        )).fetchone()
    return row[0] if row else None


async def list_names(table: str, chat_id: int):
    if table not in {"group_notes", "custom_commands"}:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            f"SELECT name FROM {table} WHERE chat_id=? ORDER BY name", (chat_id,)
        )).fetchall()
    return [row[0] for row in rows]


async def delete_text(table: str, chat_id: int, name: str) -> bool:
    if table not in {"group_notes", "custom_commands"}:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(f"DELETE FROM {table} WHERE chat_id=? AND name=?", (chat_id, name))
        await db.commit()
    return cursor.rowcount > 0


async def set_lock(chat_id: int, content_type: str, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        if enabled:
            await db.execute("INSERT OR IGNORE INTO content_locks VALUES(?,?)", (chat_id, content_type))
        else:
            await db.execute("DELETE FROM content_locks WHERE chat_id=? AND content_type=?", (chat_id, content_type))
        await db.commit()


async def get_locks(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute("SELECT content_type FROM content_locks WHERE chat_id=?", (chat_id,))).fetchall()
    return {row[0] for row in rows}


async def set_whitelist(table: str, chat_id: int, value, enabled: bool):
    column = "domain" if table == "link_whitelist" else "user_id"
    if table not in {"link_whitelist", "user_whitelist"}:
        raise ValueError("Tabla no permitida")
    async with aiosqlite.connect(DB_PATH) as db:
        if enabled:
            await db.execute(f"INSERT OR IGNORE INTO {table}(chat_id,{column}) VALUES(?,?)", (chat_id, value))
        else:
            await db.execute(f"DELETE FROM {table} WHERE chat_id=? AND {column}=?", (chat_id, value))
        await db.commit()


async def list_whitelist(table: str, chat_id: int):
    column = "domain" if table == "link_whitelist" else "user_id"
    if table not in {"link_whitelist", "user_whitelist"}:
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(f"SELECT {column} FROM {table} WHERE chat_id=? ORDER BY {column}", (chat_id,))).fetchall()
    return [row[0] for row in rows]


async def is_user_whitelisted(chat_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("SELECT 1 FROM user_whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
    return bool(row)


async def has_allowed_link(chat_id: int, text: str) -> bool:
    domains = await list_whitelist("link_whitelist", chat_id)
    lowered = (text or "").lower()
    for domain in domains:
        clean = str(domain).lower().removeprefix("www.")
        if clean and clean in lowered:
            return True
    return False


async def upsert_filter(chat_id: int, trigger: str, match_type: str, response: str, user_id: int):
    trigger = " ".join((trigger or "").casefold().split())
    if match_type not in {"contains", "exact", "prefix"} or not trigger:
        raise ValueError("Filtro inválido")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO group_filters(chat_id,trigger,match_type,response,created_by)
            VALUES(?,?,?,?,?) ON CONFLICT(chat_id,trigger,match_type) DO UPDATE SET
            response=excluded.response,created_by=excluded.created_by,created_at=CURRENT_TIMESTAMP""",
            (chat_id, trigger, match_type, response, user_id),
        )
        await db.commit()


async def list_filters(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT trigger,match_type,response FROM group_filters WHERE chat_id=? ORDER BY trigger,match_type",
            (chat_id,),
        )).fetchall()
    return rows


async def delete_filter(chat_id: int, trigger: str) -> int:
    trigger = " ".join((trigger or "").casefold().split())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM group_filters WHERE chat_id=? AND trigger=?", (chat_id, trigger))
        await db.commit()
    return cursor.rowcount


async def find_filter(chat_id: int, text: str):
    normalized = " ".join((text or "").casefold().split())
    if not normalized:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT trigger,match_type,response FROM group_filters WHERE chat_id=? ORDER BY length(trigger) DESC,trigger",
            (chat_id,),
        )).fetchall()
    for trigger, match_type, response in rows:
        matched = (
            normalized == trigger if match_type == "exact"
            else normalized.startswith(trigger) if match_type == "prefix"
            else trigger in normalized
        )
        if matched:
            return trigger, match_type, response
    return None


def night_mode_active(settings: dict, now: datetime | None = None) -> bool:
    if not settings.get("night_mode_enabled"):
        return False
    try:
        zone = ZoneInfo(settings.get("night_mode_timezone") or "America/Santiago")
        start = clock_time.fromisoformat(settings.get("night_mode_start") or "22:00")
        end = clock_time.fromisoformat(settings.get("night_mode_end") or "07:00")
    except (ValueError, TypeError):
        return False
    if start == end:
        return False
    current = (now or datetime.now(zone)).astimezone(zone).time().replace(tzinfo=None)
    if start < end:
        return start <= current < end
    return current >= start or current < end
