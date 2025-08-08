#!/usr/bin/env python3
"""
Test script for Instagram bypass functionality
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the parent directory to sys.path to import our modules
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))

from config import Config
from db.database import Database
from utils import URLValidator


async def test_instagram_bypass():
    """Test Instagram bypass functionality"""
    print("🧪 Testing Instagram Bypass Functionality")
    print("=" * 50)
    
    # Initialize database
    db = Database(Config.DATABASE_PATH)
    await db.init_db()
    
    # Test URLs
    test_urls = [
        "https://instagram.com/stories/johndoe/123456789/",
        "https://instagram.com/stories/testuser/987654321/", 
        "https://instagram.com/p/ABC123/",  # This won't have username
        "https://instagram.com/reel/XYZ789/"  # This won't have username
    ]
    
    # Test username extraction
    print("\n1. Testing URL username extraction:")
    for url in test_urls:
        username = URLValidator.extract_instagram_username_from_url(url)
        print(f"  URL: {url}")
        print(f"  Username: {username or 'None'}")
        print()
    
    # Test adding bypass profiles
    print("2. Testing bypass profile management:")
    
    # Add test profiles
    test_profiles = ["johndoe", "testuser", "bypass_profile"]
    
    for profile in test_profiles:
        success = await db.add_instagram_bypass_profile(profile)
        print(f"  Added '{profile}': {'✅ Success' if success else '❌ Failed'}")
    
    # List all bypass profiles
    print("\n3. Current bypass profiles:")
    profiles = await db.get_instagram_bypass_profiles()
    for profile in profiles:
        print(f"  - @{profile[1]} (ID: {profile[0]})")
    
    # Test bypass check
    print("\n4. Testing bypass checks:")
    test_usernames = ["johndoe", "testuser", "nonexistent", "bypass_profile"]
    
    for username in test_usernames:
        is_bypass = await db.is_instagram_bypass_profile(username)
        print(f"  @{username}: {'✅ Bypass enabled' if is_bypass else '❌ Regular check'}")
    
    # Test removing profiles
    print("\n5. Testing profile removal:")
    if profiles:
        first_profile = profiles[0]
        success = await db.remove_instagram_bypass_profile(first_profile[0])
        print(f"  Removed @{first_profile[1]}: {'✅ Success' if success else '❌ Failed'}")
    
    # Final profile list
    print("\n6. Final bypass profiles:")
    final_profiles = await db.get_instagram_bypass_profiles()
    for profile in final_profiles:
        print(f"  - @{profile[1]} (ID: {profile[0]})")
    
    print("\n✅ Instagram bypass functionality test completed!")


async def test_url_validation():
    """Test URL validation and processing"""
    print("\n🔗 Testing URL Validation")
    print("=" * 30)
    
    test_cases = [
        # Instagram URLs
        ("https://instagram.com/p/ABC123/", "instagram"),
        ("https://instagram.com/reel/XYZ789/", "instagram"),
        ("https://instagram.com/stories/username/123456789/", "instagram"),
        
        # YouTube URLs  
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
        
        # TikTok URLs
        ("https://tiktok.com/@user/video/123456789", "tiktok"),
        ("https://vm.tiktok.com/ABC123/", "tiktok"),
        
        # Facebook URLs
        ("https://facebook.com/watch/?v=123456789", "facebook"),
        ("https://fb.watch/XYZ789/", "facebook"),
        
        # Twitter URLs
        ("https://twitter.com/user/status/123456789", "twitter"),
        ("https://x.com/user/status/123456789", "twitter"),
        
        # Invalid URLs
        ("https://example.com/video", None),
        ("not_a_url", None)
    ]
    
    for url, expected_type in test_cases:
        detected_type = URLValidator.get_url_type(url)
        status = "✅" if detected_type == expected_type else "❌"
        
        print(f"  {status} {url}")
        print(f"      Expected: {expected_type}, Got: {detected_type}")
        
        if expected_type == "instagram":
            username = URLValidator.extract_instagram_username_from_url(url)
            print(f"      Username: {username or 'None'}")
        print()


if __name__ == "__main__":
    async def main():
        print("🚀 Starting Instagram Bypass Tests\n")
        
        # Validate config first
        if not Config.validate():
            print("❌ Configuration validation failed!")
            print("Please check your .env file and ensure all required fields are set.")
            return
        
        await test_url_validation()
        await test_instagram_bypass()
        
        print("\n🎉 All tests completed!")
    
    # Run tests
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
