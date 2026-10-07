from nexora import async_db as aiosqlite
from nexora.db import initialized_remote
import asyncio
from app.config import (
    DB_PATH,
    DEFAULT_WARN_LIMIT,
    DEFAULT_AUTO_MUTE_MINUTES,
    DEFAULT_FLOOD_MAX_MESSAGES,
    DEFAULT_FLOOD_WINDOW_SECONDS,
    DEFAULT_RULES_TEXT,
)


async def init_db():
    if await asyncio.to_thread(initialized_remote):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            anti_link INTEGER DEFAULT 1,
            welcome_text TEXT DEFAULT '🎉 Bienvenido/a, {name} al grupo.',
            rules_text TEXT DEFAULT '📜 Aún no se han configurado las reglas del grupo.',
            antiflood INTEGER DEFAULT 1,
            captcha_enabled INTEGER DEFAULT 1,
            warn_limit INTEGER DEFAULT 3,
            auto_mute_minutes INTEGER DEFAULT 60,
            flood_max_messages INTEGER DEFAULT 5,
            flood_window_seconds INTEGER DEFAULT 10,
            farewell_enabled INTEGER DEFAULT 0,
            farewell_text TEXT DEFAULT '👋 {name} salió del grupo.',
            progressive_sanctions INTEGER DEFAULT 1,
            mention_limit INTEGER DEFAULT 5,
            log_chat_id INTEGER,
            welcome_media_id TEXT,
            welcome_media_type TEXT,
            slow_mode_seconds INTEGER DEFAULT 0,
            approval_enabled INTEGER DEFAULT 0,
            weekly_stats_enabled INTEGER DEFAULT 0,
            required_channel TEXT,
            auto_delete_seconds INTEGER DEFAULT 0,
            language TEXT DEFAULT 'es'
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS bad_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            word TEXT NOT NULL
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            warns INTEGER DEFAULT 0,
            UNIQUE(chat_id, user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS action_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER,
            admin_id INTEGER,
            action TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS captcha_challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            verified INTEGER DEFAULT 0,
            UNIQUE(chat_id, user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            reporter_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            target_message_text TEXT,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_by INTEGER,
            closed_at TIMESTAMP
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS staff_aliases (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS staff_roles (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role_name TEXT NOT NULL,
            PRIMARY KEY (chat_id, user_id)
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_by INTEGER,
            closed_at TIMESTAMP
        )
        """)
        await db.execute("""CREATE TABLE IF NOT EXISTS case_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            case_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL, text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")

        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN antiflood INTEGER DEFAULT 1")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN captcha_enabled INTEGER DEFAULT 1")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN warn_limit INTEGER DEFAULT 3")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN auto_mute_minutes INTEGER DEFAULT 60")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN flood_max_messages INTEGER DEFAULT 5")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN flood_window_seconds INTEGER DEFAULT 10")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN rules_text TEXT DEFAULT '📜 Aún no se han configurado las reglas del grupo.'")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN farewell_enabled INTEGER DEFAULT 0")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN farewell_text TEXT DEFAULT '👋 {name} salió del grupo.'")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN progressive_sanctions INTEGER DEFAULT 1")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN mention_limit INTEGER DEFAULT 5")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN log_chat_id INTEGER")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN welcome_media_id TEXT")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN welcome_media_type TEXT")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN slow_mode_seconds INTEGER DEFAULT 0")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN approval_enabled INTEGER DEFAULT 0")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN weekly_stats_enabled INTEGER DEFAULT 0")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN required_channel TEXT")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN auto_delete_seconds INTEGER DEFAULT 0")
        await _run_safe_alter(db, "ALTER TABLE group_settings ADD COLUMN language TEXT DEFAULT 'es'")
        await db.execute("""CREATE TABLE IF NOT EXISTS rules_acceptance (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, user_id))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_chat_id INTEGER NOT NULL,
            source_title TEXT,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS download_exemptions (
            user_id INTEGER PRIMARY KEY,
            granted_by INTEGER NOT NULL,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS download_policy (
            id INTEGER PRIMARY KEY CHECK(id=1),
            max_downloads INTEGER NOT NULL DEFAULT 3,
            window_seconds INTEGER NOT NULL DEFAULT 600,
            parallel_downloads INTEGER NOT NULL DEFAULT 3
        )""")
        await db.execute("""INSERT OR IGNORE INTO download_policy
            (id,max_downloads,window_seconds,parallel_downloads) VALUES(1,3,600,3)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS economy_missions (
            user_id INTEGER NOT NULL, period TEXT NOT NULL, mission_key TEXT NOT NULL,
            period_key TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
            claimed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, period, mission_key, period_key))""")
        await db.execute("""CREATE TABLE IF NOT EXISTS group_notes (
            chat_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
            created_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, name)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS custom_commands (
            chat_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
            created_by INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, name)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS content_locks (
            chat_id INTEGER NOT NULL, content_type TEXT NOT NULL,
            PRIMARY KEY(chat_id, content_type)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS link_whitelist (
            chat_id INTEGER NOT NULL, domain TEXT NOT NULL,
            PRIMARY KEY(chat_id, domain)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_whitelist (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            PRIMARY KEY(chat_id, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS group_activity (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            messages INTEGER DEFAULT 0, last_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS group_activity_daily (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, activity_date TEXT NOT NULL,
            messages INTEGER DEFAULT 0, PRIMARY KEY(chat_id,user_id,activity_date)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
            message_id INTEGER, prize TEXT NOT NULL, created_by INTEGER NOT NULL,
            ends_at TEXT NOT NULL, status TEXT DEFAULT 'open', winner_id INTEGER
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(giveaway_id, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS level_roles (
            chat_id INTEGER NOT NULL, level INTEGER NOT NULL, role_name TEXT NOT NULL,
            PRIMARY KEY(chat_id, level)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS activity_levels (
            chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, announced_level INTEGER DEFAULT 1,
            PRIMARY KEY(chat_id, user_id)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS scheduled_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
            text TEXT NOT NULL, next_run TEXT NOT NULL, repeat_seconds INTEGER,
            created_by INTEGER NOT NULL, enabled INTEGER DEFAULT 1
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS weekly_stats_sent (
            chat_id INTEGER NOT NULL, year_week TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(chat_id, year_week)
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS media_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            query TEXT NOT NULL, media_type TEXT NOT NULL, quality TEXT,
            title TEXT, document INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id,query,media_type,quality,document)
        )""")
        await _run_safe_alter(db, "ALTER TABLE download_history ADD COLUMN document INTEGER DEFAULT 0")

        await db.commit()


