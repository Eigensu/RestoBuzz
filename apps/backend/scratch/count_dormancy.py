import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta, timezone
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.config import settings
from app.database import get_fielia_db

async def count():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client.get_database(settings.mongodb_db_name or "restobuzz")
    
    now = datetime.now(timezone.utc)
    
    # Thresholds
    at_risk_start = now - timedelta(days=60)
    at_risk_end = now - timedelta(days=30)
    
    dormant_start = now - timedelta(days=90)
    dormant_end = now - timedelta(days=60)
    
    lost_end = now - timedelta(days=90)
    
    print(f"Counting segments as of: {now.strftime('%Y-%m-%d')}")
    print(f"At-Risk Range: {at_risk_start.strftime('%Y-%m-%d')} to {at_risk_end.strftime('%Y-%m-%d')}")
    print(f"Dormant Range: {dormant_start.strftime('%Y-%m-%d')} to {dormant_end.strftime('%Y-%m-%d')}")
    print(f"Lost: Before {lost_end.strftime('%Y-%m-%d')}")
    
    restaurants = await db.restaurants.find().to_list(100)
    
    results = []
    
    for rest in restaurants:
        rid = rest.get("id") or str(rest["_id"])
        
        m_db = db
        m_coll = "members"
        m_query = {"restaurant_id": rid, "is_active": True}
        
        if rid == "r2":
            f_db = get_fielia_db()
            if f_db is not None:
                m_db = f_db.client.get_database("test")
                m_coll = "cards"
                m_query = {} # all cards are r2
        
        active = await m_db[m_coll].count_documents({
            **m_query,
            "last_visit": {"$gte": now - timedelta(days=30)}
        })
        
        at_risk = await m_db[m_coll].count_documents({
            **m_query,
            "last_visit": {"$gte": at_risk_start, "$lt": at_risk_end}
        })
        
        dormant = await m_db[m_coll].count_documents({
            **m_query,
            "last_visit": {"$gte": dormant_start, "$lt": dormant_end}
        })
        
        lost = await m_db[m_coll].count_documents({
            **m_query,
            "last_visit": {"$lt": lost_end}
        })
        
        total = await m_db[m_coll].count_documents({"restaurant_id": rid} if m_coll == "members" else {})
        
        results.append({
            "name": rest.get("name"),
            "rid": rid,
            "total": total,
            "active": active,
            "at_risk": at_risk,
            "dormant": dormant,
            "lost": lost
        })

    # Print Table
    print("\n| Restaurant | Total Members | Active (<30d) | At-Risk (30-60d) | Dormant (60-90d) | Lost (90d+) | Unknown |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    grand_total = 0
    grand_active = 0
    grand_at_risk = 0
    grand_dormant = 0
    grand_lost = 0
    
    for r in results:
        unknown = r["total"] - (r["active"] + r["at_risk"] + r["dormant"] + r["lost"])
        print(f"| **{r['name']} ({r['rid']})** | {r['total']} | {r['active']} | **{r['at_risk']}** | **{r['dormant']}** | **{r['lost']}** | {unknown} |")
        
        grand_total += r["total"]
        grand_active += r["active"]
        grand_at_risk += r["at_risk"]
        grand_dormant += r["dormant"]
        grand_lost += r["lost"]
        
    print(f"| **TOTAL** | **{grand_total}** | **{grand_active}** | **{grand_at_risk}** | **{grand_dormant}** | **{grand_lost}** | **{grand_total - (grand_active + grand_at_risk + grand_dormant + grand_lost)}** |")

if __name__ == "__main__":
    asyncio.run(count())
