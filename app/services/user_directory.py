from nexora import async_db as aiosqlite
from aiogram import BaseMiddleware
from app.config import DB_PATH


async def init_directory():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS known_usernames (user_id INTEGER PRIMARY KEY, username TEXT)")
        await db.commit()


class UserDirectoryMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        users = [getattr(event, "from_user", None)]
        users.extend(getattr(event, "new_chat_members", None) or [])
        reply = getattr(event, "reply_to_message", None)
        users.append(getattr(reply, "from_user", None))
        async with aiosqlite.connect(DB_PATH) as db:
            for user in users:
                if user and not user.is_bot:
                    await db.execute("INSERT OR REPLACE INTO known_usernames VALUES (?, ?)",
                                     (user.id, (user.username or "").lower()))
            await db.commit()
        return await handler(event, data)


async def resolve_username(bot, chat_id, username):
    name = username.lstrip("@").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM known_usernames WHERE username = ?", (name,)) as cursor:
            rows = await cursor.fetchall()
    for (user_id,) in rows:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except Exception:
            continue
        # Revalidate the alias so a renamed account is never banned by mistake.
        if (member.user.username or "").lower() == name:
            return user_id
    return None