async def _run_safe_alter(db, sql: str):
    try:
        await db.execute(sql)
    except aiosqlite.OperationalError as exc:
        if "duplicate column name" in str(exc).lower():
            return
        if "download_history" in sql and "no such table" in str(exc).lower():
            return  # Created lazily by media on a fresh database.
        raise


async def ensure_group(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO group_settings (
                chat_id,
                anti_link,
                welcome_text,
                rules_text,
                antiflood,
                captcha_enabled,
                warn_limit,
                auto_mute_minutes,
                flood_max_messages,
                flood_window_seconds
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat_id,
            1,
            '🎉 Bienvenido/a, {name} al grupo.',
            DEFAULT_RULES_TEXT,
            1,
            1,
            DEFAULT_WARN_LIMIT,
            DEFAULT_AUTO_MUTE_MINUTES,
            DEFAULT_FLOOD_MAX_MESSAGES,
            DEFAULT_FLOOD_WINDOW_SECONDS
        ))
        await db.commit()


async def get_settings(chat_id: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT
                anti_link,
                welcome_text,
                rules_text,
                antiflood,
                captcha_enabled,
                warn_limit,
                auto_mute_minutes,
                flood_max_messages,
                flood_window_seconds,
                farewell_enabled,
                farewell_text,
                progressive_sanctions,
                mention_limit,
                log_chat_id,
                welcome_media_id,
                welcome_media_type,
                slow_mode_seconds,
                approval_enabled,
                weekly_stats_enabled,
                required_channel,
                auto_delete_seconds,
                language
            FROM group_settings
            WHERE chat_id = ?
        """, (chat_id,))
        row = await cursor.fetchone()

        return {
            "anti_link": bool(row[0]),
            "welcome_text": row[1],
            "rules_text": row[2],
            "antiflood": bool(row[3]),
            "captcha_enabled": bool(row[4]),
            "warn_limit": int(row[5]),
            "auto_mute_minutes": int(row[6]),
            "flood_max_messages": int(row[7]),
            "flood_window_seconds": int(row[8]),
            "farewell_enabled": bool(row[9]),
            "farewell_text": row[10],
            "progressive_sanctions": bool(row[11]),
            "mention_limit": int(row[12]),
            "log_chat_id": row[13],
            "welcome_media_id": row[14],
            "welcome_media_type": row[15],
            "slow_mode_seconds": int(row[16] or 0),
            "approval_enabled": bool(row[17]),
            "weekly_stats_enabled": bool(row[18]),
            "required_channel": row[19],
            "auto_delete_seconds": int(row[20] or 0),
            "language": row[21] or "es",
        }


async def set_slow_mode(chat_id: int, seconds: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET slow_mode_seconds=? WHERE chat_id=?", (seconds, chat_id))
        await db.commit()


async def set_approval_enabled(chat_id: int, enabled: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET approval_enabled=? WHERE chat_id=?", (1 if enabled else 0, chat_id))
        await db.commit()


async def set_weekly_stats_enabled(chat_id: int, enabled: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET weekly_stats_enabled=? WHERE chat_id=?", (1 if enabled else 0, chat_id)); await db.commit()


async def set_required_channel(chat_id: int, channel: str | None):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET required_channel=? WHERE chat_id=?", (channel, chat_id)); await db.commit()


async def set_auto_delete_seconds(chat_id: int, seconds: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET auto_delete_seconds=? WHERE chat_id=?", (seconds, chat_id)); await db.commit()


async def set_language(chat_id: int, language: str):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET language=? WHERE chat_id=?", (language, chat_id)); await db.commit()


async def set_anti_link(chat_id: int, value: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET anti_link = ? WHERE chat_id = ?",
            (1 if value else 0, chat_id)
        )
        await db.commit()


async def set_antiflood(chat_id: int, value: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET antiflood = ? WHERE chat_id = ?",
            (1 if value else 0, chat_id)
        )
        await db.commit()


async def set_captcha_enabled(chat_id: int, value: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET captcha_enabled = ? WHERE chat_id = ?",
            (1 if value else 0, chat_id)
        )
        await db.commit()


async def set_warn_limit(chat_id: int, value: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET warn_limit = ? WHERE chat_id = ?",
            (value, chat_id)
        )
        await db.commit()


async def set_auto_mute_minutes(chat_id: int, value: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET auto_mute_minutes = ? WHERE chat_id = ?",
            (value, chat_id)
        )
        await db.commit()


async def set_flood_limit(chat_id: int, max_messages: int, window_seconds: int):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE group_settings
            SET flood_max_messages = ?, flood_window_seconds = ?
            WHERE chat_id = ?
        """, (max_messages, window_seconds, chat_id))
        await db.commit()


