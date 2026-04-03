# Campaign Retry Chain Migration

## Problem

Previously, retry campaigns were created with names like "Campaign Name (retry)" but weren't linked together in the database. This caused the dashboard's effective reach metric to be calculated incorrectly because:

1. Each retry campaign was counted as a separate campaign
2. The total audience was being counted multiple times
3. Failed counts weren't being properly tracked across the retry chain

## Solution

This migration script (`migrate_retry_campaigns.py`) identifies campaigns with "(retry)" in their names and links them together using the `parent_campaign_id` field.

After migration:

- Root campaigns have no `parent_campaign_id`
- Retry campaigns have `parent_campaign_id` pointing to the root campaign
- Dashboard calculates effective reach as: `(total_read / original_audience) * 100`
- Only the final campaign's `failed_count` is used (remaining failures after all retries)

## Running the Migration

```bash
cd apps/backend
python -m scripts.migrate_retry_campaigns
```

## What It Does

1. Scans all campaigns in the database
2. Groups campaigns by base name (removing "(retry)" suffixes)
3. For each group with retries:
   - Identifies the root campaign (earliest created_at)
   - Links all retry campaigns to the root using `parent_campaign_id`
4. Reports the number of campaigns updated

## Verification

After running, the script will show:

- Number of campaigns updated
- Total campaigns with `parent_campaign_id` set

You can also verify in the dashboard - the effective reach percentage should increase to reflect the true reach across retry chains.

## Frontend Changes

The dashboard (`app/(dashboard)/dashboard/page.tsx`) has been updated to:

1. Group campaigns by retry chains
2. Calculate totals by:
   - Using root campaign's `total_count` as audience (not summing retries)
   - Summing `sent`, `delivered`, `read` across the entire chain
   - Using the last campaign's `failed_count` (remaining failures)
3. Calculate effective reach as: `total_read / total_audience`

This ensures retry chains are treated as a single logical campaign for analytics purposes.
