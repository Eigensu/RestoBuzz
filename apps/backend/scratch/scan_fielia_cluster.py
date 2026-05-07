import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def scan():
    uri = settings.fielia_mongo_uri
    if not uri:
        print("FIELIA_MONGO_URI is empty.")
        return
        
    print(f"Connecting to Fielia Cluster...")
    client = AsyncIOMotorClient(uri)
    
    try:
        # List all databases
        db_names = await client.list_database_names()
        print(f"Databases found: {db_names}")
        
        for db_name in db_names:
            if db_name in ["admin", "local", "config"]:
                continue
                
            db = client.get_database(db_name)
            collections = await db.list_collection_names()
            print(f"\nDatabase: {db_name}")
            print(f"Collections: {collections}")
            
            for coll_name in collections:
                count = await db[coll_name].count_documents({})
                print(f"   - {coll_name}: {count} records")
                
                if coll_name in ["members", "reservego_uploads"] and count > 0:
                    print(f"      [MATCH] Found data in {db_name}.{coll_name}!")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(scan())