async def set_welcome_text(chat_id: int, text: str):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET welcome_text = ? WHERE chat_id = ?",
            (text, chat_id)
        )
        await db.commit()


async def set_rules_text(chat_id: int, text: str):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_settings SET rules_text = ? WHERE chat_id = ?",
            (text, chat_id)
        )
        await db.commit()


async def add_bad_word(chat_id: int, word: str):
    word = word.strip().lower()
    if not word:
        return False

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM bad_words WHERE chat_id = ? AND word = ? LIMIT 1",
            (chat_id, word)
        )
        exists = await cursor.fetchone()
        if exists:
            return False

        await db.execute(
            "INSERT INTO bad_words (chat_id, word) VALUES (?, ?)",
            (chat_id, word)
        )
        await db.commit()


async def set_farewell(chat_id: int, text: str | None = None, enabled: bool | None = None):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        if text is not None:
            await db.execute("UPDATE group_settings SET farewell_text=? WHERE chat_id=?", (text, chat_id))
        if enabled is not None:
            await db.execute("UPDATE group_settings SET farewell_enabled=? WHERE chat_id=?", (1 if enabled else 0, chat_id))
        await db.commit()


async def accept_rules(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO rules_acceptance(chat_id,user_id) VALUES(?,?)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET accepted_at=CURRENT_TIMESTAMP""", (chat_id, user_id))
        await db.commit()


async def set_progressive_sanctions(chat_id: int, enabled: bool):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET progressive_sanctions=? WHERE chat_id=?",
                         (1 if enabled else 0, chat_id))
        await db.commit()


async def set_log_chat(chat_id: int, log_chat_id: int | None):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET log_chat_id=? WHERE chat_id=?", (log_chat_id, chat_id))
        await db.commit()


async def set_welcome_media(chat_id: int, file_id: str | None, media_type: str | None):
    await ensure_group(chat_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE group_settings SET welcome_media_id=?,welcome_media_type=? WHERE chat_id=?",
                         (file_id, media_type, chat_id))
        await db.commit()


async def get_log_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await (await db.execute(
            "SELECT DISTINCT log_chat_id FROM group_settings WHERE log_chat_id IS NOT NULL"
        )).fetchall()
        return [row[0] for row in rows]
        return True


async def del_bad_word(chat_id: int, word: str):
    word = word.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM bad_words WHERE chat_id = ? AND word = ?",
            (chat_id, word)
        )
        await db.commit()


async def get_bad_words(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT word FROM bad_words WHERE chat_id = ? ORDER BY word ASC",
            (chat_id,)
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]


async def add_warn(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO warnings (chat_id, user_id, warns)
            VALUES (?, ?, 1)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET warns = warns + 1
        """, (chat_id, user_id))
        await db.commit()

        cursor = await db.execute(
            "SELECT warns FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0]


async def remove_warn(chat_id: int, user_id: int):
    current = await get_warns(chat_id, user_id)
    if current <= 0:
        return 0

    new_value = current - 1
    async with aiosqlite.connect(DB_PATH) as db:
        if new_value == 0:
            await db.execute(
                "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
        else:
            await db.execute(
                "UPDATE warnings SET warns = ? WHERE chat_id = ? AND user_id = ?",
                (new_value, chat_id, user_id)
            )
        await db.commit()

    return new_value


async def get_warns(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT warns FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def reset_warns(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM warnings WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def get_group_stats(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM bad_words WHERE chat_id = ?",
            (chat_id,)
        )
        bad_words_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM warnings WHERE chat_id = ?",
            (chat_id,)
        )
        warned_users_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM action_logs WHERE chat_id = ?",
            (chat_id,)
        )
        logs_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM reports WHERE chat_id = ? AND status = 'open'",
            (chat_id,)
        )
        open_reports_count = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM tickets WHERE chat_id = ? AND status = 'open'",
            (chat_id,)
        )
        open_tickets_count = (await cursor.fetchone())[0]

        return {
            "bad_words_count": bad_words_count,
            "warned_users_count": warned_users_count,
            "logs_count": logs_count,
            "open_reports_count": open_reports_count,
            "open_tickets_count": open_tickets_count,
        }


