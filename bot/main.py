"""Main bot application using Aiogram."""

import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.enums import ParseMode
try:
    from aiogram.client.default import DefaultBotProperties
except ImportError:
    # For older versions of aiogram
    DefaultBotProperties = None
from aiogram.types import TelegramObject
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
from config import Config
from db.database import Database
from userbot.client import DownloaderUserbot
from bot.handlers import router


class DatabaseMiddleware(BaseMiddleware):
    """Middleware to inject database instance into handlers."""
    
    def __init__(self, database: Database):
        self.database = database
        super().__init__()
    
    async def __call__(self, handler, event: TelegramObject, data: dict):
        data['db'] = self.database
        return await handler(event, data)


class DownloaderUserbotMiddleware(BaseMiddleware):
    """Middleware to inject userbot instance into handlers."""
    
    def __init__(self, userbot: DownloaderUserbot):
        self.userbot = userbot
        super().__init__()
    
    async def __call__(self, handler, event: TelegramObject, data: dict):
        data['userbot'] = self.userbot
        return await handler(event, data)


async def setup_logging():
    """Configure logging."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=Config.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    logger.add(
        "logs/bot.log",
        level=Config.LOG_LEVEL,
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )


async def main():
    """Main application entry point."""
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    # Setup logging
    await setup_logging()
    
    # Validate configuration
    if not Config.validate():
        logger.error("Konfiguratsiya tekshiruvidan o'tmadi. Iltimos, .env faylingizni tekshiring.")
        return
    
    logger.info("Video Yuklovchi Bot ishga tushirilmoqda...")
    
    # Initialize database
    db = Database(Config.DATABASE_PATH)
    await db.init_db()
    
    # Initialize userbot
    userbot = DownloaderUserbot()
    if not await userbot.start():
        logger.error("Userbot ishga tushmadi. Iltimos, yuqoridagi loglarni tekshiring.")
        return
    
    # Clear any previous YouTube callback data
    userbot.format_callbacks.clear()
    userbot.youtube_requests.clear()
    
    # Test userbot connection
    if not await userbot.test_connection():
        logger.error("Userbot ulanish testi muvaffaqiyatsiz tugadi.")
        await userbot.stop()
        return
    
    # Initialize bot
    if DefaultBotProperties:
        bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    else:
        # For older versions of aiogram
        bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    
    # Initialize dispatcher with memory storage for FSM
    dp = Dispatcher(storage=MemoryStorage())
    
    # Add middleware
    dp.message.middleware(DatabaseMiddleware(db))
    dp.inline_query.middleware(DatabaseMiddleware(db))
    dp.callback_query.middleware(DatabaseMiddleware(db))
    dp.message.middleware(DownloaderUserbotMiddleware(userbot))
    dp.callback_query.middleware(DownloaderUserbotMiddleware(userbot))
    
    # Include routers
    dp.include_router(router)
    
    try:
        logger.info("Bot muvaffaqiyatli ishga tushirildi va foydalanuvchi xabarlarini kutmoqda.")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot foydalanuvchi tomonidan to'xtatildi.")
    except Exception as e:
        logger.error(f"Botda kutilmagan xatolik: {e}")
    finally:
        # Cleanup
        await userbot.stop()
        await bot.session.close()
        logger.info("Bot to'liq o'chirildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
