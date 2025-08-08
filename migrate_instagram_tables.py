#!/usr/bin/env python3
"""Migration script to convert Instagram bypass profiles to Instagram mandatory profiles."""

import asyncio
import aiosqlite
import os
from loguru import logger

DATABASE_PATH = "./db/videos.db"

async def migrate_instagram_tables():
    """Migrate Instagram bypass profiles to Instagram mandatory profiles."""
    if not os.path.exists(DATABASE_PATH):
        logger.info("Database file does not exist, no migration needed")
        return
    
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Check if old table exists
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='instagram_bypass_profiles'") as cursor:
                old_table_exists = await cursor.fetchone()
            
            if not old_table_exists:
                logger.info("Old instagram_bypass_profiles table does not exist, no migration needed")
                return
            
            # Check if new table exists
            async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='instagram_mandatory_profiles'") as cursor:
                new_table_exists = await cursor.fetchone()
            
            if not new_table_exists:
                logger.info("Creating new instagram_mandatory_profiles table...")
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
                await db.commit()
                logger.info("Created instagram_mandatory_profiles table")
            
            # Check if there's data to migrate
            async with db.execute("SELECT COUNT(*) FROM instagram_bypass_profiles WHERE is_active = 1") as cursor:
                count_result = await cursor.fetchone()
                count = count_result[0] if count_result else 0
            
            if count == 0:
                logger.info("No active Instagram bypass profiles to migrate")
                return
            
            logger.info(f"Migrating {count} Instagram bypass profiles to mandatory profiles...")
            
            # Get old data
            async with db.execute("SELECT username FROM instagram_bypass_profiles WHERE is_active = 1") as cursor:
                old_profiles = await cursor.fetchall()
            
            migrated_count = 0
            for profile in old_profiles:
                username = profile[0]
                
                # Skip wildcard entries
                if username == '*':
                    logger.info(f"Skipping wildcard entry: {username}")
                    continue
                
                profile_url = f"https://instagram.com/{username}"
                profile_title = f"@{username}"
                
                try:
                    # Insert into new table
                    await db.execute("""
                        INSERT OR IGNORE INTO instagram_mandatory_profiles 
                        (username, profile_url, profile_title) 
                        VALUES (?, ?, ?)
                    """, (username, profile_url, profile_title))
                    
                    migrated_count += 1
                    logger.info(f"Migrated profile: @{username}")
                    
                except Exception as e:
                    logger.error(f"Error migrating profile @{username}: {e}")
            
            await db.commit()
            logger.info(f"Successfully migrated {migrated_count} Instagram profiles")
            
            # Optionally rename old table (don't delete, just rename for safety)
            try:
                await db.execute("ALTER TABLE instagram_bypass_profiles RENAME TO instagram_bypass_profiles_old")
                await db.commit()
                logger.info("Renamed old table to instagram_bypass_profiles_old")
            except Exception as e:
                logger.warning(f"Could not rename old table: {e}")
                
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

async def main():
    """Main migration function."""
    logger.info("Starting Instagram tables migration...")
    
    # Ensure database directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")
    
    await migrate_instagram_tables()
    logger.info("Migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