async def record_activity(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO group_activity(chat_id,user_id,messages) VALUES(?,?,1)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET messages=messages+1,last_message=CURRENT_TIMESTAMP""",
                         (chat_id, user_id))
        await db.execute("""INSERT INTO group_activity_daily(chat_id,user_id,activity_date,messages)
            VALUES(?,?,DATE('now'),1) ON CONFLICT(chat_id,user_id,activity_date)
            DO UPDATE SET messages=messages+1""", (chat_id, user_id))
        await db.commit()
        row = await (await db.execute(
            "SELECT messages FROM group_activity WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
    return int(row[0])


async def get_activity_ranking(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT user_id,messages FROM group_activity WHERE chat_id=? ORDER BY messages DESC LIMIT ?",
            (chat_id, limit))).fetchall()


async def get_activity_total(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT COALESCE(SUM(messages),0),COUNT(*) FROM group_activity WHERE chat_id=?", (chat_id,))).fetchone()
    return row


async def get_weekly_activity(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute("""SELECT COALESCE(SUM(messages),0),COUNT(DISTINCT user_id)
            FROM group_activity_daily WHERE chat_id=? AND activity_date>=DATE('now','-6 days')""",
            (chat_id,))).fetchone()
    return row


async def set_level_role(chat_id: int, level: int, role_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT INTO level_roles(chat_id,level,role_name) VALUES(?,?,?)
            ON CONFLICT(chat_id,level) DO UPDATE SET role_name=excluded.role_name""", (chat_id, level, role_name))
        await db.commit()


