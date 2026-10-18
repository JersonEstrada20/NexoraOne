import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_NAME = "NEXORA ONE"
BOT_USERNAME = "NexoraOneRoBot"
OWNER_USERNAME = "PeruDoxer"
OFFICIAL_ACCOUNT_USERNAME = "OficialNexora"
OFFICIAL_CHANNEL_USERNAME = "NexoraOneOficial"


def _positive_ids(value: str | None) -> set[int]:
    return {
        int(item)
        for item in str(value or "").replace(",", " ").split()
        if item.isdigit() and int(item) > 0
    }


_explicit_owner_ids = _positive_ids(os.getenv("OWNER_USER_ID")) or _positive_ids(os.getenv("NEXORA_OWNER_ID"))
if len(_explicit_owner_ids) == 1:
    OWNER_USER_ID = next(iter(_explicit_owner_ids))
else:
    _admin_ids = set().union(*(
        _positive_ids(os.getenv(name))
        for name in ("NEXORA_ADMIN_ID", "SPIDERSYN_ADMIN_ID", "ADMIN_ID")
    ))
    OWNER_USER_ID = next(iter(_admin_ids)) if len(_admin_ids) == 1 else 0
DB_PATH = os.getenv("DB_PATH", "app/data/bot.db")


def _ensure_database_path(path: str) -> str:
    database_path = Path(path).expanduser().resolve()
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        probe = database_path.parent / ".write-test"
        probe.touch(exist_ok=True)
        probe.unlink(missing_ok=True)
        return str(database_path)
    except OSError:
        fallback = Path("/bot/app/data/bot.db")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return str(fallback)


DB_PATH = _ensure_database_path(DB_PATH)
_backup_chat_id = os.getenv("BACKUP_CHAT_ID", "").strip()
try:
    _parsed_backup_chat_id = int(_backup_chat_id) if _backup_chat_id else 0
    BACKUP_CHAT_ID = _parsed_backup_chat_id or None
except ValueError:
    BACKUP_CHAT_ID = None

DEFAULT_WARN_LIMIT = 3
DEFAULT_AUTO_MUTE_MINUTES = 60
DEFAULT_FLOOD_MAX_MESSAGES = 5
DEFAULT_FLOOD_WINDOW_SECONDS = 10
DEFAULT_CAPTCHA_TIMEOUT_MINUTES = 5
DEFAULT_RULES_TEXT = "📜 Aún no se han configurado las reglas del grupo."
