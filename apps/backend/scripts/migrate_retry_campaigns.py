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
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId


async def process_chain(db, base_name, group):
    print(f"\n📦 Processing retry chain: {base_name}")
    print(f"   Found {len(group)} campaigns in chain")
    
    root = group[0]
    root_id = root["_id"]
    
    if root.get("parent_campaign_id"):
        print("   ⚠️  Root campaign already has parent_campaign_id, skipping")
        return 0
    
    updated = 0
    for i, campaign in enumerate(group[1:], start=1):
        if campaign.get("parent_campaign_id") == root_id:
            print(f"   ✓ Campaign {i} already linked")
            continue
        
        result = await db.campaign_jobs.update_one(
            {"_id": campaign["_id"]},
            {"$set": {"parent_campaign_id": root_id}}
        )
        
        if result.modified_count > 0:
            print(f"   ✓ Linked campaign {i}: {campaign.get('name')}")
            updated += 1
        else:
            print(f"   ⚠️  Failed to link campaign {i}")
            
    return updated

async def migrate_retry_campaigns():
    """
    Find campaigns with '(retry)' in their name and link them to their parent.
    """
    from app.config import settings
    
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    
    print("🔍 Scanning for retry campaigns...")
    all_campaigns = await db.campaign_jobs.find({}).sort("created_at", 1).to_list(None)
    
    campaign_groups = {}
    retry_pattern = re.compile(r'\s*\(retry\)\s*', re.IGNORECASE)
    
    for campaign in all_campaigns:
        base_name = retry_pattern.sub("", campaign.get("name", "")).strip()
        campaign_groups.setdefault(base_name, []).append(campaign)
    
    total_updated = 0
    for base_name, group in campaign_groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda c: c["created_at"])
        if not any("retry" in c.get("name", "").lower() for c in group):
            continue
        
        total_updated += await process_chain(db, base_name, group)
    
    print(f"\n✅ Migration complete! Updated {total_updated} campaigns")
    
    # Verify the results
    print("\n📊 Verification:")
    retry_campaigns_count = await db.campaign_jobs.count_documents({
        "parent_campaign_id": {"$exists": True}
    })
    print(f"   Total campaigns with parent_campaign_id: {retry_campaigns_count}")
    
    await client.close()


if __name__ == "__main__":
    asyncio.run(migrate_retry_campaigns())
