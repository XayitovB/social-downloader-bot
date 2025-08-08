"""Script to check remaining flood wait time"""

import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from config import Config
from datetime import datetime, timedelta

async def check_flood_wait():
    """Check if we can connect without flood wait"""
    print("🔍 Flood wait holatini tekshirish...")
    
    client = TelegramClient(
        'temp_check_session',
        Config.API_ID,
        Config.API_HASH
    )
    
    try:
        print("⚡ Telegram serveriga ulanishga urinish...")
        await client.start()
        
        if await client.is_user_authorized():
            print("✅ Flood wait muammosi yo'q! Bot ishga tushirish mumkin.")
            me = await client.get_me()
            print(f"👤 Hisobingiz: {me.first_name}")
            return True
        else:
            print("⚠️ Avtorizatsiya talab etiladi, lekin flood wait muammosi yo'q.")
            return True
            
    except FloodWaitError as e:
        remaining_time = e.seconds
        hours = remaining_time // 3600
        minutes = (remaining_time % 3600) // 60
        seconds = remaining_time % 60
        
        print(f"❌ Flood wait: {remaining_time} soniya kutish kerak")
        print(f"⏰ Vaqt: {hours} soat, {minutes} daqiqa, {seconds} soniya")
        
        # Calculate when it will be available
        available_time = datetime.now() + timedelta(seconds=remaining_time)
        print(f"🕒 Bot ishga tushirish mumkin bo'lgan vaqt: {available_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return False
        
    except Exception as e:
        print(f"❓ Noma'lum xatolik: {e}")
        return False
        
    finally:
        if client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    try:
        can_start = asyncio.run(check_flood_wait())
        if not can_start:
            print("\n💡 Maslahat: Cheklov vaqti tugaguncha kutib turing.")
            sys.exit(1)
        else:
            print("\n🚀 Hozir botni ishga tushirishingiz mumkin: python main.py")
    except KeyboardInterrupt:
        print("\n❌ Tekshirish to'xtatildi.")
        sys.exit(1)
