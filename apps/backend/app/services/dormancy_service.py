from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Dict, List, Tuple
from app.core.logging import get_logger

logger = get_logger(__name__)

# IST is UTC + 5:30
IST_OFFSET = timedelta(hours=5, minutes=30)

def normalize_phone_for_match(phone: str | None) -> str | None:
    """Standardize phone number to last 10 digits for matching."""
    if not phone:
        return None
    # Remove all non-numeric characters
    clean = "".join(filter(str.isdigit, str(phone)))
    # Return last 10 digits
    return clean[-10:] if len(clean) >= 10 else clean

class DormancyService:
    @staticmethod
    def get_ist_now() -> datetime:
        return datetime.now(timezone.utc) + IST_OFFSET

    async def get_bulk_activity(
        self, 
        db: AsyncIOMotorDatabase, 
        restaurant_id: str, 
        member_phones: List[str], 
        member_uuids: List[str]
    ) -> Dict[str, Tuple[datetime, str]]:
        """
        Fetch latest activity for a list of members from ReserveGo collections.
        Returns a map of (phone_or_uuid -> (latest_date, source))
        """
        activity_map = {}
        
        # 1. Clean and normalize inputs
        clean_phones = [p for p in [normalize_phone_for_match(ph) for ph in member_phones] if p]
        clean_uuids = [u for u in member_uuids if u]

        if not clean_phones and not clean_uuids:
            return {}

        try:
            # 2. Query reservego_bill_data (Most reliable behavioral source)
            query = {"restaurant_id": restaurant_id}
            id_filters = []
            if clean_phones:
                # We need to match the stored phone which might be in different formats
                # For now, we search for phones ending with our clean 10 digits
                id_filters.append({"phone": {"$regex": f"{'|'.join(clean_phones)}$"}})
            if clean_uuids:
                id_filters.append({"uuid": {"$in": clean_uuids}})
            
            if id_filters:
                query["$or"] = id_filters

            cursor = db.reservego_bill_data.find(
                query, 
                {"phone": 1, "uuid": 1, "booking_time": 1}
            ).sort("booking_time", -1)
            
            async for doc in cursor:
                dt = doc.get("booking_time")
                if not dt: continue
                if isinstance(dt, str): dt = datetime.fromisoformat(dt)
                
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

            # 3. Query reservego_uploads (Secondary source)
            # Similar logic as above...
            upload_cursor = db.reservego_uploads.find(
                query,
                {"phone": 1, "uuid": 1, "last_visited_date": 1, "uploaded_at": 1}
            ).sort("uploaded_at", -1)

            async for doc in upload_cursor:
                dt = doc.get("last_visited_date") or doc.get("uploaded_at")
                if not dt: continue
                if isinstance(dt, str): dt = datetime.fromisoformat(dt)

                uuid = doc.get("uuid")
                if uuid in clean_uuids:
                    if uuid not in activity_map or dt > activity_map[uuid][0]:
                        activity_map[uuid] = (dt, "uuid_match")
                
                phone = normalize_phone_for_match(doc.get("phone"))
                if phone in clean_phones:
                    if phone not in activity_map or dt > activity_map[phone][0]:
                        activity_map[phone] = (dt, "phone_match")

        except Exception as e:
            logger.error("dormancy_bulk_query_failed", error=str(e))

        return activity_map

    def compute_status(
        self, 
        last_visit: datetime | None, 
        internal_last_visit: datetime | None = None
    ) -> Tuple[str, str | None]:
        """Determine status and source."""
        # Get current time as naive (representing UTC)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Priority 1: ReserveGo activity
        if last_visit:
            # Ensure last_visit is naive for comparison
            lv_naive = last_visit.replace(tzinfo=None)
            days_ago = (now - lv_naive).days
            status = "active" if days_ago <= 30 else "dormant"
            return status, None 

        # Priority 2: Fallback to internal member record
        if internal_last_visit:
            iv_naive = internal_last_visit.replace(tzinfo=None)
            days_ago = (now - iv_naive).days
            status = "active" if days_ago <= 30 else "dormant"
            return status, "fallback_internal"

        return "unknown", None

dormancy_service = DormancyService()
