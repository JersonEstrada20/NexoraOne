"""Initialize the new unified schema without starting Telegram or a web server.

Run explicitly: python scripts/init_turso.py --initialize
Does not delete existing business data. Credentials never appear in output.
"""
import argparse
import asyncio
import os
import sys
import secrets
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def initialize():
    from app.services.database import init_db
    from app.services.bans import init_bans
    from app.services.user_directory import init_directory
    await init_db()
    await init_bans()
    await init_directory()
    print("Esquema del bot inicializado.", flush=True)
    # Flask's existing startup initializes the five logical service schemas.
    from nexora import web
    print("Esquema de la web inicializado.", flush=True)
    from nexora.comandos.admin_requests import init_db as init_requests
    await asyncio.to_thread(init_requests)
    print("Esquema compartido de solicitudes inicializado.", flush=True)
    from nexora.db import connect, SCHEMA_VERSION
    from contextlib import closing
    with closing(connect("ignored")) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS nexora_schema(version TEXT PRIMARY KEY)")
        conn.execute("INSERT OR IGNORE INTO nexora_schema VALUES(?)", (SCHEMA_VERSION,))
        conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true", required=True)
    parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    os.environ["DATABASE_BACKEND"] = "turso"
    os.environ["NEXORA_INITIALIZE_SCHEMA"] = "1"
    from nexora.db import remote_config
    remote_config()
    # Schema-only process, no HTTP server/cookies. Production still requires its
    # own persistent NEXORA_PANEL_SECRET, checked by nexora.web at startup.
    os.environ.setdefault("NEXORA_PANEL_SECRET", secrets.token_hex(32))
    try:
        asyncio.run(initialize())
    except Exception as exc:
        print("Inicialización incompleta (" + type(exc).__name__ + "). Revisar configuración y pruebas; no desplegar.")
        import traceback
        for frame in traceback.extract_tb(exc.__traceback__):
            print(Path(frame.filename).name + ":" + str(frame.lineno) + " " + frame.name)
        return 1
    print("Inicialización completada. No se inició ningún bot ni servidor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
