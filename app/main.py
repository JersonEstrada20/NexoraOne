import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from app.config import BOT_TOKEN
from app.services.database import init_db
from app.handlers.general import router as general_router
from app.handlers.menu import router as menu_router
from app.handlers.admin import router as admin_router
from app.handlers.moderation import router as moderation_router
from app.handlers.media import router as media_router
from app.handlers.media import media_cleanup_loop
from app.handlers.features import router as features_router
from app.handlers.maintenance import router as maintenance_router
from app.handlers.suggestions import router as suggestions_router
from app.handlers.group_tools import router as group_tools_router
from app.handlers.community import router as community_router, giveaway_recovery_loop
from app.handlers.automation import router as automation_router, scheduled_messages_loop, weekly_stats_loop
from app.handlers.config_transfer import router as config_transfer_router
from app.services.backups import backup_loop
from app.services.diagnostics import database_check, diagnostics_loop
from app.services.access import RequiredChannelMiddleware
from app.services.cleanup import CommandCleanupMiddleware
from app.services.user_directory import init_directory, UserDirectoryMiddleware
from app.handlers.improvements import router as improvements_router
from app.handlers.unified import router as unified_router
from nexora.runtime import runtime
from app.handlers.global_bans import router as global_bans_router
from app.services.bans import init_bans, BanMiddleware

logging.basicConfig(level=logging.INFO)


async def main():
    if not BOT_TOKEN:
        raise ValueError("Falta BOT_TOKEN en el archivo .env")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(BanMiddleware())
    dp.message.outer_middleware(UserDirectoryMiddleware())
    dp.message.outer_middleware(CommandCleanupMiddleware())

    media_router.message.middleware(RequiredChannelMiddleware())
    media_router.callback_query.middleware(RequiredChannelMiddleware())
    features_router.message.middleware(RequiredChannelMiddleware())
    features_router.callback_query.middleware(RequiredChannelMiddleware())

    dp.include_router(global_bans_router)
    dp.include_router(unified_router)
    dp.include_router(improvements_router)
    dp.include_router(maintenance_router)
    dp.include_router(suggestions_router)
    dp.include_router(general_router)
    dp.include_router(menu_router)
    dp.include_router(admin_router)
    dp.include_router(media_router)
    dp.include_router(features_router)
    dp.include_router(community_router)
    dp.include_router(automation_router)
    dp.include_router(config_transfer_router)
    dp.include_router(group_tools_router)
    # El moderador incluye un manejador genérico y debe quedar al final.
    dp.include_router(moderation_router)

    await init_db()
    await init_bans()
    await init_directory()
    # Verificar la integridad antes de empezar el polling: así un volumen
    # desmontado o una base dañada se detectan en el despliegue y no después
    # de que los usuarios ya hayan enviado comandos.
    db_health = await asyncio.to_thread(database_check)
    if db_health != "ok":
        raise RuntimeError(f"La base de datos no pasó la comprobación inicial: {db_health}")
    logging.info("Comprobación inicial correcta: base de datos íntegra")
    await bot.set_my_commands([
        BotCommand(command="menu", description="Abrir todos los comandos del bot"),
    ])

    print("Bot iniciado correctamente...")
    asyncio.create_task(backup_loop(bot))
    asyncio.create_task(diagnostics_loop(bot))
    asyncio.create_task(media_cleanup_loop())
    asyncio.create_task(giveaway_recovery_loop(bot))
    asyncio.create_task(scheduled_messages_loop(bot))
    asyncio.create_task(weekly_stats_loop(bot))
    try:
        await runtime.start(BOT_TOKEN)
        await dp.start_polling(bot)
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
