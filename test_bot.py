#!/usr/bin/env python3
"""Test bot with Instagram URL"""

import asyncio
from aiogram import Bot
from config import Config

async def test_bot():
    """Send test message to bot"""
    bot = Bot(token=Config.BOT_TOKEN)
    
    # Get bot info
    me = await bot.get_me()
    print(f"Bot info: @{me.username}")
    
    # Test URL
    test_url = "https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA=="
    user_id = 7703771091  # Your user ID from logs
    
    try:
        # Send the test URL
        await bot.send_message(user_id, test_url)
        print(f"Sent test URL to user {user_id}")
    except Exception as e:
        print(f"Error sending message: {e}")
    
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_bot())
