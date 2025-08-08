#!/usr/bin/env python3
"""Check mandatory channels"""

from db.database import Database
import asyncio

async def check_channels():
    from config import Config
    db = Database(Config.DATABASE_PATH)
    await db.init_db()
    channels = await db.get_mandatory_channels()
    print('Mandatory channels:', channels)
    await db.close()

if __name__ == "__main__":
    asyncio.run(check_channels())
