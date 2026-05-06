import asyncio
from app.database import get_db, close_db

async def cleanup_member():
    db = get_db()
    
    phone = "7506907585"
    category = "test1"
    
    print(f"Searching for member with phone {phone} in category {category}...")
    
    # Check multiple variants
    query = {
        "phone": {"$in": [phone, f"+91{phone}", f" {phone}"]},
        "type": {"$regex": f"^{category}$", "$options": "i"}
    }
    
    result = await db.members.delete_many(query)
    
    if result.deleted_count > 0:
        print(f"SUCCESS: Deleted {result.deleted_count} member(s).")
    else:
        # One last try: just any member with this phone if it's orphaned
        result2 = await db.members.delete_many({"phone": {"$in": [phone, f"+91{phone}"]}})
        if result2.deleted_count > 0:
            print(f"SUCCESS: Found and deleted {result2.deleted_count} orphaned member(s) by phone.")
        else:
            print("INFO: No matching member found in internal database.")
        
    await close_db()

if __name__ == "__main__":
    asyncio.run(cleanup_member())
