"""Persistent bot bans and recorded global group actions."""
from nexora import async_db as aiosqlite
from aiogram import BaseMiddleware
from app.config import DB_PATH, OWNER_USER_ID

async def init_bans():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS bot_bans(user_id INTEGER PRIMARY KEY, reason TEXT NOT NULL, global_ban INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS global_ban_targets(user_id INTEGER, chat_id INTEGER, PRIMARY KEY(user_id,chat_id));
        CREATE TABLE IF NOT EXISTS known_groups(chat_id INTEGER PRIMARY KEY);
        """)
        await db.commit()

async def banned(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute("SELECT reason,global_ban FROM bot_bans WHERE user_id=?", (user_id,))).fetchone()

async def set_ban(user_id, reason, global_ban=False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO bot_bans VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason,global_ban=max(bot_bans.global_ban,excluded.global_ban)", (user_id,reason,int(global_ban)))
        await db.commit()

async def clear_ban(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bot_bans WHERE user_id=?", (user_id,))
        await db.commit()

async def targets(user_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id is None:
            rows = await (await db.execute("SELECT chat_id FROM known_groups UNION SELECT chat_id FROM group_settings WHERE chat_id<0")).fetchall()
        else:
            rows = await (await db.execute("SELECT chat_id FROM global_ban_targets WHERE user_id=?", (user_id,))).fetchall()
        return [row[0] for row in rows]

async def record(user_id, chat_id, remove=False):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM global_ban_targets WHERE user_id=? AND chat_id=?" if remove else "INSERT OR IGNORE INTO global_ban_targets VALUES(?,?)", (user_id,chat_id))
        await db.commit()

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None) or getattr(getattr(event,"message",None),"chat",None)
        if chat and chat.id < 0:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR IGNORE INTO known_groups VALUES(?)", (chat.id,))
                await db.commit()
        user = getattr(event, "from_user", None)
        if user and user.id != OWNER_USER_ID and await banned(user.id):
            if hasattr(event, "data"):
                await event.answer("Tu acceso al bot está suspendido.", show_alert=True)
            return
        return await handler(event,data)
