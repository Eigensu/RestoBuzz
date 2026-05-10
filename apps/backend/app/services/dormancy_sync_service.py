from typing import Any, List, Optional
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import UpdateOne, ASCENDING
from app.services.phone_normalizer import phone_normalizer
from app.services.member_match_service import member_match_service
from app.core.logging import get_logger
from app.database import get_db

logger = get_logger(__name__)

SYNC_NAME = "dormancy_sync"

class DormancySyncService:
    @staticmethod
    def calculate_tier(last_visit: datetime) -> str:
        if not last_visit:
            return "UNKNOWN"
            
        if last_visit.tzinfo is None:
            last_visit = last_visit.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        days = (now - last_visit).days
        
        if days < 30: return "ACTIVE"
        if days < 60: return "AT_RISK"
        if days < 90: return "DORMANT"
        return "LOST"

    @staticmethod
    async def sync_restaurant(rid: str, db: Optional[AsyncIOMotorDatabase] = None):
        if not db:
            db = get_db()
            
        start_time = datetime.now(timezone.utc)
        
        # 1. Fetch Sync State (Resumability)
        # We track the last processed '_id' using sync_name for indexing consistency
        state = await db.sync_metadata.find_one({"restaurant_id": rid, "sync_name": SYNC_NAME})
        last_id = state.get("last_processed_id") if state else None
        
        query = {"restaurant_id": rid, "last_visited_date": {"$ne": None}}
        if last_id:
            query["_id"] = {"$gt": last_id}
            
        # 2. Setup Member DB context
        m_db, m_coll, m_filter = await member_match_service.get_member_db_context(rid)
        
        # 3. Process Uploads in Chunks
        cursor = db.reservego_uploads.find(query).sort("_id", ASCENDING)
        
        stats = {
            "processed": 0,
            "matched": 0,
            "tier_changes": 0,
            "failed": 0,
            "latest_id": last_id
        }
        
        ops = []
        async for record in cursor:
            stats["processed"] += 1
            stats["latest_id"] = record["_id"]
            
            phone = record.get("phone") or record.get("guest_number")
            visit_date = record.get("last_visited_date")
            
            norm = phone_normalizer.normalize(phone)
            if not norm:
                stats["failed"] += 1
                continue
                
            tier = DormancySyncService.calculate_tier(visit_date)
            
            # OPTIMIZATION: Only update if last_visit is newer OR tier is different
            # We use $max for date safety and a combined filter for tier efficiency
            ops.append(UpdateOne(
                {
                    **m_filter, 
                    "normalized_phone": norm,
                    # Optimization: Only write if something actually changes
                    "$or": [
                        {"last_visit": {"$lt": visit_date}},
                        {"dormancy_tier": {"$ne": tier}},
                        {"dormancy_tier": {"$exists": False}}
                    ]
                },
                {
                    "$max": {"last_visit": visit_date},
                    "$set": {
                        "dormancy_tier": tier,
                        "last_synced_at": datetime.now(timezone.utc)
                    }
                }
            ))
            
            if len(ops) >= 500:
                result = await m_db[m_coll].bulk_write(ops, ordered=False)
                stats["matched"] += result.matched_count
                stats["tier_changes"] += result.modified_count
                ops = []
                
        if ops:
            result = await m_db[m_coll].bulk_write(ops, ordered=False)
            stats["matched"] += result.matched_count
            stats["tier_changes"] += result.modified_count

        # 4. Update Sync State (Checkpoint)
        if stats["latest_id"]:
            await db.sync_metadata.update_one(
                {"restaurant_id": rid, "sync_name": SYNC_NAME},
                {
                    "$set": {
                        "last_processed_id": stats["latest_id"],
                        "last_sync_time": datetime.now(timezone.utc),
                        "status": "SUCCESS",
                        "source": "reservego_uploads"
                    }
                },
                upsert=True
            )
        
        # 5. Production Audit Logging
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        log_entry = {
            "restaurant_id": rid,
            "start_time": start_time,
            "end_time": datetime.now(timezone.utc),
            "duration_seconds": duration,
            "processed_records": stats["processed"],
            "matched_records": stats["matched"],
            "tier_changes": stats["tier_changes"],
            "failed_records": stats["failed"],
            "checkpoint_id": str(stats["latest_id"]) if stats["latest_id"] else None
        }
        await db.sync_logs.insert_one(log_entry)
        
        return log_entry

    @staticmethod
    async def sync_all_restaurants():
        db = get_db()
        restaurants = await db.restaurants.find().to_list(None)
        results = []
        for rest in restaurants:
            rid = rest.get("id") or str(rest["_id"])
            try:
                res = await DormancySyncService.sync_restaurant(rid, db)
                results.append(res)
            except Exception as e:
                logger.error("dormancy_sync_failed", rid=rid, error=str(e))
        return results

dormancy_sync_service = DormancySyncService()
