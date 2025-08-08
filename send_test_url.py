#!/usr/bin/env python3
"""Send test Instagram URL to the bot"""

import asyncio
from aiogram import Bot
from config import Config

async def send_test():
    """Send test URL to bot"""
    bot = Bot(token=Config.BOT_TOKEN)
    
    # Test URL from the screenshot
    test_url = "https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA=="
    user_id = 7703771091  # Your user ID from logs
    
    try:
        # Send the test URL to yourself
        message = await bot.send_message(user_id, test_url)
        print(f"✅ Sent test URL to user {user_id}, message ID: {message.message_id}")
        
        # Wait a moment for the bot to process
        await asyncio.sleep(2)
        
        # Also send via group if needed
        group_id = -4960895872  # Group ID from logs
        try:
            group_message = await bot.send_message(group_id, test_url)
            print(f"✅ Sent test URL to group {group_id}, message ID: {group_message.message_id}")
        except Exception as e:
            print(f"⚠️  Could not send to group: {e}")
        
    except Exception as e:
        print(f"❌ Error sending message: {e}")
    
    await bot.session.close()

if __name__ == "__main__":
    print("Sending test Instagram URL...")
    asyncio.run(send_test())
