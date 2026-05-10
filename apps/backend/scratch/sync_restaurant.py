import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
from datetime import datetime, timezone, timedelta
import time
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.database import get_fielia_db
from app.utils.phone import normalize_phone

async def _normalize_members(m_db, m_coll_name, m_query):
    m_cursor = m_db[m_coll_name].find({**m_query, "normalized_phone": {"$exists": False}})
    m_ops = []
    async for m in m_cursor:
        norm = normalize_phone(m.get("phone"))
        if norm:
            m_ops.append(UpdateOne({"_id": m["_id"]}, {"$set": {"normalized_phone": norm}}))
    if m_ops:
        print(f"[INFO] Normalizing {len(m_ops)} members in {m_coll_name}...")
        await m_db[m_coll_name].bulk_write(m_ops, ordered=False)

async def _normalize_uploads(db, rid):
    print("[INFO] Scanning for unnormalized uploads...")
    u_cursor = db.reservego_uploads.find({"restaurant_id": rid, "normalized_phone": {"$exists": False}})
    u_ops = []
    processed_count = 0
    async for u in u_cursor:
        norm = normalize_phone(u.get("phone") or u.get("guest_number"))
        if norm:
            u_ops.append(UpdateOne({"_id": u["_id"]}, {"$set": {"normalized_phone": norm}}))
        if len(u_ops) >= 1000:
            await db.reservego_uploads.bulk_write(u_ops, ordered=False)
            processed_count += len(u_ops)
            print(f"   [INFO] Normalized {processed_count} uploads...")
            u_ops = []
    if u_ops:
        await db.reservego_uploads.bulk_write(u_ops, ordered=False)
        processed_count += len(u_ops)
        print(f"   [INFO] Normalized {processed_count} uploads total.")

async def _sync_visits(db, m_db, m_coll_name, m_query, rid):
    print("[INFO] Syncing visit history...")
    total_uploads = await db.reservego_uploads.count_documents({"restaurant_id": rid})
    visit_records = await db.reservego_uploads.count_documents({"restaurant_id": rid, "last_visited_date": {"$ne": None}})
    
    v_cursor = db.reservego_uploads.find({"restaurant_id": rid, "last_visited_date": {"$ne": None}, "normalized_phone": {"$ne": None}})
    v_ops = []
    async for v in v_cursor:
        norm = v.get("normalized_phone")
        visit_date = v.get("last_visited_date")
        if norm and visit_date:
            v_ops.append(UpdateOne(
                {**m_query, "normalized_phone": norm},
                {"$max": {"last_visit": visit_date}}
            ))
            
    matched_members = 0
    if v_ops:
        print(f"[INFO] Processing {len(v_ops)} matches against {m_coll_name}...")
        for i in range(0, len(v_ops), 1000):
            result = await m_db[m_coll_name].bulk_write(v_ops[i:i+1000], ordered=False)
            matched_members += result.modified_count
            if i % 5000 == 0 and i > 0:
                print(f"   [INFO] Progress: {i}/{len(v_ops)} updates applied...")
    return total_uploads, visit_records, matched_members

async def _print_final_validation(m_db, m_coll_name, m_query, rid, total_uploads, visit_records, matched_members, execution_time):
    now = datetime.now(timezone.utc)
    active = await m_db[m_coll_name].count_documents({**m_query, "last_visit": {"$gte": now - timedelta(days=30)}})
    at_risk = await m_db[m_coll_name].count_documents({**m_query, "last_visit": {"$gte": now - timedelta(days=60), "$lt": now - timedelta(days=30)}})
    dormant = await m_db[m_coll_name].count_documents({**m_query, "last_visit": {"$gte": now - timedelta(days=90), "$lt": now - timedelta(days=60)}})
    lost = await m_db[m_coll_name].count_documents({**m_query, "last_visit": {"$lt": now - timedelta(days=90)}})
    
    print(f"[INFO] Uploads Found: {total_uploads}")
    print(f"[INFO] Visit Records: {visit_records}")
    print(f"[INFO] Matched Members Updated: {matched_members}")
    print(f"\n[DORMANCY STATE] {rid}")
    print(f"   - Active (<30d): {active}")
    print(f"   - At-Risk (30-60d): {at_risk}")
    print(f"   - Dormant (60-90d): {dormant}")
    print(f"   - Lost (90d+):    {lost}")
    print(f"[SYNC COMPLETE] Execution Time: {execution_time}s")

async def sync_restaurant(rid: str):
    start_time = time.time()
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    rest = await db.restaurants.find_one({"id": rid})
    name = rest.get("name", "Unknown") if rest else "Unknown"
    print(f"\n[SYNC START] Restaurant: {name} ({rid})")
    
    m_db = db
    m_coll_name = "members"
    m_query = {"restaurant_id": rid}
    
    if rid == "r2":
        f_db = get_fielia_db()
        if f_db is not None:
            m_db = f_db.client.get_database("test")
            m_coll_name = "cards"
            m_query = {} 
            print("[INFO] Using Fielia External DB [test.cards] for members.")
        else:
            print("[WARNING] Fielia External DB URI found but connection failed. Falling back to local.")

    await _normalize_members(m_db, m_coll_name, m_query)
    await _normalize_uploads(db, rid)
    t_uploads, v_records, m_members = await _sync_visits(db, m_db, m_coll_name, m_query, rid)
    
    execution_time = round(time.time() - start_time, 2)
    await _print_final_validation(m_db, m_coll_name, m_query, rid, t_uploads, v_records, m_members, execution_time)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sync_restaurant.py <restaurant_id>")
        sys.exit(1)
    
    asyncio.run(sync_restaurant(sys.argv[1]))
