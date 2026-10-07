"""Small panel images stored in the database, not Northflank's ephemeral disk."""
import io
from contextlib import closing
from PIL import Image
from nexora.db import connect
from nexora.storage import db_path

MAX_IMAGE_BYTES = 512 * 1024


def init_assets():
    with closing(connect(db_path("multiplataforma.db"))) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS nexora_assets(name TEXT PRIMARY KEY, mime TEXT NOT NULL, content BLOB NOT NULL)")
        conn.commit()


def put_image(name, content):
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen debe pesar como máximo 512 KB.")
    try:
        with Image.open(io.BytesIO(content)) as picture:
            mime = Image.MIME.get(picture.format)
            if picture.width * picture.height > 16_000_000 or mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
                raise ValueError("Formato o dimensiones no admitidos.")
            picture.verify()
    except Exception:
        raise ValueError("No es una imagen válida o es demasiado grande.") from None
    with closing(connect(db_path("multiplataforma.db"))) as conn:
        conn.execute("INSERT INTO nexora_assets(name,mime,content) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET mime=excluded.mime,content=excluded.content", (name, mime, content))
        conn.commit()


def get_image(name):
    with closing(connect(db_path("multiplataforma.db"))) as conn:
        return conn.execute("SELECT mime,content FROM nexora_assets WHERE name=?", (name,)).fetchone()
