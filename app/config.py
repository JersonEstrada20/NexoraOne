import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_NAME = "NEXORA ONE"
BOT_USERNAME = "NexoraOneRoBot"
OWNER_USERNAME = "PeruDoxer"
OFFICIAL_ACCOUNT_USERNAME = "OficialNexora"
OFFICIAL_ACCOUNT_ID = 7151644287
OFFICIAL_CHANNEL_USERNAME = "NexoraOneOficial"
OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "7454664711"))
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
_backup_chat_id = os.getenv("BACKUP_CHAT_ID", "-1004334720154").strip()
try:
    BACKUP_CHAT_ID = int(_backup_chat_id) if _backup_chat_id else None
except ValueError:
    BACKUP_CHAT_ID = None

DEFAULT_WARN_LIMIT = 3
DEFAULT_AUTO_MUTE_MINUTES = 60
DEFAULT_FLOOD_MAX_MESSAGES = 5
DEFAULT_FLOOD_WINDOW_SECONDS = 10
DEFAULT_CAPTCHA_TIMEOUT_MINUTES = 5
DEFAULT_RULES_TEXT = "📜 Aún no se han configurado las reglas del grupo."
