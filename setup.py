"""Setup script for initial userbot authentication."""

import asyncio
import sys
import os
import glob

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from loguru import logger
from config import Config
from userbot.client import DownloaderUserbot


def setup_logging():
    """Configure logging for setup."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}"
    )


async def main():
    """Main setup function."""
    setup_logging()
    
    print("=== Instagram Video Botni Sozlash ===\n")
    
    # Validate basic configuration
    if not Config.API_ID or not Config.API_HASH:
        print("❌ API_ID and API_HASH are required in .env file")
        print("Get them from https://my.telegram.org/apps")
        return False
    
    if not Config.BOT_TOKEN:
        print("❌ BOT_TOKEN is required in .env file")
        print("Get it from @BotFather on Telegram")
        return False
    
    if not Config.STORAGE_CHANNEL_ID:
        print("❌ STORAGE_CHANNEL_ID is required in .env file")
        print("Create a private channel and get its ID")
        return False
    
    print("✅ Konfiguratsiya to'g'ri!\n")
    
    # Initialize userbot with specific client settings
    from telethon import TelegramClient
    client = TelegramClient(
        Config.SESSION_NAME,
        Config.API_ID,
        Config.API_HASH,
        receive_updates=False
    )
    userbot = DownloaderUserbot()
    userbot.client = client
    
    print("🔐 Userbot autentifikatsiyasini sozlash...")
    print("Telegram hisobingiz bilan autentifikatsiya qilishingiz kerak.")
    print("Bu bir martalik jarayon va sessiya faylini yaratadi.\n")
    
    # Authenticate interactively
    if await userbot.authenticate_interactive(
        phone=os.getenv('PHONE'), 
        code=os.getenv('CODE'), 
        password=os.getenv('PASSWORD')
    ):
        print("\n✅ Autentifikatsiya muvaffaqiyatli!")
        
        # Test connection
        print("🔍 Ulanishlarni tekshirish...")
        if await userbot.test_connection():
            print("✅ Barcha ulanishlar ishlamoqda!")
            
            # Cleanup
            await userbot.stop()
            
            print("\n🎉 Sozlash muvaffaqiyatli yakunlandi!")
            print("\nKeyingi qadamlar:")
            print("1. Botni ishga tushiring: python main.py")
            print("2. Botga Instagram havolalarini yuboring")
            print("3. Avtomatlashtirilgan video yuklashdan zavqlaning!")
            
            return True
        else:
            print("❌ Ulanish testi muvaffaqiyatsiz tugadi")
            await userbot.stop()
            return False
    else:
        print("❌ Autentifikatsiya muvaffaqiyatsiz tugadi")
        await userbot.stop()
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n❌ Sozlash foydalanuvchi tomonidan to'xtatildi")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Setup error: {e}")
        sys.exit(1)
