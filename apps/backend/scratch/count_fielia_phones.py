import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load from .env in the root
load_dotenv(os.path.join(os.getcwd(), ".env"))

async def count_phones():
    uri = os.getenv("FIELIA_MONGO_URI")
    if not uri:
        print("Error: FIELIA_MONGO_URI not found in .env")
        return

    client = AsyncIOMotorClient(uri)
    db = client["test"]
    col = db["cards"]
    
    total = await col.count_documents({})
    # Count docs with non-empty, non-N/A phone numbers
    with_phone = await col.count_documents({
        "phone": {
            "$exists": True, 
            "$ne": "", 
            "$nin": [None, "N/A", "null", "undefined"]
        }
    })
    missing = total - with_phone
    
    print(f"Total Cards: {total}")
    print(f"Cards with valid phone: {with_phone}")
    print(f"Cards missing phone: {missing}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(count_phones())
