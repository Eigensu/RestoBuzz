import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import csv
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

import aiofiles

def _get_tier(lv: datetime, t1: datetime, t2: datetime, t3: datetime) -> str:
    if lv >= t1: return "ACTIVE (<30d)"
    if lv >= t2: return "AT-RISK (30-60d)"
    if lv >= t3: return "DORMANT (60-90d)"
    return "LOST (90d+)"

async def export_csv():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    now = datetime.now(timezone.utc)
    t1 = now - timedelta(days=30)
    t2 = now - timedelta(days=60)
    t3 = now - timedelta(days=90)
    
    output_file = "c:/Users/Aanshuvi Shah/Desktop/Eigensu/BINGE/RestoBuzz/apps/backend/scratch/dormant_members_report.csv"
    print(f"Generating CSV report at: {output_file}")
    
    restaurants = await db.restaurants.find().to_list(100)
    member_rows = []
    
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        name = rest.get("name")
        print(f"Processing {name} ({rid})...")
        
        cursor = db.members.find({"restaurant_id": rid, "last_visit": {"$ne": None}})
        async for m in cursor:
            lv = m.get("last_visit")
            if not lv: continue
            
            if lv.tzinfo is None:
                lv = lv.replace(tzinfo=timezone.utc)
                
            tier = _get_tier(lv, t1, t2, t3)
            
            member_rows.append([
                rid, name, f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
                m.get("phone"), lv.strftime("%Y-%m-%d"), tier
            ])
            
    async with aiofiles.open(output_file, mode='w', newline='', encoding='utf-8') as f:
        # csv.writer requires synchronous file, but we can write strings
        await f.write("--- RESTOBUZZ DORMANCY REPORT ---\n")
        await f.write(f"Generated At,{now.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        await f.write("restaurant_id,restaurant_name,member_name,phone,last_visit,tier\n")
        
        for row in member_rows:
            escaped_row = ['"{}"'.format(str(val).replace('"', '""')) if ',' in str(val) else str(val) for val in row]
            await f.write(",".join(escaped_row) + "\n")

    print(f"Export complete. Total segmented members exported: {len(member_rows)}")

if __name__ == "__main__":
    asyncio.run(export_csv())
