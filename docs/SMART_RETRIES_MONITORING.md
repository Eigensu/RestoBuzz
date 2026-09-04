# Smart Retries Monitoring Guide

## Overview

Smart retries automatically retry failed messages from WhatsApp campaigns every **4 hours** until a specified deadline (`retry_until`). This document explains how the system works and how to monitor it.

---

## How Smart Retries Work

### 1. **Setup**

When creating a campaign, enable smart retries by setting:

- `smart_retries: true`
- `retry_until: <deadline datetime>` (up to 30 days in the future)

### 2. **Automatic Retry Cycle**

- A Celery Beat task (`poll-smart-retries-every-15m`) runs **every 15 minutes**
- It finds campaigns eligible for retry:
  - Smart retries enabled
  - Status is `completed` or `failed`
  - Has failed messages (`failed_count > 0`)
  - Deadline (`retry_until`) is still in the future
  - **Either:**
    - Never auto-retried before (`last_auto_retry_at` missing)
    - OR last auto-retry was more than 4 hours ago

### 3. **Retry Execution**

When a campaign is eligible:

1. The poller atomically updates `last_auto_retry_at` to current time (prevents duplicate retries)
2. Creates a child retry campaign containing only the failed messages
3. Dispatches the child campaign to Celery queue
4. Process repeats every 4 hours until:
   - No more failed messages remain, OR
   - The `retry_until` deadline is reached

---

## Monitoring Methods

### Method 1: API Endpoint (Recommended)

A new endpoint provides real-time smart retry status:

```bash
GET /api/campaigns/{campaign_id}/smart-retry-status
```

**Response Example:**

```json
{
  "campaign_id": "507f1f77bcf86cd799439011",
  "campaign_name": "Soraia Campaign",
  "smart_retries_enabled": true,
  "status": "completed",
  "failed_count": 25,
  "retry_until": "2026-06-10T15:00:00Z",
  "last_auto_retry_at": "2026-06-06T12:00:00Z",
  "last_retry_seconds_ago": 14400,
  "next_retry_at": "2026-06-06T16:00:00Z",
  "next_retry_in_seconds": 0,
  "deadline_in_seconds": 345600,
  "is_eligible_for_retry": true,
  "reason_not_eligible": null,
  "retry_chain": [
    {
      "id": "507f1f77bcf86cd799439011",
      "name": "Soraia Campaign",
      "status": "completed",
      "created_at": "2026-06-06T10:00:00Z",
      "total_count": 100,
      "sent_count": 75,
      "delivered_count": 70,
      "failed_count": 25,
      "is_root": true
    },
    {
      "id": "507f1f77bcf86cd799439012",
      "name": "Soraia Campaign (retry)",
      "status": "completed",
      "created_at": "2026-06-06T12:00:00Z",
      "total_count": 25,
      "sent_count": 18,
      "delivered_count": 16,
      "failed_count": 7,
      "is_root": false
    }
  ],
  "total_retries": 1,
  "poller_frequency": "Every 15 minutes",
  "retry_interval": "Every 4 hours"
}
```

**Key Fields:**

- `is_eligible_for_retry`: Whether the campaign will retry again
- `reason_not_eligible`: Why it won't retry (if applicable)
- `next_retry_in_seconds`: How long until next retry (0 = will retry on next poll)
- `last_retry_seconds_ago`: Time since last auto-retry (14400 = 4 hours)
- `retry_chain`: All campaigns in the retry chain (root + children)
- `total_retries`: Number of auto-retries that have been executed

### Method 2: Python Script

Use the included monitoring script:

```bash
cd apps/backend

# List all smart retry campaigns
python check_smart_retries.py

# Check specific campaign
python check_smart_retries.py 507f1f77bcf86cd799439011
```

**Output Example:**

```text
=== Campaign: Soraia Campaign ===
ID: 507f1f77bcf86cd799439011
Status: completed
Smart Retries: True
Failed Count: 7
Retry Until: 2026-06-10 15:00:00+00:00
Last Auto Retry: 2026-06-06 12:00:00+00:00
Parent Campaign ID: None

=== Child Retry Campaigns (1) ===

  #1 - Soraia Campaign (retry)
  ID: 507f1f77bcf86cd799439012
  Created: 2026-06-06 12:00:00+00:00
  Status: completed
  Total: 25
  Sent: 18
  Delivered: 16
  Failed: 7
```

### Method 3: MongoDB Direct Query

Query the database directly:

```javascript
// Find all smart retry campaigns
db.campaign_jobs
  .find({
    smart_retries: true,
    parent_campaign_id: null, // Only root campaigns
  })
  .sort({ created_at: -1 });

// Check specific campaign's retry history
db.campaign_jobs
  .find({
    $or: [
      { _id: ObjectId("507f1f77bcf86cd799439011") },
      { parent_campaign_id: "507f1f77bcf86cd799439011" },
    ],
  })
  .sort({ created_at: 1 });
```

### Method 4: Log Analysis

Check Celery worker logs for smart retry activity:

```bash
# On Railway or local logs
grep "smart_retry" celery_worker.log

# Expected log entries:
# - smart_retry_dispatched: Retry campaign created and dispatched
# - smart_retry_skipped_no_failures: Campaign had no failures
# - smart_retry_dispatch_failed: Error creating retry campaign
```

