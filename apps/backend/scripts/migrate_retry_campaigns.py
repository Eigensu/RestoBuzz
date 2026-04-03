"""
Migration script to link old retry campaigns into parent-child chains.

This script identifies campaigns that follow the old retry naming pattern
(e.g., "Campaign Name (retry)", "Campaign Name (retry) (retry)")
and links them together using the parent_campaign_id field.

This ensures the dashboard calculates effective reach correctly by treating
retry chains as a single logical campaign.
"""

import asyncio
import re
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def migrate_retry_campaigns():
    """
    Find campaigns with '(retry)' in their name and link them to their parent.
    """
    from app.config import settings

    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    print("🔍 Scanning for retry campaigns...")

    # Find all campaigns
    all_campaigns = await db.campaign_jobs.find({}).sort("created_at", 1).to_list(None)

    # Group campaigns by base name (removing retry suffixes)
    campaign_groups = {}
    # Simple pattern to avoid ReDoS - matches " (retry) " with optional spaces
    retry_pattern = re.compile(r" ?\(retry\) ?", re.IGNORECASE)

    for campaign in all_campaigns:
        name = campaign.get("name", "")
        # Remove all (retry) suffixes to get base name
        base_name = retry_pattern.sub("", name).strip()

        if base_name not in campaign_groups:
            campaign_groups[base_name] = []

        campaign_groups[base_name].append(campaign)

    # Process each group
    total_updated = 0

    for base_name, group in campaign_groups.items():
        if len(group) <= 1:
            continue  # No retries for this campaign

        # Sort by created_at to establish order
        group.sort(key=lambda c: c["created_at"])

        # Check if any have '(retry)' in the name
        has_retry = any("retry" in c.get("name", "").lower() for c in group)

        if not has_retry:
            continue  # Not a retry chain

        print(f"\n📦 Processing retry chain: {base_name}")
        print(f"   Found {len(group)} campaigns in chain")

        # First campaign is the root
        root = group[0]
        root_id = root["_id"]

        # Check if root already has parent_campaign_id (shouldn't happen)
        if root.get("parent_campaign_id"):
            print("   ⚠️  Root campaign already has parent_campaign_id, skipping")
            continue

        # Update all retry campaigns to point to root
        for i, campaign in enumerate(group[1:], start=1):
            campaign_id = campaign["_id"]
            current_parent = campaign.get("parent_campaign_id")

            if current_parent == root_id:
                print(f"   ✓ Campaign {i} already linked")
                continue

            # Update the campaign
            result = await db.campaign_jobs.update_one(
                {"_id": campaign_id}, {"$set": {"parent_campaign_id": root_id}}
            )

            campaign_name = campaign.get("name", "Unknown")
            if result.modified_count > 0:
                print(f"   ✓ Linked campaign {i}: {campaign_name}")
                total_updated += 1
            else:
                print(f"   ⚠️  Failed to link campaign {i}")

    print(f"\n✅ Migration complete! Updated {total_updated} campaigns")

    # Verify the results
    print("\n📊 Verification:")
    retry_campaigns = await db.campaign_jobs.count_documents(
        {"parent_campaign_id": {"$exists": True}}
    )
    print(f"   Total campaigns with parent_campaign_id: {retry_campaigns}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(migrate_retry_campaigns())
