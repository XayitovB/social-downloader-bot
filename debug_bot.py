#!/usr/bin/env python3
"""Debug bot startup and handlers"""

import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
try:
    from aiogram.client.default import DefaultBotProperties
except ImportError:
    DefaultBotProperties = None
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger
from config import Config
from db.database import Database
from userbot.client import DownloaderUserbot
from bot.handlers import router

async def debug_bot():
    """Debug bot setup"""
    # Setup logging
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")
    
    logger.info("=== DEBUG BOT STARTUP ===")
    
    # Check config
    logger.info(f"Bot token length: {len(Config.BOT_TOKEN)}")
    logger.info(f"Storage channel: {Config.STORAGE_CHANNEL_ID}")
    
    # Initialize database
    db = Database(Config.DATABASE_PATH)
    await db.init_db()
    
    # Check handlers in router
    logger.info(f"Router observers: {len(router.observers)}")
    
    # Initialize bot  
    if DefaultBotProperties:
        bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
    else:
        bot = Bot(token=Config.BOT_TOKEN, parse_mode=ParseMode.HTML)
    
    # Get bot info
    me = await bot.get_me()
    logger.info(f"Bot info: @{me.username} (ID: {me.id})")
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(debug_bot())
