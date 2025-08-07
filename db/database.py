"""Database module for managing video records in SQLite."""

import os
import aiosqlite
import asyncio
from typing import Optional, Tuple
from datetime import datetime
from loguru import logger

class Database:
    """Database manager for video records."""
    
    def __init__(self, db_path: str):
        """Initialize database with the given path."""
        self.db_path = db_path
        self.ensure_db_directory()
    
    def ensure_db_directory(self):
        """Ensure the database directory exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
    
    async def init_db(self):
        """Initialize the database tables."""
        async with aiosqlite.connect(self.db_path) as db:
            # Videos table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    channel_message_id INTEGER NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'unknown',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    phone TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    first_interaction DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_interaction DATETIME DEFAULT CURRENT_TIMESTAMP,
                    total_downloads INTEGER DEFAULT 0
                )
            """)
            
            # Statistics table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE NOT NULL,
                    new_users INTEGER DEFAULT 0,
                    total_downloads INTEGER DEFAULT 0,
                    instagram_downloads INTEGER DEFAULT 0,
                    youtube_downloads INTEGER DEFAULT 0,
                    tiktok_downloads INTEGER DEFAULT 0
                )
            """)
            
            # Mandatory subscription channels table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mandatory_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_type TEXT NOT NULL,
                    channel_username TEXT,
                    channel_title TEXT,
                    invite_link TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Reaction messages table for reaction-based processing
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reaction_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    url_type TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(message_id, chat_id, user_id)
                )
            """)
            
            # Instagram mandatory profiles table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS instagram_mandatory_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    profile_url TEXT,
                    profile_title TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User subscription notifications table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_subscription_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, chat_id, notification_type)
                )
            """)
            
            # Add platform column to existing videos if it doesn't exist
            try:
                await db.execute("ALTER TABLE videos ADD COLUMN platform TEXT DEFAULT 'unknown'")
            except:
                pass  # Column already exists
            
            await db.commit()
            logger.info("Database initialized successfully")
    
    async def add_video(self, url: str, channel_message_id: int, platform: str = 'unknown') -> bool:
        """
        Add a new video record to the database.
        
        Args:
            url: Instagram reel URL
            channel_message_id: Message ID in the storage channel
            
        Returns:
            True if added successfully, False if URL already exists
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO videos (url, channel_message_id, platform) VALUES (?, ?, ?)",
                    (url, channel_message_id, platform)
                )
                await db.commit()
                logger.info(f"Added video record: {url} -> {channel_message_id} ({platform})")
                
                # Update daily stats
                await self._update_daily_stats(db, platform)
                
                return True
        except aiosqlite.IntegrityError:
            logger.warning(f"URL already exists in database: {url}")
            return False
        except Exception as e:
            logger.error(f"Error adding video record: {e}")
            return False
    
    async def get_video(self, url: str) -> Optional[Tuple[int, datetime]]:
        """
        Get video record by URL.
        
        Args:
            url: Instagram reel URL
            
        Returns:
            Tuple of (channel_message_id, timestamp) if found, None otherwise
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT channel_message_id, timestamp FROM videos WHERE url = ?",
                    (url,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0], datetime.fromisoformat(row[1])
                    return None
        except Exception as e:
            logger.error(f"Error getting video record: {e}")
            return None
    
    async def get_video_count(self) -> int:
        """Get total number of videos in the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM videos") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting video count: {e}")
            return 0
    
    async def cleanup_old_records(self, days: int = 30) -> int:
        """
        Clean up old records from the database.
        
        Args:
            days: Number of days to keep records
            
        Returns:
            Number of deleted records
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM videos WHERE timestamp < datetime('now', '-{} days')".format(days)
                )
                deleted_count = cursor.rowcount
                await db.commit()
                logger.info(f"Cleaned up {deleted_count} old records")
                return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")
            return 0
    
    # User management methods
    async def add_or_update_user(self, user_id: int, username: str = None, phone: str = None, 
                                first_name: str = None, last_name: str = None) -> bool:
        """Add new user or update existing user info."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Check if user exists
                async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
                    exists = await cursor.fetchone()
                
                if exists:
                    # Update existing user
                    await db.execute(
                        "UPDATE users SET username = ?, phone = ?, first_name = ?, last_name = ?, last_interaction = CURRENT_TIMESTAMP WHERE id = ?",
                        (username, phone, first_name, last_name, user_id)
                    )
                else:
                    # Add new user and update daily stats
                    await db.execute(
                        "INSERT INTO users (id, username, phone, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                        (user_id, username, phone, first_name, last_name)
                    )
                    await self._update_daily_new_users(db)
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding/updating user: {e}")
            return False
    
    async def increment_user_downloads(self, user_id: int) -> None:
        """Increment user's download count."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET total_downloads = total_downloads + 1, last_interaction = CURRENT_TIMESTAMP WHERE id = ?",
                    (user_id,)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error incrementing user downloads: {e}")
    
    async def get_users_paginated(self, offset: int = 0, limit: int = 10) -> list:
        """Get users with pagination."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT id, username, first_name, last_name, total_downloads, first_interaction FROM users ORDER BY first_interaction DESC LIMIT ? OFFSET ?",
                    (limit, offset)
                ) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
    
    async def get_total_users_count(self) -> int:
        """Get total number of users."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting users count: {e}")
            return 0
    
    async def get_all_users(self) -> list:
        """Get all users for broadcast."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT id FROM users") as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    # Statistics methods
    async def get_today_stats(self) -> dict:
        """Get today's statistics."""
        try:
            today = datetime.now().date()
            async with aiosqlite.connect(self.db_path) as db:
                # Get daily stats
                async with db.execute(
                    "SELECT new_users, total_downloads, instagram_downloads, youtube_downloads, tiktok_downloads FROM daily_stats WHERE date = ?",
                    (today,)
                ) as cursor:
                    row = await cursor.fetchone()
                
                if row:
                    return {
                        'new_users': row[0],
                        'total_downloads': row[1],
                        'instagram_downloads': row[2],
                        'youtube_downloads': row[3],
                        'tiktok_downloads': row[4]
                    }
                else:
                    return {
                        'new_users': 0,
                        'total_downloads': 0,
                        'instagram_downloads': 0,
                        'youtube_downloads': 0,
                        'tiktok_downloads': 0
                    }
        except Exception as e:
            logger.error(f"Error getting today stats: {e}")
            return {}
    
    async def get_platform_stats(self) -> dict:
        """Get all-time platform statistics."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT platform, COUNT(*) FROM videos GROUP BY platform"
                ) as cursor:
                    rows = await cursor.fetchall()
                
                stats = {}
                for row in rows:
                    stats[row[0]] = row[1]
                
                return stats
        except Exception as e:
            logger.error(f"Error getting platform stats: {e}")
            return {}
    
    async def _update_daily_stats(self, db, platform: str) -> None:
        """Update daily statistics for downloads."""
        try:
            today = datetime.now().date()
            
            # Get current stats
            async with db.execute(
                "SELECT total_downloads, instagram_downloads, youtube_downloads, tiktok_downloads FROM daily_stats WHERE date = ?",
                (today,)
            ) as cursor:
                row = await cursor.fetchone()
            
            if row:
                # Update existing record
                total, instagram, youtube, tiktok = row
                total += 1
                
                if platform.lower() == 'instagram':
                    instagram += 1
                elif platform.lower() == 'youtube':
                    youtube += 1
                elif platform.lower() == 'tiktok':
                    tiktok += 1
                
                await db.execute(
                    "UPDATE daily_stats SET total_downloads = ?, instagram_downloads = ?, youtube_downloads = ?, tiktok_downloads = ? WHERE date = ?",
                    (total, instagram, youtube, tiktok, today)
                )
            else:
                # Create new record
                instagram = 1 if platform.lower() == 'instagram' else 0
                youtube = 1 if platform.lower() == 'youtube' else 0
                tiktok = 1 if platform.lower() == 'tiktok' else 0
                
                await db.execute(
                    "INSERT INTO daily_stats (date, total_downloads, instagram_downloads, youtube_downloads, tiktok_downloads) VALUES (?, ?, ?, ?, ?)",
                    (today, 1, instagram, youtube, tiktok)
                )
            
            await db.commit()
        except Exception as e:
            logger.error(f"Error updating daily stats: {e}")
    
    async def _update_daily_new_users(self, db) -> None:
        """Update daily statistics for new users."""
        try:
            today = datetime.now().date()
            
            # Get current stats
            async with db.execute(
                "SELECT new_users FROM daily_stats WHERE date = ?",
                (today,)
            ) as cursor:
                row = await cursor.fetchone()
            
            if row:
                # Update existing record
                new_users = row[0] + 1
                await db.execute(
                    "UPDATE daily_stats SET new_users = ? WHERE date = ?",
                    (new_users, today)
                )
            else:
                # Create new record
                await db.execute(
                    "INSERT INTO daily_stats (date, new_users) VALUES (?, ?)",
                    (today, 1)
                )
            
            await db.commit()
        except Exception as e:
            logger.error(f"Error updating daily new users: {e}")
    
    # Mandatory subscription channels methods
    async def add_mandatory_channel(self, channel_id: str, channel_type: str, 
                                  channel_username: str = None, channel_title: str = None, 
                                  invite_link: str = None) -> bool:
        """Add a mandatory subscription channel."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO mandatory_channels (channel_id, channel_type, channel_username, channel_title, invite_link) VALUES (?, ?, ?, ?, ?)",
                    (channel_id, channel_type, channel_username, channel_title, invite_link)
                )
                await db.commit()
                logger.info(f"Added mandatory channel: {channel_id} ({channel_type})")
                return True
        except Exception as e:
            logger.error(f"Error adding mandatory channel: {e}")
            return False
    
    async def get_mandatory_channels(self) -> list:
        """Get all active mandatory subscription channels."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT id, channel_id, channel_type, channel_username, channel_title, invite_link FROM mandatory_channels WHERE is_active = 1"
                ) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting mandatory channels: {e}")
            return []
    
    async def remove_mandatory_channel(self, channel_id: str) -> bool:
        """Remove a mandatory subscription channel."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "UPDATE mandatory_channels SET is_active = 0 WHERE channel_id = ?",
                    (channel_id,)
                )
                await db.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Removed mandatory channel: {channel_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error removing mandatory channel: {e}")
            return False
    
    async def get_mandatory_channels_count(self) -> int:
        """Get count of active mandatory channels."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute("SELECT COUNT(*) FROM mandatory_channels WHERE is_active = 1") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting mandatory channels count: {e}")
            return 0
    
    # Reaction message storage methods
    async def store_reaction_message(self, message_id: int, chat_id: int, user_id: int, url: str, url_type: str):
        """Store message info for reaction-based processing."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Remove old entries (older than 1 hour)
                from datetime import datetime, timedelta
                old_time = datetime.now() - timedelta(hours=1)
                await db.execute(
                    "DELETE FROM reaction_messages WHERE created_at < ?",
                    (old_time.isoformat(),)
                )
                
                # Store new message
                await db.execute(
                    "INSERT OR REPLACE INTO reaction_messages (message_id, chat_id, user_id, url, url_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (message_id, chat_id, user_id, url, url_type, datetime.now().isoformat())
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Error storing reaction message: {e}")
    
    async def get_reaction_message(self, message_id: int, chat_id: int, user_id: int):
        """Get stored message info for reaction processing."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT url, url_type FROM reaction_messages WHERE message_id = ? AND chat_id = ? AND user_id = ?",
                    (message_id, chat_id, user_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row if row else None
        except Exception as e:
            logger.error(f"Error getting reaction message: {e}")
            return None
    
    async def get_any_reaction_message(self, message_id: int, chat_id: int):
        """Get any stored message info for this message_id and chat_id."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT url, url_type FROM reaction_messages WHERE message_id = ? AND chat_id = ? LIMIT 1",
                    (message_id, chat_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row if row else None
        except Exception as e:
            logger.error(f"Error getting any reaction message: {e}")
            return None
    
    async def cleanup_old_reaction_messages(self):
        """Clean up old reaction messages (older than 1 hour)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                from datetime import datetime, timedelta
                old_time = datetime.now() - timedelta(hours=1)
                cursor = await db.execute(
                    "DELETE FROM reaction_messages WHERE created_at < ?",
                    (old_time.isoformat(),)
                )
                await db.commit()
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old reaction messages")
        except Exception as e:
            logger.error(f"Error cleaning up reaction messages: {e}")
    
    # Instagram mandatory profile methods
    async def add_instagram_mandatory_profile(self, username: str, profile_title: str = None) -> bool:
        """Add an Instagram mandatory subscription profile."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                profile_url = f"https://instagram.com/{username.lower()}"
                title = profile_title or f"@{username}"
                await db.execute(
                    "INSERT INTO instagram_mandatory_profiles (username, profile_url, profile_title) VALUES (?, ?, ?)",
                    (username.lower(), profile_url, title)
                )
                await db.commit()
                logger.info(f"Added Instagram mandatory profile: {username}")
                return True
        except Exception as e:
            logger.error(f"Error adding Instagram mandatory profile: {e}")
            return False
    
    async def get_instagram_mandatory_profiles(self) -> list:
        """Get all active Instagram mandatory profiles."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT id, username, profile_url, profile_title FROM instagram_mandatory_profiles WHERE is_active = 1"
                ) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting Instagram mandatory profiles: {e}")
            return []
    
    async def remove_instagram_mandatory_profile(self, profile_id: int) -> bool:
        """Remove an Instagram mandatory profile."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "UPDATE instagram_mandatory_profiles SET is_active = 0 WHERE id = ?",
                    (profile_id,)
                )
                await db.commit()
                if cursor.rowcount > 0:
                    logger.info(f"Removed Instagram mandatory profile: {profile_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error removing Instagram mandatory profile: {e}")
            return False
    
    # User subscription notification methods
    async def has_shown_subscription_check(self, user_id: int, chat_id: int, notification_type: str = "subscription_check") -> bool:
        """Check if subscription check has been shown to user in this chat."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT id FROM user_subscription_notifications WHERE user_id = ? AND chat_id = ? AND notification_type = ?",
                    (user_id, chat_id, notification_type)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row is not None
        except Exception as e:
            logger.error(f"Error checking subscription notification: {e}")
            return False
    
    async def mark_subscription_check_shown(self, user_id: int, chat_id: int, notification_type: str = "subscription_check") -> bool:
        """Mark that subscription check has been shown to user in this chat."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO user_subscription_notifications (user_id, chat_id, notification_type) VALUES (?, ?, ?)",
                    (user_id, chat_id, notification_type)
                )
                await db.commit()
                logger.info(f"Marked subscription check as shown for user {user_id} in chat {chat_id}")
                return True
        except Exception as e:
            logger.error(f"Error marking subscription notification: {e}")
            return False
    
    async def reset_subscription_check_for_user(self, user_id: int, notification_type: str = "subscription_check") -> bool:
        """Reset subscription check notification for a user (admin use)."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM user_subscription_notifications WHERE user_id = ? AND notification_type = ?",
                    (user_id, notification_type)
                )
                await db.commit()
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Reset subscription check for user {user_id}: {deleted_count} records deleted")
                    return True
                return False
        except Exception as e:
            logger.error(f"Error resetting subscription notification: {e}")
            return False
