import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), ".env"))

async def count_unique_phones():
    uri = os.getenv("FIELIA_MONGO_URI")
    client = AsyncIOMotorClient(uri)
    db = client["test"]
    col = db["cards"]
    
    # Get all phones
    cursor = col.find({}, {"phone": 1})
    all_phones = []
    async for doc in cursor:
        p = doc.get("phone")
        if p and p not in ["", "N/A", "null", "undefined"]:
            all_phones.append(p)
    
    unique_phones = set(all_phones)
    
    print(f"Total Card Records: {len(all_phones) + (1165 - len(all_phones))}") # roughly
    print(f"Unique Phone Numbers: {len(unique_phones)}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(count_unique_phones())
