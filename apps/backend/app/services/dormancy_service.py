from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Dict, List, Tuple, Any
from app.core.logging import get_logger

logger = get_logger(__name__)

# IST is UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)
REGEX = "$regex"


def normalize_phone_for_match(phone: str | None) -> str | None:
    """Standardize phone number to last 10 digits for matching.
    Returns None for inputs with fewer than 10 digits to avoid partial matches.
    """
    if not phone:
        return None
    # Remove all non-numeric characters
    clean = "".join(filter(str.isdigit, str(phone)))
    # Require at least 10 digits — short fragments cause false-positive matches
    return clean[-10:] if len(clean) >= 10 else None


class DormancyService:
    @staticmethod
    def get_ist_now() -> datetime:
        return datetime.now(timezone.utc) + IST_OFFSET

    async def get_bulk_activity(
        self,
        db: AsyncIOMotorDatabase,
        restaurant_id: str,
        member_phones: List[str],
        member_uuids: List[str],
    ) -> Dict[str, Tuple[datetime, str]]:
        """Fetch latest activity for a list of members from ReserveGo collections."""
        clean_phones = [p for p in [normalize_phone_for_match(ph) for ph in member_phones] if p]
        clean_uuids = [u for u in member_uuids if u]

        if not clean_phones and not clean_uuids:
            return {}

        activity_map = {}
        query = self._build_query(restaurant_id, clean_phones, clean_uuids)

        try:
            await self._process_collection(
                db.reservego_bill_data, query, clean_phones, clean_uuids, activity_map, "booking_time"
            )
            await self._process_collection(
                db.reservego_uploads, query, clean_phones, clean_uuids, activity_map, "uploaded_at"
            )
        except Exception as e:
            logger.error("dormancy_bulk_query_failed", error=str(e))

        return activity_map

    def _build_query(self, restaurant_id: str, clean_phones: List[str], clean_uuids: List[str]) -> dict:
        """Build the MongoDB query for activity lookup."""
        query = {"restaurant_id": restaurant_id}
        id_filters = []
        if clean_phones:
            # Wrap alternatives in a group so $ anchors every alternative
            id_filters.append({"phone": {REGEX: "(" + "|".join(clean_phones) + ")$"}})
        if clean_uuids:
            id_filters.append({"uuid": {"$in": clean_uuids}})
        if id_filters:
            query["$or"] = id_filters
        return query

    async def _process_collection(
        self, collection: Any, query: dict, clean_phones: List[str], clean_uuids: List[str], 
        activity_map: dict, sort_field: str
    ):
        """Helper to process activity from a specific collection."""
        cursor = collection.find(query).sort(sort_field, -1)
        async for doc in cursor:
            dt = self._extract_datetime(doc)
            if not dt:
                continue

            self._update_activity_map(doc, dt, clean_phones, clean_uuids, activity_map)

    def _extract_datetime(self, doc: dict) -> datetime | None:
        """Extract and normalize datetime from a document."""
        dt = doc.get("booking_time") or doc.get("last_visited_date") or doc.get("uploaded_at")
        if not dt:
            return None
        if isinstance(dt, str):
            try:
                return datetime.fromisoformat(dt)
            except ValueError:
                return None
        return dt

    def _update_activity_map(self, doc: dict, dt: datetime, clean_phones: List[str], 
                            clean_uuids: List[str], activity_map: dict):
        """Update the activity map with matches from a document."""
        # Check UUID match first (High confidence)
        uuid = doc.get("uuid")
        if uuid in clean_uuids:
            if uuid not in activity_map or dt > activity_map[uuid][0]:
                activity_map[uuid] = (dt, "uuid_match")

        # Check Phone match
        phone = normalize_phone_for_match(doc.get("phone"))
        if phone in clean_phones:
            if phone not in activity_map or dt > activity_map[phone][0]:
                activity_map[phone] = (dt, "phone_match")

    def compute_status(
        self, last_visit: datetime | None, internal_last_visit: datetime | None = None
    ) -> Tuple[str, str | None]:
        """Determine status and source."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if last_visit:
            status = self._get_status_for_date(last_visit, now)
            return status, None

        if internal_last_visit:
            status = self._get_status_for_date(internal_last_visit, now)
            return status, "fallback_internal"

        return "unknown", None

    def _get_status_for_date(self, dt: datetime, now: datetime) -> str:
        """Calculate active/dormant status based on date."""
        naive_dt = dt.replace(tzinfo=None)
        days_ago = (now - naive_dt).days
        return "active" if days_ago <= 30 else "dormant"


 dormancy_service = DormancyService()
