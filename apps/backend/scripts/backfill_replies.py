import asyncio
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse


REPLY_WINDOW_HOURS = 48


def normalize(p):
    if not p:
        return ""
    return "".join(filter(str.isdigit, str(p)))


def _parse_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    """Robustly extract the database name from any MongoDB URI."""
    try:
        parsed = urlparse(mongo_url)
        path = parsed.path.strip("/").split("?")[0].split("/")[0]
        return path if path else default
    except Exception:
        return default


async def _build_recipient_map(db) -> dict:
    """Build a normalized phone → sorted list of outbound logs map."""
    recipient_map: dict = {}
    async for log in db.message_logs.find():
        norm = normalize(log.get("recipient_phone"))
        if not norm:
            continue
        recipient_map.setdefault(norm, []).append(log)
    for logs in recipient_map.values():
        logs.sort(key=lambda x: x.get("created_at"))
    return recipient_map


def _find_best_match(
    recipient_map: dict, from_phone: str, received_at: datetime
) -> dict | None:
    """Return the latest unmatched outbound log within 48 hrs before received_at, or None."""
    if from_phone not in recipient_map:
        return None
    window_start = received_at - timedelta(hours=REPLY_WINDOW_HOURS)
    candidates = [
        log
        for log in recipient_map[from_phone]
        if not log.get("temp_replied")
        and log.get("created_at") is not None
        and window_start <= log["created_at"].replace(tzinfo=timezone.utc) < received_at
    ]
    return candidates[-1] if candidates else None


async def _process_inbound_message(
    db, recipient_map: dict, msg: dict, wa_message_logs: dict
) -> bool:
    """Match one inbound message to an outbound log and collect updates. Returns True if matched."""
    from_phone = normalize(msg.get("from_phone"))
    received_at = msg.get("received_at")
    if not from_phone or not received_at:
        return False

    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    # Prefer wa_message_id match (mirrors webhook_task.py logic)
    replied_to_wa_id = msg.get("raw_payload", {}).get("context", {}).get("id")
    best_match = None
    if replied_to_wa_id and replied_to_wa_id in wa_message_logs:
        candidate = wa_message_logs[replied_to_wa_id]
        if not candidate.get("temp_replied"):
            best_match = candidate

    if best_match is None:
        best_match = _find_best_match(recipient_map, from_phone, received_at)

    if best_match is None:
        return False

    best_match["temp_replied"] = True
    await db.message_logs.update_one(
        {"_id": best_match["_id"]}, {"$set": {"replied": True}}
    )
    if best_match.get("job_id"):
        await db.campaign_jobs.update_one(
            {"_id": best_match["job_id"]}, {"$inc": {"replies_count": 1}}
        )
    return True


async def backfill():
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGODB_URL", "mongodb://localhost:27017/restobuzz")
    db_name = _parse_db_name(mongo_url)
    client = AsyncIOMotorClient(mongo_url)
    db = client.get_database(db_name)
    print(f"Starting Robust Normalized Backfill on DB: {db_name}...")

    print("Building recipient map...")
    recipient_map = await _build_recipient_map(db)

    # Build wa_message_id → log lookup for direct-reply matching
    wa_message_logs: dict = {}
    for logs in recipient_map.values():
        for log in logs:
            wa_id = log.get("wa_message_id")
            if wa_id:
                wa_message_logs[wa_id] = log

    print("Processing inbound messages...")
    updated_messages = 0
    matched_log_ids = []
    job_increments: dict = {}

    async for msg in db.inbound_messages.find():
        from_phone = normalize(msg.get("from_phone"))
        received_at = msg.get("received_at")
        if not from_phone or not received_at:
            continue
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)

        replied_to_wa_id = msg.get("raw_payload", {}).get("context", {}).get("id")
        best_match = None
        if replied_to_wa_id and replied_to_wa_id in wa_message_logs:
            candidate = wa_message_logs[replied_to_wa_id]
            if not candidate.get("temp_replied"):
                best_match = candidate

        if best_match is None:
            best_match = _find_best_match(recipient_map, from_phone, received_at)

        if best_match is None:
            continue

        best_match["temp_replied"] = True
        matched_log_ids.append(best_match["_id"])
        if best_match.get("job_id"):
            job_id = best_match["job_id"]
            job_increments[job_id] = job_increments.get(job_id, 0) + 1
        updated_messages += 1

    # Apply all updates atomically after full scan
    print(f"Applying updates for {updated_messages} matched replies...")
    if matched_log_ids:
        await db.message_logs.update_many(
            {"_id": {"$in": matched_log_ids}}, {"$set": {"replied": True}}
        )
        await db.message_logs.update_many(
            {"_id": {"$nin": matched_log_ids}}, {"$set": {"replied": False}}
        )

    await db.campaign_jobs.update_many({}, {"$set": {"replies_count": 0}})
    for job_id, count in job_increments.items():
        await db.campaign_jobs.update_one(
            {"_id": job_id}, {"$set": {"replies_count": count}}
        )

    print(f"Backfill complete! Captured {updated_messages} unique campaign replies.")
    client.close()


if __name__ == "__main__":
    import sys

    if "--yes-really-reset" not in sys.argv:
        print(
            "Safety guard: this script rewrites replied flags and reply counts for ALL campaigns.\n"
            "Re-run with --yes-really-reset to confirm you intend to do this."
        )
        sys.exit(1)

    asyncio.run(backfill())
