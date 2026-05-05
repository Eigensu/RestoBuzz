"""Service for accessing the external Fielia (NFC card) MongoDB database."""

import json
import re
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.core.logging import get_logger
from app.database import get_db
from app.services.dormancy_service import dormancy_service, normalize_phone_for_match

logger = get_logger(__name__)


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
                    msg="FIELIA_MONGO_URI is not configured. "
                    "External members will not be available.",
                )
                return None
            try:
                cls._client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
            except (ConnectionError, ValueError) as exc:
                logger.error("fielia_service_client_init_failed", error=str(exc))
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
            joined_at = doc.get("createdAt")
            if isinstance(joined_at, datetime):
                joined_at = joined_at.replace(tzinfo=timezone.utc)

            internal_activity = doc.get("updatedAt")
            if isinstance(internal_activity, datetime):
                internal_activity = internal_activity.replace(tzinfo=timezone.utc)

            name = (
                doc.get("content")
                or (f"{doc.get('firstName', '')} {doc.get('lastName', '')}".strip())
                or "Unknown"
            )

            last_visit_date, source = None, None
            if activity:
                last_visit_date, source = activity

            status, fallback_source = dormancy_service.compute_status(
                last_visit_date, internal_activity
            )

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
                "tags": [],
                "notes": doc.get("address", ""),
            }
        except (KeyError, TypeError, AttributeError) as exc:
            logger.error(
                "fielia_doc_mapping_failed",
                doc_id=str(doc.get("_id")),
                error=str(exc),
            )
            return None

    def _build_search_query(self, search: str | None) -> dict:
        """Build a MongoDB query dict for a free-text search across name/phone fields."""
        if not search:
            return {}
        pattern = re.escape(search)
        return {
            "$or": [
                {"firstName": {"$regex": pattern, "$options": "i"}},
                {"lastName": {"$regex": pattern, "$options": "i"}},
                {"phone": {"$regex": pattern, "$options": "i"}},
                {"content": {"$regex": pattern, "$options": "i"}},
            ]
        }

    async def _resolve_activity_map(self, docs: list[dict]) -> dict:
        """Bulk-fetch ReserveGo activity for a list of Fielia docs."""
        db_main = get_db()
        phones = [d.get("phone") for d in docs]
        uuids = [d.get("uuid") for d in docs]
        return await dormancy_service.get_bulk_activity(db_main, "r2", phones, uuids)

    async def stream_all_members(
        self,
        search: str | None = None,
        member_type: str | None = None,
        batch_size: int = 200,
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator that streams all Fielia members in batches of `batch_size`.

        Memory usage stays flat regardless of collection size — one batch of docs
        is held at a time, with a single bulk activity lookup per batch.
        Suitable for large-scale operations like campaign contact building.
        """
        db_handle = self.get_db_handle()
        if db_handle is None:
            logger.warning("fielia_stream_skipped", reason="client not configured")
            return

        if member_type and member_type.lower() != "nfc":
            return  # Fielia only holds NFC members

        collection = db_handle[self.collection_name]
        query = self._build_search_query(search)
        batch: list[dict] = []

        try:
            async for doc in collection.find(query).sort("createdAt", -1):
                batch.append(doc)
                if len(batch) >= batch_size:
                    activity_map = await self._resolve_activity_map(batch)
                    for raw in batch:
                        norm_phone = normalize_phone_for_match(raw.get("phone"))
                        uuid_val = raw.get("uuid")
                        activity = activity_map.get(uuid_val) or activity_map.get(
                            norm_phone
                        )
                        mapped = self._map_doc(raw, activity)
                        if mapped:
                            yield mapped
                    batch = []

            # Flush the final partial batch
            if batch:
                activity_map = await self._resolve_activity_map(batch)
                for raw in batch:
                    norm_phone = normalize_phone_for_match(raw.get("phone"))
                    uuid_val = raw.get("uuid")
                    activity = activity_map.get(uuid_val) or activity_map.get(
                        norm_phone
                    )
                    mapped = self._map_doc(raw, activity)
                    if mapped:
                        yield mapped

        except (ConnectionError, TimeoutError) as exc:
            logger.error("fielia_stream_members_failed", error=str(exc))

    async def list_members(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
        member_type: str | None = None,
    ) -> dict:
        """Fetch a paginated members list from Fielia. Returns empty result on failure."""
        page = (offset // limit) + 1

        db_handle = self.get_db_handle()
        if db_handle is None:
            return {
                "items": [],
                "total": 0,
                "warning": "External member service not configured",
            }

        if member_type and member_type.lower() != "nfc":
            return {"items": [], "total": 0, "page": page, "page_size": limit}

        try:
            collection = db_handle[self.collection_name]
            query = self._build_search_query(search)

            total = await collection.count_documents(query)
            docs = await (
                collection.find(query)
                .sort("createdAt", -1)
                .skip(offset)
                .limit(limit)
                .to_list(length=limit)
            )

            activity_map = await self._resolve_activity_map(docs)
            items = []
            for doc in docs:
                norm_phone = normalize_phone_for_match(doc.get("phone"))
                uuid_val = doc.get("uuid")
                activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
                mapped = self._map_doc(doc, activity)
                if mapped:
                    items.append(mapped)

            return {"items": items, "total": total, "page": page, "page_size": limit}

        except (ConnectionError, TimeoutError) as exc:
            logger.error("fielia_list_members_failed", error=str(exc))
            return {
                "items": [],
                "total": 0,
                "warning": "External member service unavailable",
            }

    async def check_phone_exists(self, phone: str) -> bool:
        """Return True if a document with the given phone exists in Fielia."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return False
        try:
            collection = db_handle[self.collection_name]
            doc = await collection.find_one({"phone": phone}, {"_id": 1})
            return doc is not None
        except (ConnectionError, TimeoutError) as exc:
            logger.error("fielia_check_phone_failed", error=str(exc))
            return False

    async def get_summary(self, from_dt: datetime, to_dt: datetime) -> dict:
        """Fetch summary dashboard data from Fielia. Returns empty summary on failure."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return self._empty_summary()

        try:
            collection = db_handle[self.collection_name]

            pipeline = [
                {"$match": {"createdAt": {"$gte": from_dt, "$lte": to_dt}}},
                {
                    "$group": {
                        "_id": {
                            "year": {"$year": "$createdAt"},
                            "month": {"$month": "$createdAt"},
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"_id.year": 1, "_id.month": 1}},
            ]
            growth_raw = await collection.aggregate(pipeline).to_list(24)

            month_names = [
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ]
            monthly_growth = [
                {
                    "month": (
                        f"{month_names[r['_id']['month'] - 1]} {r['_id']['year']}"
                    ),
                    "new_members": r["count"],
                }
                for r in growth_raw
            ]

            now = datetime.now(timezone.utc)
            month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
            dormant_cutoff = now - timedelta(days=30)

            total_all = await collection.count_documents({})
            new_this_month = await collection.count_documents(
                {"createdAt": {"$gte": month_start}}
            )
            dormant = await collection.count_documents(
                {
                    "$or": [
                        {"updatedAt": {"$lt": dormant_cutoff}},
                        {"updatedAt": {"$exists": False}},
                    ]
                }
            )

            top_visitors_raw = await collection.aggregate(
                [
                    {
                        "$addFields": {
                            "visit_count": {"$size": {"$ifNull": ["$scanHistory", []]}}
                        }
                    },
                    {"$sort": {"visit_count": -1}},
                    {"$limit": 10},
                ]
            ).to_list(10)

            top_visitors = []
            for doc in top_visitors_raw:
                mapped = self._map_doc(doc)
                if mapped:
                    top_visitors.append(
                        {
                            "name": mapped["name"],
                            "phone": mapped["phone"],
                            "type": mapped["type"],
                            "visit_count": mapped["visit_count"],
                            "last_visit": mapped["last_visit"],
                        }
                    )

            dormant_rate = round(dormant / total_all * 100, 1) if total_all else 0
            return {
                "summary": {
                    "total_members": total_all,
                    "active_members": total_all,
                    "new_this_month": new_this_month,
                    "dormant_members": dormant,
                    "dormant_rate": dormant_rate,
                },
                "monthly_growth": monthly_growth,
                "category_split": [{"category": "ecard", "count": total_all}],
                "top_visitors": top_visitors,
            }
        except (ConnectionError, TimeoutError) as exc:
            logger.error("fielia_summary_failed", error=str(exc))
            return self._empty_summary()

    def _empty_summary(self) -> dict:
        return {
            "summary": {
                "total_members": 0,
                "active_members": 0,
                "new_this_month": 0,
                "dormant_members": 0,
                "dormant_rate": 0,
            },
            "monthly_growth": [],
            "category_split": [],
            "top_visitors": [],
            "warning": "External member service unavailable",
        }

    async def get_export_rows(self, from_dt: datetime, to_dt: datetime) -> list:
        """Fetch export rows from Fielia for a given date range, with activity enrichment."""
        db_handle = self.get_db_handle()
        if db_handle is None:
            return []

        try:
            collection = db_handle[self.collection_name]
            query = {"createdAt": {"$gte": from_dt, "$lte": to_dt}}
            docs = (
                await collection.find(query).sort("createdAt", -1).to_list(length=None)
            )

            # Enrich with ReserveGo activity — same as list_members
            activity_map = await self._resolve_activity_map(docs)

            rows = []
            for doc in docs:
                norm_phone = normalize_phone_for_match(doc.get("phone"))
                uuid_val = doc.get("uuid")
                activity = activity_map.get(uuid_val) or activity_map.get(norm_phone)
                mapped = self._map_doc(doc, activity)
                if mapped:
                    rows.append(
                        [
                            mapped["name"],
                            mapped["phone"],
                            mapped.get("email", ""),
                            mapped["type"],
                            mapped["joined_at"][:10] if mapped["joined_at"] else "",
                            mapped["visit_count"],
                            mapped["last_visit"][:10] if mapped["last_visit"] else "",
                            "Yes",
                            doc.get("uuid", ""),
                            "",
                            "",
                            doc.get("address", ""),
                        ]
                    )
            return rows
        except (ConnectionError, TimeoutError) as exc:
            logger.error("fielia_export_failed", error=str(exc))
            return []


fielia_service = FieliaMembersService()
