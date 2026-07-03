#!/usr/bin/env python3
"""
Script to check smart retry status for campaigns.
Usage: python check_smart_retries.py [campaign_id]
"""
import asyncio
import sys
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from app.database import get_fresh_db


async def _show_campaign_detail(db, campaign_id_str: str) -> None:
    """Print smart-retry status and child campaigns for one campaign."""
    try:
        campaign_oid = ObjectId(campaign_id_str)
    except InvalidId:
        print(f"Invalid campaign ID: {campaign_id_str}")
        return

    campaign = await db.campaign_jobs.find_one({"_id": campaign_oid})
    if not campaign:
        print(f"Campaign not found: {campaign_id_str}")
        return

    print(f"\n=== Campaign: {campaign['name']} ===")
    print(f"ID: {campaign_id_str}")
    print(f"Status: {campaign['status']}")
    print(f"Smart Retries: {campaign.get('smart_retries', False)}")
    print(f"Failed Count: {campaign.get('failed_count', 0)}")
    print(f"Retry Until: {campaign.get('retry_until')}")
    print(f"Last Auto Retry: {campaign.get('last_auto_retry_at')}")
    print(f"Parent Campaign ID: {campaign.get('parent_campaign_id')}")

    # parent_campaign_id is always persisted as a string (campaign_service.py).
    children = [
        child
        async for child in db.campaign_jobs.find(
            {"parent_campaign_id": campaign_id_str}
        ).sort("created_at", 1)
    ]

    if not children:
        print("\n=== No child retry campaigns found ===")
        return

    print(f"\n=== Child Retry Campaigns ({len(children)}) ===")
    for i, child in enumerate(children, 1):
        print(f"\n  #{i} - {child['name']}")
        print(f"  ID: {child['_id']}")
        print(f"  Created: {child.get('created_at')}")
        print(f"  Status: {child['status']}")
        print(f"  Total: {child.get('total_count', 0)}")
        print(f"  Sent: {child.get('sent_count', 0)}")
        print(f"  Delivered: {child.get('delivered_count', 0)}")
        print(f"  Failed: {child.get('failed_count', 0)}")


def _format_retry_age(now: datetime, last_auto_retry_at) -> str:
    if not last_auto_retry_at:
        return ""
    hours = (now - last_auto_retry_at).total_seconds() / 3600
    return f" (last retry {hours:.1f}h ago)"


def _format_deadline(now: datetime, retry_until) -> str:
    if not retry_until:
        return ""
    if retry_until > now:
        hours_left = (retry_until - now).total_seconds() / 3600
        return f"⏰ {hours_left:.1f}h left"
    return "❌ expired"


async def _list_active_smart_retries(db) -> None:
    """List all root (non-child) smart-retry campaigns and their progress."""
    now = datetime.now(timezone.utc)

    print("\n=== Active Smart Retry Campaigns ===\n")
    cursor = db.campaign_jobs.find(
        {
            "smart_retries": True,
            "parent_campaign_id": None,  # Only show parent campaigns
        }
    ).sort("created_at", -1)

    count = 0
    async for campaign in cursor:
        count += 1
        campaign_id = str(campaign["_id"])
        child_count = await db.campaign_jobs.count_documents(
            {"parent_campaign_id": campaign_id}
        )
        time_since_retry = _format_retry_age(now, campaign.get("last_auto_retry_at"))
        deadline_status = _format_deadline(now, campaign.get("retry_until"))

        print(f"{count}. {campaign['name']}")
        print(f"   ID: {campaign_id}")
        print(
            f"   Status: {campaign['status']} | Failed: {campaign.get('failed_count', 0)}"
        )
        print(f"   Auto-retries done: {child_count}{time_since_retry}")
        print(f"   Deadline: {deadline_status}")
        print()

    if count == 0:
        print("No smart retry campaigns found.")


async def check_campaign_retries(campaign_id_str: str = None):
    db = get_fresh_db()
    try:
        if campaign_id_str:
            await _show_campaign_detail(db, campaign_id_str)
        else:
            await _list_active_smart_retries(db)
    finally:
        db.client.close()


if __name__ == "__main__":
    campaign_id = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(check_campaign_retries(campaign_id))
