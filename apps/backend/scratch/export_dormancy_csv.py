import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import csv
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings

async def export_csv():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    now = datetime.now(timezone.utc)
    
    # Tier thresholds
    t1 = now - timedelta(days=30)
    t2 = now - timedelta(days=60)
    t3 = now - timedelta(days=90)
    
    output_file = "c:/Users/Aanshuvi Shah/Desktop/Eigensu/BINGE/RestoBuzz/apps/backend/scratch/dormant_members_report.csv"
    
    print(f"Generating CSV report at: {output_file}")
    
    # 1. Total Counts for Summary
    restaurants = await db.restaurants.find().to_list(100)
    summary_rows = []
    
    # Header for members
    member_header = ["restaurant_id", "restaurant_name", "member_name", "phone", "last_visit", "tier"]
    member_rows = []
    
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        name = rest.get("name")
        
        # Aggregate stats
        total = await db.members.count_documents({"restaurant_id": rid})
        with_visit = await db.members.count_documents({"restaurant_id": rid, "last_visit": {"$ne": None}})
        
        print(f"Processing {name} ({rid})...")
        
        # Fetch members with visits
        cursor = db.members.find({"restaurant_id": rid, "last_visit": {"$ne": None}})
        async for m in cursor:
            lv = m.get("last_visit")
            if not lv: continue
            
            # Ensure lv is timezone aware for comparison
            if lv.tzinfo is None:
                lv = lv.replace(tzinfo=timezone.utc)
                
            tier = "UNKNOWN"
            if lv >= t1: tier = "ACTIVE (<30d)"
            elif lv >= t2: tier = "AT-RISK (30-60d)"
            elif lv >= t3: tier = "DORMANT (60-90d)"
            else: tier = "LOST (90d+)"
            
            member_rows.append([
                rid,
                name,
                f"{m.get('first_name', '')} {m.get('last_name', '')}".strip(),
                m.get("phone"),
                lv.strftime("%Y-%m-%d"),
                tier
            ])
            
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["--- RESTOBUZZ DORMANCY REPORT ---"])
        writer.writerow(["Generated At", now.strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow([])
        writer.writerow(member_header)
        writer.writerows(member_rows)

    print(f"Export complete. Total segmented members exported: {len(member_rows)}")

if __name__ == "__main__":
    asyncio.run(export_csv())