async def delete_level_role(chat_id: int, level: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM level_roles WHERE chat_id=? AND level=?", (chat_id, level)); await db.commit()


async def get_level_roles(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        return await (await db.execute(
            "SELECT level,role_name FROM level_roles WHERE chat_id=? ORDER BY level", (chat_id,))).fetchall()


async def get_activity_profile(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT messages FROM group_activity WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
        messages = int(row[0]) if row else 0
        level = messages // 25 + 1
        role = await (await db.execute(
            "SELECT role_name FROM level_roles WHERE chat_id=? AND level<=? ORDER BY level DESC LIMIT 1",
            (chat_id, level))).fetchone()
    return messages, level, role[0] if role else None


async def mark_level_announced(chat_id: int, user_id: int, level: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        row = await (await db.execute(
            "SELECT announced_level FROM activity_levels WHERE chat_id=? AND user_id=?", (chat_id, user_id))).fetchone()
        previous = int(row[0]) if row else 1
        if level <= previous:
            return False
        await db.execute("""INSERT INTO activity_levels(chat_id,user_id,announced_level) VALUES(?,?,?)
            ON CONFLICT(chat_id,user_id) DO UPDATE SET announced_level=excluded.announced_level""",
                         (chat_id, user_id, level)); await db.commit()
    return True


async def add_log(chat_id: int, action: str, user_id: int | None = None, admin_id: int | None = None, reason: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO action_logs (chat_id, user_id, admin_id, action, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, user_id, admin_id, action, reason))
        await db.commit()


async def get_logs(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, admin_id, action, reason, created_at
            FROM action_logs
            WHERE chat_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))
        return await cursor.fetchall()


async def get_user_logs(chat_id: int, user_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, admin_id, action, reason, created_at
            FROM action_logs
            WHERE chat_id = ? AND user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, user_id, limit))
        return await cursor.fetchall()


async def create_or_update_captcha(chat_id: int, user_id: int, question: str, answer: str, expires_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO captcha_challenges (chat_id, user_id, question, answer, expires_at, verified)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET
                question = excluded.question,
                answer = excluded.answer,
                expires_at = excluded.expires_at,
                verified = 0
        """, (chat_id, user_id, question, answer, expires_at))
        await db.commit()


async def get_captcha(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT question, answer, expires_at, verified
            FROM captcha_challenges
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id))
        row = await cursor.fetchone()
        if not row:
            return None

        return {
            "question": row[0],
            "answer": row[1],
            "expires_at": row[2],
            "verified": bool(row[3]),
        }


async def verify_captcha(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE captcha_challenges
            SET verified = 1
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id))
        await db.commit()


async def delete_captcha(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM captcha_challenges WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def add_report(
    chat_id: int,
    reporter_id: int,
    target_user_id: int,
    target_message_text: str | None,
    reason: str | None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO reports (chat_id, reporter_id, target_user_id, target_message_text, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (chat_id, reporter_id, target_user_id, target_message_text, reason))
        await db.commit()
        return cursor.lastrowid


async def get_open_reports(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, reporter_id, target_user_id, target_message_text, reason, created_at
            FROM reports
            WHERE chat_id = ? AND status = 'open'
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))
        return await cursor.fetchall()


async def close_report(chat_id: int, report_id: int, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE reports
            SET status = 'closed',
                closed_by = ?,
                closed_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND id = ? AND status = 'open'
        """, (admin_id, chat_id, report_id))
        await db.commit()
        return cursor.rowcount > 0


async def set_staff_nickname(chat_id: int, user_id: int, nickname: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO staff_aliases (chat_id, user_id, nickname)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET nickname = excluded.nickname
        """, (chat_id, user_id, nickname))
        await db.commit()


async def remove_staff_nickname(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM staff_aliases WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def get_staff_nickname(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT nickname FROM staff_aliases WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def set_staff_role(chat_id: int, user_id: int, role_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO staff_roles (chat_id, user_id, role_name)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id)
            DO UPDATE SET role_name = excluded.role_name
        """, (chat_id, user_id, role_name))
        await db.commit()


async def remove_staff_role(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM staff_roles WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        await db.commit()


async def get_staff_role(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT role_name FROM staff_roles WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_registered_staff(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT
                sa.user_id,
                sa.nickname,
                sr.role_name
            FROM staff_aliases sa
            LEFT JOIN staff_roles sr
                ON sr.chat_id = sa.chat_id AND sr.user_id = sa.user_id
            WHERE sa.chat_id = ?
            ORDER BY COALESCE(sr.role_name, ''), sa.nickname
        """, (chat_id,))
        return await cursor.fetchall()


async def add_ticket(chat_id: int, user_id: int, reason: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO tickets (chat_id, user_id, reason)
            VALUES (?, ?, ?)
        """, (chat_id, user_id, reason))
        await db.commit()
        return cursor.lastrowid


async def get_open_tickets(chat_id: int, limit: int = 10):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, user_id, reason, created_at
            FROM tickets
            WHERE chat_id = ? AND status = 'open'
            ORDER BY id DESC
            LIMIT ?
        """, (chat_id, limit))
        return await cursor.fetchall()


async def close_ticket(chat_id: int, ticket_id: int, admin_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            UPDATE tickets
            SET status = 'closed',
                closed_by = ?,
                closed_at = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND id = ? AND status = 'open'
        """, (admin_id, chat_id, ticket_id))
        await db.commit()
        return cursor.rowcount > 0
