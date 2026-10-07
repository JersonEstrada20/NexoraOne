"""Read-only deployment preflight. Never starts polling or prints secrets."""
import asyncio
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

from dotenv import load_dotenv
from aiogram import Bot
import aiohttp


async def check():
    missing = [key for key in (
        'BOT_TOKEN', 'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN',
        'NEXORA_API_BASE', 'NEXORA_INTERNAL_API_KEY', 'NEXORA_PANEL_USER',
        'NEXORA_PANEL_PASSWORD', 'NEXORA_PANEL_SECRET',
    ) if not os.getenv(key, '').strip()]
    for key in missing:
        print('Falta: ' + key)
    ok = not missing
    token = os.getenv('BOT_TOKEN', '').strip()
    if token:
        bot = None
        try:
            bot = Bot(token)
            me = await bot.get_me()
            matches = str(me.username).lower() == 'nexoraonerobot'
            print('Bot: @' + str(me.username))
            print('Identidad correcta: ' + str(matches))
            ok = ok and matches
        except Exception as exc:
            print('Telegram no verificado: ' + type(exc).__name__)
            ok = False
        finally:
            if bot:
                await bot.session.close()
    base = os.getenv('NEXORA_API_BASE', '').strip().rstrip('/')
    if base:
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            print('NEXORA_API_BASE debe ser una URL HTTPS sin credenciales ni parámetros.')
            return 1
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
                async with session.get(base + '/health', allow_redirects=False) as response:
                    healthy = response.status == 200
                    print('Web health: ' + str(response.status))
                    ok = ok and healthy
                async with session.get(base + '/tg_info?ID_TG=7454664711', allow_redirects=False) as response:
                    denied = response.status in (401, 403)
                    print('API rechaza acceso anónimo: ' + str(denied))
                    ok = ok and denied
                key = os.getenv('NEXORA_INTERNAL_API_KEY', '')
                if key:
                    async with session.get(base + '/tg_info?ID_TG=7454664711',
                            headers={'X-Internal-Api-Key': key}, allow_redirects=False) as response:
                        print('API autenticada: ' + str(response.status))
                        ok = ok and response.status == 200
        except Exception as exc:
            print('Web no verificada: ' + type(exc).__name__)
            ok = False
    print('Preflight correcto.' if ok else 'Preflight incompleto. No activar el bot.')
    return 0 if ok else 1


if __name__ == '__main__':
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    sys.exit(asyncio.run(check()))
