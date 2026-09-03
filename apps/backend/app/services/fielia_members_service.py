"""Service for accessing the external Fielia (NFC card) MongoDB database."""

import json
import re
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, List, Dict, Tuple, Any

from app.core.time import now_utc, normalize_external_dt, ist_month_start_utc

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ServerSelectionTimeoutError, AutoReconnect, PyMongoError

from app.config import settings
from app.core.logging import get_logger
from app.database import get_db
from app.services.dormancy_service import dormancy_service, normalize_phone_for_match

logger = get_logger(__name__)

# Constants for MongoDB operators to avoid duplication
REGEX = "$regex"
OPTIONS = "$options"
MATCH = "$match"
GROUP = "$group"
SORT = "$sort"
SUM = "$sum"
LIMIT = "$limit"
PROJECT = "$project"


class FieliaDatabaseError(RuntimeError):
    """Raised when the external Fielia database is unreachable."""
    pass


class FieliaMembersService:
    """Provides read access to the external Fielia NFC-card member database."""

    _client: AsyncIOMotorClient | None = None
    db_name = "test"
    collection_name = "cards"

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient | None:
        """Lazy-load the MongoDB client. Returns None if URI is missing."""
        if cls._client is None:
            uri = settings.fielia_mongo_uri
            if not uri:
                logger.warning(
                    "fielia_service_uri_missing",
                    msg="FIELIA_MONGO_URI is not configured. External members will not be available.",
                )
                return None
            try:
                cls._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            except (ServerSelectionTimeoutError, AutoReconnect, ValueError) as exc:
                logger.error("fielia_service_client_init_failed", error=str(exc))
                return None
            except PyMongoError as exc:
                logger.error("fielia_service_client_init_pymongo_error", error=str(exc))
                return None
        return cls._client

    @classmethod
    def get_db_handle(cls) -> AsyncIOMotorDatabase | None:
        """Return the Fielia database handle, or None if unavailable."""
        client = cls.get_client()
        if client is None:
            return None
        return client[cls.db_name]

    def _map_doc(self, doc: dict, activity: tuple | None = None) -> dict | None:
        """Normalize a Fielia document to the internal Member shape."""
        try:
            joined_at = self._normalize_dt(doc.get("createdAt"))
            internal_activity = self._normalize_dt(doc.get("updatedAt"))
            name = self._resolve_name(doc)

            last_visit_date, source = activity if activity else (None, None)
            status, fallback_source = dormancy_service.compute_status(last_visit_date, internal_activity)
            last_visit = last_visit_date or internal_activity

            return {
                "id": str(doc.get("_id")),
                "restaurant_id": "r2",
                "type": "nfc",
                "name": name,
                "phone": doc.get("phone") or "N/A",
                "email": doc.get("email"),
                "card_uid": doc.get("uuid"),
                "ecard_code": None,
                "joined_at": joined_at.isoformat() if joined_at else None,
                "visit_count": len(doc.get("scanHistory", [])),
                "points": 0,
                "last_visit": last_visit.isoformat() if last_visit else None,
                "is_active": True,
                "activity_status": status,
                "activity_source": source or fallback_source,
                "dormancy_tier": dormancy_service.get_tier(last_visit),
                "tags": [],
                "notes": doc.get("address", ""),
            }
        except Exception as exc:
            logger.error("fielia_doc_mapping_failed", doc_id=str(doc.get("_id")), error=str(exc))
            return None

    def _normalize_dt(self, dt: Any) -> datetime | None:
        """Normalize an externally sourced Fielia datetime to UTC-aware."""
        if isinstance(dt, datetime):
            return normalize_external_dt(dt)
        return None

    def _resolve_name(self, doc: dict) -> str:
        return (doc.get("content") or 
                f"{doc.get('firstName', '')} {doc.get('lastName', '')}".strip() or 
                "Unknown")

    def _build_search_query(self, search: str | None) -> dict:
        """Build a MongoDB query dict for a free-text search across name/phone fields."""
        if not search:
            return {}
        pattern = re.escape(search)
        return {
            "$or": [
                {"firstName": {REGEX: pattern, OPTIONS: "i"}},
                {"lastName": {REGEX: pattern, OPTIONS: "i"}},
                {"phone": {REGEX: pattern, OPTIONS: "i"}},
                {"content": {REGEX: pattern, OPTIONS: "i"}},
            ]
        }

    async def _resolve_activity_map(self, docs: list[dict]) -> dict:
        """Bulk-fetch ReserveGo activity for a list of Fielia docs."""
        db_main = get_db()
        phones = [d.get("phone") for d in docs]
        uuids = [d.get("uuid") for d in docs]
        return await dormancy_service.get_bulk_activity(db_main, "r2", phones, uuids)

    async def stream_all_members(
        self, search: str | None = None, member_type: str | None = None, batch_size: int = 200
    ) -> AsyncGenerator[dict, None]:
        """Async generator that streams all Fielia members in batches."""
        db_handle = self.get_db_handle()
        if db_handle is None or (member_type and member_type.lower() != "nfc"):
            return

        collection = db_handle[self.collection_name]
        query = self._build_search_query(search)
        batch = []

        try:
            async for doc in collection.find(query).sort("createdAt", -1):
                batch.append(doc)
                if len(batch) >= batch_size:
                    async for mapped in self._process_batch(batch):
                        yield mapped
                    batch = []
            if batch:
                async for mapped in self._process_batch(batch):
                    yield mapped
        except (ServerSelectionTimeoutError, AutoReconnect) as exc:
            logger.error("fielia_stream_members_failed", error=str(exc))
        except PyMongoError as exc:
            logger.exception("fielia_stream_members_pymongo_error")
        except Exception:
            logger.exception("fielia_stream_members_unexpected_error")

    async def _process_batch(self, batch: list[dict]) -> AsyncGenerator[dict, None]:
        """Process a batch of documents, enriching with activity."""
        activity_map = await self._resolve_activity_map(batch)
        for raw in batch:
            norm_phone = normalize_phone_for_match(raw.get("phone"))
            uuid_val = raw.get("uuid")
            activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
            mapped = self._map_doc(raw, activity)
            if mapped:
                yield mapped

    async def list_members(
        self, limit: int = 50, offset: int = 0, search: str | None = None, member_type: str | None = None
    ) -> dict:
        """Fetch a paginated members list from Fielia."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return {"items": [], "total": 0, "warning": "External member service not configured"}
        if member_type and member_type.lower() != "nfc":
            return {"items": [], "total": 0, "page": (offset // limit) + 1, "page_size": limit}

        try:
            collection = db_handle[self.collection_name]
            query = self._build_search_query(search)
            total = await collection.count_documents(query)
            docs = await collection.find(query).sort("createdAt", -1).skip(offset).limit(limit).to_list(limit)
            
            activity_map = await self._resolve_activity_map(docs)
            items = []
            for doc in docs:
                norm_phone = normalize_phone_for_match(doc.get("phone"))
                uuid_val = doc.get("uuid")
                activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
                mapped = self._map_doc(doc, activity)
                if mapped:
                    items.append(mapped)

            return {"items": items, "total": total, "page": (offset // limit) + 1, "page_size": limit}
        except (ServerSelectionTimeoutError, AutoReconnect) as exc:
            logger.error("fielia_list_members_failed", error=str(exc))
            return {"items": [], "total": 0, "warning": "External member service unavailable (Connection Error)"}
        except PyMongoError:
            logger.exception("fielia_list_members_pymongo_error")
            return {"items": [], "total": 0, "warning": "External member service unavailable"}
        except Exception:
            logger.exception("fielia_list_members_unexpected_error")
            return {"items": [], "total": 0, "warning": "External member service unavailable"}

    async def list_joined_between(
        self, from_dt: datetime, to_dt: datetime, limit: int = 20000
    ) -> list[dict]:
        """Return lightweight {phone, name, joined_at} rows for members who
        joined in a window. Used by acquisition attribution, which only needs
        each member's phone and join date — not the full mapped member shape.
        """
        db_handle = self.get_db_handle()
        if db_handle is None:
            return []

        try:
            cursor = (
                db_handle[self.collection_name]
                .find(
                    {"createdAt": {"$gte": from_dt, "$lte": to_dt}},
                    {"phone": 1, "createdAt": 1, "content": 1, "firstName": 1, "lastName": 1},
                )
                .sort("createdAt", -1)
                .limit(limit)
            )
            rows = []
            async for doc in cursor:
                joined_at = self._normalize_dt(doc.get("createdAt"))
                if not joined_at:
                    continue
                rows.append(
                    {
                        "phone": doc.get("phone"),
                        "name": self._resolve_name(doc),
                        "joined_at": joined_at,
                        "source": "nfc",
                    }
                )
            return rows
        except (ServerSelectionTimeoutError, AutoReconnect) as exc:
            logger.error("fielia_list_joined_between_failed", error=str(exc))
            return []
        except Exception:
            logger.exception("fielia_list_joined_between_unexpected_error")
            return []

    async def check_phone_exists(self, phone: str) -> bool:
        """Return True if a document with the given phone exists in Fielia."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return False
        try:
            doc = await db_handle[self.collection_name].find_one({"phone": phone}, {"_id": 1})
            return doc is not None
        except (ServerSelectionTimeoutError, AutoReconnect) as exc:
            logger.error("fielia_check_phone_failed", error=str(exc))
            # Fail closed: If we can't verify uniqueness, don't allow creation.
            raise FieliaDatabaseError("Fielia database unavailable for uniqueness check") from exc
        except Exception:
            logger.exception("fielia_check_phone_unexpected_error")
            return False

    async def get_summary(self, from_dt: datetime, to_dt: datetime) -> dict:
        """Fetch summary dashboard data from Fielia."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return self._empty_summary()

        try:
            col = db_handle[self.collection_name]
            growth = await self._get_growth_trend(col, from_dt, to_dt)
            counts = await self._get_scalar_counts(col)
            top = await self._get_top_visitors(col)

            return {
                "summary": counts,
                "monthly_growth": growth,
                "category_split": [{"category": "ecard", "count": counts["total_members"]}],
                "top_visitors": top,
            }
        except Exception as exc:
            logger.error("fielia_summary_failed", error=str(exc))
            return self._empty_summary()

    async def _get_growth_trend(self, collection: Any, from_dt: datetime, to_dt: datetime) -> List[Dict]:
        pipeline = [
            {MATCH: {"createdAt": {"$gte": from_dt, "$lte": to_dt}}},
            {GROUP: {"_id": {"year": {"$year": "$createdAt"}, "month": {"$month": "$createdAt"}}, "count": {SUM: 1}}},
            {SORT: {"_id.year": 1, "_id.month": 1}},
        ]
        raw = await collection.aggregate(pipeline).to_list(24)
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return [{"month": f"{month_names[r['_id']['month'] - 1]} {r['_id']['year']}", "new_members": r["count"]} 
                for r in raw]

    async def _get_scalar_counts(self, collection: Any) -> Dict:
        now = now_utc()
        month_start = ist_month_start_utc()
        dormant_cutoff = now - timedelta(days=30)

        total = await collection.count_documents({})
        new_this_month = await collection.count_documents({"createdAt": {"$gte": month_start}})
        dormant = await collection.count_documents({
            "$or": [{"updatedAt": {"$lt": dormant_cutoff}}, {"updatedAt": {"$exists": False}}]
        })
        return {
            "total_members": total,
            "active_members": total,
            "new_this_month": new_this_month,
            "dormant_members": dormant,
            "dormant_rate": round(dormant / total * 100, 1) if total else 0,
        }

    async def _get_top_visitors(self, collection: Any) -> List[Dict]:
        pipeline = [
            {"$addFields": {"visit_count": {"$size": {"$ifNull": ["$scanHistory", []]}}}},
            {SORT: {"visit_count": -1}},
            {LIMIT: 10},
        ]
        raw = await collection.aggregate(pipeline).to_list(10)
        items = []
        for doc in raw:
            m = self._map_doc(doc)
            if m:
                items.append({"name": m["name"], "phone": m["phone"], "type": m["type"], 
                             "visit_count": m["visit_count"], "last_visit": m["last_visit"]})
        return items

    def _empty_summary(self) -> dict:
        return {
            "summary": {"total_members": 0, "active_members": 0, "new_this_month": 0, "dormant_members": 0, "dormant_rate": 0},
            "monthly_growth": [], "category_split": [], "top_visitors": [],
            "warning": "External member service unavailable",
        }

    async def get_export_rows(self, from_dt: datetime, to_dt: datetime) -> list:
        """Fetch export rows from Fielia."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return []
        try:
            col = db_handle[self.collection_name]
            docs = await col.find({"createdAt": {"$gte": from_dt, "$lte": to_dt}}).sort("createdAt", -1).to_list(None)
            activity_map = await self._resolve_activity_map(docs)
            rows = []
            for doc in docs:
                m = self._map_doc(doc, activity_map.get(doc.get("uuid")) or activity_map.get(normalize_phone_for_match(doc.get("phone"))))
                if m:
                    rows.append([m["name"], m["phone"], m.get("email", ""), m["type"], m["joined_at"][:10] if m["joined_at"] else "",
                                m["visit_count"], m["last_visit"][:10] if m["last_visit"] else "", "Yes", doc.get("uuid", ""), "", "", doc.get("address", "")])
            return rows
        except Exception as exc:
            logger.error("fielia_export_failed", error=str(exc))
            return []


fielia_service = FieliaMembersService()
