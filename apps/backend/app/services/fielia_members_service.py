from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.core.logging import get_logger
from bson import ObjectId
import asyncio

logger = get_logger(__name__)

class FieliaMembersService:
    _client: AsyncIOMotorClient | None = None
    _db_name = "test"
    _collection_name = "cards"

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient | None:
        """Lazy-load the MongoDB client. Returns None if URI is missing."""
        if cls._client is None:
            uri = settings.fielia_mongo_uri
            if not uri:
                logger.warning("fielia_service_uri_missing", msg="FIELIA_MONGO_URI is not configured. External members will not be available.")
                return None
            try:
                # Use a short timeout for initial connection to avoid blocking backend startup
                cls._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            except Exception as e:
                logger.error("fielia_service_client_init_failed", error=str(e))
                return None
        return cls._client

    def _map_doc(self, doc: dict):
        """Normalize external document to internal Member model."""
        try:
            joined_at = doc.get("createdAt")
            if isinstance(joined_at, datetime):
                joined_at = joined_at.replace(tzinfo=timezone.utc)
            
            last_visit = doc.get("updatedAt")
            if isinstance(last_visit, datetime):
                last_visit = last_visit.replace(tzinfo=timezone.utc)

            return {
                "id": str(doc.get("_id")),
                "restaurant_id": "r2",
                "type": doc.get("type", "ecard"),
                "name": doc.get("content") or f"{doc.get('firstName', '')} {doc.get('lastName', '')}".strip() or "Unknown",
                "phone": doc.get("phone") or "N/A",
                "email": doc.get("email"),
                "card_uid": doc.get("uuid"), # Mapping external uuid to card_uid
                "ecard_code": None,
                "joined_at": joined_at.isoformat() if joined_at else None,
                "visit_count": len(doc.get("scanHistory", [])),
                "points": 0,
                "last_visit": last_visit.isoformat() if last_visit else None,
                "is_active": True,
                "tags": [],
                "notes": doc.get("address", "")
            }
        except Exception as e:
            logger.error("fielia_doc_mapping_failed", doc_id=str(doc.get("_id")), error=str(e))
            return None

    async def list_members(self, limit: int = 50, offset: int = 0, search: str = None, member_type: str = None):
        """Fetch members list from external DB with fail-safe."""
        try:
            client = self.get_client()
            if not client:
                return {"items": [], "total": 0, "warning": "External member service not configured"}

            db = client[self._db_name]
            collection = db[self._collection_name]

            query = {}
            if search:
                query["$or"] = [
                    {"firstName": {"$regex": search, "$options": "i"}},
                    {"lastName": {"$regex": search, "$options": "i"}},
                    {"phone": {"$regex": search, "$options": "i"}},
                    {"content": {"$regex": search, "$options": "i"}},
                ]

            total = await collection.count_documents(query)
            cursor = collection.find(query).sort("createdAt", -1).skip(offset).limit(limit)
            docs = await cursor.to_list(length=limit)

            return {
                "items": [m for d in docs if (m := self._map_doc(d)) is not None],
                "total": total,
                "page": (offset // limit) + 1,
                "page_size": limit
            }
        except Exception as e:
            logger.error("fielia_list_members_failed", error=str(e))
            return {"items": [], "total": 0, "warning": "External member service unavailable"}

    async def get_summary(self, from_dt: datetime, to_dt: datetime):
        """Fetch summary dashboard data from external DB with fail-safe."""
        try:
            client = self.get_client()
            if not client:
                return self._empty_summary()

            db = client[self._db_name]
            collection = db[self._collection_name]

            # Growth trend
            pipeline = [
                {"$match": {"createdAt": {"$gte": from_dt, "$lte": to_dt}}},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$createdAt"},
                        "month": {"$month": "$createdAt"},
                    },
                    "count": {"$sum": 1},
                }},
                {"$sort": {"_id.year": 1, "_id.month": 1}},
            ]
            growth_raw = await collection.aggregate(pipeline).to_list(24)
            
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            monthly_growth = [
                {
                    "month": f"{month_names[r['_id']['month'] - 1]} {r['_id']['year']}",
                    "new_members": r["count"],
                }
                for r in growth_raw
            ]

            # Basic Stats
            now = datetime.now(timezone.utc)
            month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            dormant_cutoff = now - timedelta(days=30)

            total_all = await collection.count_documents({})
            new_this_month = await collection.count_documents({"createdAt": {"$gte": month_start}})
            dormant = await collection.count_documents({
                "$or": [
                    {"updatedAt": {"$lt": dormant_cutoff}},
                    {"updatedAt": {"$exists": False}}
                ]
            })

            # Top visitors
            top_visitors_raw = await collection.aggregate([
                {"$addFields": {"visit_count": {"$size": {"$ifNull": ["$scanHistory", []]}}}},
                {"$sort": {"visit_count": -1}},
                {"$limit": 10}
            ]).to_list(10)

            top_visitors = []
            for doc in top_visitors_raw:
                mapped = self._map_doc(doc)
                if mapped:
                    top_visitors.append({
                        "name": mapped["name"],
                        "phone": mapped["phone"],
                        "type": mapped["type"],
                        "visit_count": mapped["visit_count"],
                        "last_visit": mapped["last_visit"]
                    })

            return {
                "summary": {
                    "total_members": total_all,
                    "active_members": total_all,
                    "new_this_month": new_this_month,
                    "dormant_members": dormant,
                    "dormant_rate": round(dormant / total_all * 100, 1) if total_all else 0,
                },
                "monthly_growth": monthly_growth,
                "category_split": [{"category": "ecard", "count": total_all}],
                "top_visitors": top_visitors,
            }
        except Exception as e:
            logger.error("fielia_summary_failed", error=str(e))
            return self._empty_summary()

    def _empty_summary(self):
        return {
            "summary": {"total_members": 0, "active_members": 0, "new_this_month": 0, "dormant_members": 0, "dormant_rate": 0},
            "monthly_growth": [],
            "category_split": [],
            "top_visitors": [],
            "warning": "External member service unavailable"
        }

    async def get_export_rows(self, from_dt: datetime, to_dt: datetime):
        """Fetch export rows from external DB with fail-safe."""
        try:
            client = self.get_client()
            if not client:
                return []

            db = client[self._db_name]
            collection = db[self._collection_name]

            query = {"createdAt": {"$gte": from_dt, "$lte": to_dt}}
            rows = []
            async for doc in collection.find(query).sort("createdAt", -1):
                m = self._map_doc(doc)
                if m:
                    rows.append([
                        m["name"], m["phone"], m.get("email", ""), m["type"],
                        m["joined_at"][:10] if m["joined_at"] else "",
                        m["visit_count"],
                        m["last_visit"][:10] if m["last_visit"] else "",
                        "Yes", doc.get("uuid", ""), "", "", doc.get("address", "")
                    ])
            return rows
        except Exception as e:
            logger.error("fielia_export_failed", error=str(e))
            return []

fielia_service = FieliaMembersService()
