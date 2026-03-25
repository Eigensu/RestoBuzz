"""
One-off script: send felia_image template to all numbers in a failed-numbers CSV.

Usage:
    cd apps/backend
    python -m scripts.send_failed_numbers \
        --csv /Volumes/External/Projects/WA-bullk-CRM/data/failed-numbers-3VZ4rZGG05sH.csv \
        --template felia_image \
        --image-url https://res.cloudinary.com/doyttqu8x/image/upload/v1774338751/whatsapp-media/xoygorfucrbeiws3c9o3.jpg
"""

import asyncio
import csv
import argparse
from datetime import datetime, timezone
from bson import ObjectId
from app.database import get_db
from app.workers.send_task import dispatch_campaign_task


async def main(csv_path: str, template_name: str, image_url: str) -> None:
    db = get_db()

    # Read phones from CSV
    phones = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            phone = row.get("phone", "").strip()
            if phone:
                phones.append(phone)

    print(f"Loaded {len(phones)} numbers from CSV")

    # Create campaign job
    now = datetime.now(timezone.utc)
    job = {
        "name": f"Retry failed - {template_name} - {now.strftime('%Y-%m-%d %H:%M')}",
        "template_name": template_name,
        "template_id": "",
        "priority": "MARKETING",
        "status": "queued",
        "total_count": len(phones),
        "sent_count": 0,
        "delivered_count": 0,
        "read_count": 0,
        "failed_count": 0,
        "scheduled_at": None,
        "started_at": None,
        "completed_at": None,
        "created_by": "script",
        "include_unsubscribe": False,
        "media_url": image_url,
        "created_at": now,
    }
    result = await db.campaign_jobs.insert_one(job)
    job_id = result.inserted_id
    print(f"Created campaign job: {job_id}")

    # Create message logs
    logs = [
        {
            "job_id": job_id,
            "recipient_phone": phone,
            "recipient_name": "",
            "template_name": template_name,
            "template_variables": {},
            "media_url": image_url,
            "status": "queued",
            "retry_count": 0,
            "endpoint_used": None,
            "fallback_used": False,
            "error_code": None,
            "error_message": None,
            "status_history": [],
            "created_at": now,
            "updated_at": now,
            "locked_until": None,
        }
        for phone in phones
    ]
    await db.message_logs.insert_many(logs)
    print(f"Created {len(logs)} message logs")

    # Dispatch via Celery
    dispatch_campaign_task.delay(str(job_id))
    print(f"Dispatched campaign job {job_id} to Celery")
    print(f"Monitor progress: check campaign_jobs collection or the dashboard")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--image-url", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.csv, args.template, args.image_url))
