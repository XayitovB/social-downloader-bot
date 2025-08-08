"""Simple test script to verify userbot connection"""

import asyncio
import sys
from telethon import TelegramClient
from config import Config

async def test_userbot():
    """Test userbot connection with simplified approach"""
    print("Testing userbot connection...")
    
    client = TelegramClient(
        'test_session',
        Config.API_ID,
        Config.API_HASH
    )
    
    try:
        print("Starting client...")
        await client.start()
        
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Already authenticated as: {me.first_name}")
            return True
        else:
            print("❌ Not authenticated. Please run setup first.")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        if client.is_connected():
            await client.disconnect()

if __name__ == "__main__":
    result = asyncio.run(test_userbot())
    if not result:
        sys.exit(1)
