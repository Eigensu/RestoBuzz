import asyncio
import sys
from app.database import get_fresh_db

async def fix_id():
    db = get_fresh_db()
    
    # Update phone_id for Soraia (r1)
    result = await db.restaurants.update_one(
        {"id": "r1", "wa_phones.0": {"$exists": True}},
        {"$set": {"wa_phones.0.phone_id": "1069035316301067"}}
    )
    print(f"Matched: {result.matched_count}, Modified: {result.modified_count}")
    if result.matched_count == 0:
        print("Error: No document matched (either 'r1' missing or wa_phones is empty).")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(fix_id())