**Log Example:**

```json
{
  "level": "info",
  "message": "smart_retry_dispatched",
  "parent_job_id": "507f1f77bcf86cd799439011",
  "child_job_id": "507f1f77bcf86cd799439012",
  "failed_count": 25,
  "timestamp": "2026-06-06T12:00:00Z"
}
```

---

## Key Database Fields

### Campaign Document Fields

| Field                | Type            | Description                             |
| -------------------- | --------------- | --------------------------------------- |
| `smart_retries`      | Boolean         | Whether smart retries are enabled       |
| `retry_until`        | DateTime        | Deadline for auto-retries               |
| `last_auto_retry_at` | DateTime        | When the last auto-retry was dispatched |
| `parent_campaign_id` | String/ObjectId | ID of root campaign (for child retries) |
| `has_been_retried`   | Boolean         | ⚠️ **Deprecated** - no longer used      |
| `failed_count`       | Number          | Current count of failed messages        |

### Important Notes

1. **`last_auto_retry_at` is the key field** - indicates when last retry happened
2. **`has_been_retried` is deprecated** - ignored by the poller (old logic that caused single-retry bug)
3. **Child campaigns inherit** `smart_retries` and `retry_until` from parent
4. **All retries point to the same root** via `parent_campaign_id`

---

## Troubleshooting

### Campaign Not Retrying

**Check the API endpoint** to see why:

```bash
curl https://buzz-api.eigensu.in/api/campaigns/{id}/smart-retry-status
```

Look at `is_eligible_for_retry` and `reason_not_eligible` fields.

**Common reasons:**

- ❌ `"No retry_until deadline set"` → Smart retries misconfigured
- ❌ `"Retry deadline has passed"` → Past the deadline
- ❌ `"No failed messages to retry"` → All messages succeeded
- ❌ `"Campaign status is 'running'"` → Wait for campaign to complete
- ❌ `"Smart retries not enabled for this campaign"` → Campaign created without smart retries

### Verifying Poller is Running

```bash
# Check Celery Beat schedule
celery -A app.workers.celery_app inspect scheduled

# Expected output should include:
# - poll-smart-retries-every-15m
```

### Manual Retry vs Auto Retry

- **Manual retry:** User clicks "Retry Failed" button → creates child campaign immediately
- **Auto retry:** System creates child campaigns every 4 hours until deadline

Both use the same `create_child_retry_campaign` function but:

- Auto retries update `last_auto_retry_at`
- Manual retries don't affect auto retry timing

---

## Deployment Status

✅ **Smart retry poller code is READY** in `smart_retries_poller.py`  
⚠️ **Deployment needed:** The updated code must be deployed to Railway (both API and celery-worker services)

### Deploy Command

```bash
# The code has been fixed but needs deployment
# Railway auto-deploys on git push to main branch

# Or manually trigger via Railway CLI:
railway up --service api
railway up --service celery-worker
```

---

## Testing Smart Retries

### Create a Test Campaign

```bash
# 1. Create campaign with smart retries
POST /api/campaigns
{
  "restaurant_id": "r1",
  "name": "Test Smart Retry",
  "template_name": "test_template",
  "smart_retries": true,
  "retry_until": "2026-06-10T00:00:00Z",  # 4 days from now
  "contact_file_ref": "..."
}

# 2. Start campaign
POST /api/campaigns/{id}/start

# 3. Wait for campaign to complete with some failures

# 4. Monitor retry status
GET /api/campaigns/{id}/smart-retry-status

# 5. Wait 2+ hours and check again
# Should see new child campaign in retry_chain

# 6. Repeat every 4 hours until deadline
```

### Expected Behavior

- **T+0min:** Campaign completes with 10 failures
- **T+15min:** First auto-retry created (poller runs)
- **T+2h15min:** Second auto-retry created (if still have failures)
- **T+4h15min:** Third auto-retry created (if still have failures)
- **T+deadline:** No more retries even if failures remain

---

## Frontend Integration (TODO)

Add smart retry status display to campaign detail page:

```typescript
// In campaigns/whatsapp/[id]/page.tsx

const { data: retryStatus } = useQuery({
  queryKey: ["smart-retry-status", id],
  queryFn: () =>
    api.get(`/campaigns/${id}/smart-retry-status`).then((r) => r.data),
  enabled: !!campaign?.smart_retries,
  refetchInterval: 60000, // Refresh every minute
});

// Display:
// - Next retry in: {formatSeconds(retryStatus.next_retry_in_seconds)}
// - Total retries: {retryStatus.total_retries}
// - Deadline in: {formatSeconds(retryStatus.deadline_in_seconds)}
```

---

## Summary

✅ **Smart retries work by:**

1. Celery Beat runs poller every 15 minutes
2. Poller finds eligible campaigns (2+ hours since last retry, before deadline, has failures)
3. Creates child campaign with failed messages
4. Updates `last_auto_retry_at` to prevent duplicate retries
5. Repeats every 4 hours

✅ **Monitor via:**

- API endpoint: `/api/campaigns/{id}/smart-retry-status`
- Python script: `check_smart_retries.py`
- MongoDB: Check `last_auto_retry_at` and `retry_chain`
- Logs: Search for `smart_retry_dispatched`

✅ **Key field:** `last_auto_retry_at` (when last retry happened)
