#!/usr/bin/env python3
"""Test sending Instagram URL with bot mention"""

import asyncio
from aiogram import Bot
from config import Config

async def send_test_with_mention():
    """Send test URL to bot with mention"""
    bot = Bot(token=Config.BOT_TOKEN)
    
    # Get bot info
    me = await bot.get_me()
    bot_username = me.username
    
    # Test URL with bot mention
    test_url_with_mention = f"@{bot_username} https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA=="
    
    try:
        # Send to group
        group_id = -4960895872  # Group ID from logs
        message = await bot.send_message(group_id, test_url_with_mention)
        print(f"✅ Sent URL with mention to group {group_id}, message ID: {message.message_id}")
        
    except Exception as e:
        print(f"❌ Error sending message: {e}")
    
    await bot.session.close()

if __name__ == "__main__":
    print("Sending Instagram URL with bot mention...")
    asyncio.run(send_test_with_mention())
