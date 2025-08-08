#!/usr/bin/env python3
"""Test updated group functionality"""

import asyncio
from aiogram import Bot
from config import Config

async def test_group_functionality():
    """Test automatic URL processing in groups"""
    bot = Bot(token=Config.BOT_TOKEN)
    
    # Test different scenarios
    test_scenarios = [
        "Check this out: https://www.instagram.com/reel/DGLPweS1Nau6r?igsh=MTR1ZWNjNmE5ZG1oNA==",
        "Look at this video https://youtube.com/watch?v=dQw4w9WgXcQ",
        "TikTok video: https://tiktok.com/@user/video/123456789", 
        "Just regular text without links",
        "Multiple links: https://instagram.com/p/ABC123/ and https://tiktok.com/@test/video/456"
    ]
    
    user_id = 7703771091
    group_id = -4960895872
    
    print("Testing automatic URL detection and processing...")
    print("=" * 60)
    
    for i, test_text in enumerate(test_scenarios, 1):
        print(f"\n🧪 Test {i}: {test_text[:50]}...")
        
        try:
            # Send to private chat first
            private_msg = await bot.send_message(user_id, f"Private test {i}: {test_text}")
            print(f"✅ Sent to private chat (ID: {private_msg.message_id})")
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Send to group
            group_msg = await bot.send_message(group_id, f"Group test {i}: {test_text}")
            print(f"✅ Sent to group (ID: {group_msg.message_id})")
            
            # Wait for bot processing
            await asyncio.sleep(3)
            
        except Exception as e:
            print(f"❌ Error in test {i}: {e}")
    
    await bot.session.close()
    print("\n🎯 Testing completed! Check the bot logs for processing results.")

if __name__ == "__main__":
    asyncio.run(test_group_functionality())
