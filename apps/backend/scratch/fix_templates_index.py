import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, IndexModel

async def fix_indexes():
    # We will connect using the same settings as the app
    # Let's import the database and config to get the correct URL
    import os
    import sys
    from pathlib import Path
    
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.append(str(ROOT))
    
    from app.config import settings
    
    print("Connecting to MongoDB...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db_name = settings.mongodb_db_name or settings.mongodb_url.split("/")[-1].split("?")[0]
    if not db_name:
        db_name = "dishpatch"
    db = client[db_name]
    
    print(f"Using database: {db_name}")
    
    # Check existing indexes on templates
    indexes = await db.templates.index_information()
    print("Current indexes on 'templates':")
    for name, info in indexes.items():
        print(f"  - {name}: {info}")
        
    # Drop any index starting with restaurant_id_1_name_1_language_1_v
    for name in list(indexes.keys()):
        if name.startswith("restaurant_id_1_name_1_language_1_v"):
            print(f"Dropping leftover versioned index: {name}")
            await db.templates.drop_index(name)
            
    # Try creating the canonical index
    print("Creating canonical index...")
    try:
        await db.templates.create_index(
            [
                ("restaurant_id", ASCENDING),
                ("name", ASCENDING),
                ("language", ASCENDING),
            ],
            unique=True,
            name="restaurant_id_1_name_1_language_1",
            partialFilterExpression={"restaurant_id": {"$type": "string"}},
        )
        print("Canonical index created successfully!")
    except Exception as e:
        print(f"Failed to create canonical index: {e}")
        
    # Print indexes again
    indexes = await db.templates.index_information()
    print("Updated indexes on 'templates':")
    for name, info in indexes.items():
        print(f"  - {name}: {info}")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_indexes())
