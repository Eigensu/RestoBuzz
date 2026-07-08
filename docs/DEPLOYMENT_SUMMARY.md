# Deployment Summary - Smart Retries Monitoring

## Date: June 6, 2026

## What Was Added

### 1. **New API Endpoint: Smart Retry Status**

**Endpoint:** `GET /api/campaigns/{campaign_id}/smart-retry-status`

**Purpose:** Provides real-time information about smart retry status for a campaign

**Returns:**

- When the last auto-retry happened
- When the next auto-retry will occur
- Why a campaign is not eligible for retry (if applicable)
- Complete retry chain (all child campaigns)
- Time until deadline
- Poller frequency and retry interval

**Use Case:** Call this endpoint to monitor if your campaign is being auto-retried every 2 hours

---

### 2. **Python Monitoring Script**

**File:** `/apps/backend/check_smart_retries.py`

**Usage:**

```bash
# List all smart retry campaigns
python check_smart_retries.py

# Check specific campaign
python check_smart_retries.py 507f1f77bcf86cd799439011
```

**Purpose:** Quick command-line tool to check retry status without using API

---

### 3. **Comprehensive Documentation**

**File:** `/docs/SMART_RETRIES_MONITORING.md`

**Contains:**

- How smart retries work (technical details)
- 4 different monitoring methods
- Database field explanations
- Troubleshooting guide
- Testing procedures
- Frontend integration examples

---

## How Smart Retries Work (Quick Summary)

1. **Celery Beat task runs every 15 minutes** (`poll-smart-retries-every-15m`)
2. **Finds campaigns eligible for retry:**
   - `smart_retries: true`
   - Status `completed` or `failed`
   - Has failed messages
   - Deadline (`retry_until`) not reached
   - Last retry was 2+ hours ago OR never retried
3. **Creates child campaign** with only failed messages
4. **Updates `last_auto_retry_at`** to current time
5. **Repeats every 2 hours** until deadline or no failures remain

---

## How to Know It's Working

### Method 1: API Call (Easiest)

```bash
curl https://buzz-api.eigensu.in/api/campaigns/{your_campaign_id}/smart-retry-status
```

**Look for:**

- `"is_eligible_for_retry": true` → Campaign will retry again
- `"next_retry_in_seconds": 0` → Will retry on next poll (within 15 min)
- `"next_retry_in_seconds": 3600` → Will retry in 1 hour
- `"total_retries": 2` → Has auto-retried 2 times already

### Method 2: Check Child Campaigns

```bash
# In MongoDB or via API
GET /api/campaigns/{campaign_id}/group
```

Look at the `retry_count` field - it shows how many child campaigns were created.

### Method 3: Frontend Display

Add a badge to the campaign detail page showing:

```text
🔄 Smart Retries Active
Next retry in: 45 minutes
Auto-retries done: 2
Deadline: 3 days 14 hours
```

---

## Deployment Checklist

- [x] Fixed `smart_retries_poller.py` to use `last_auto_retry_at` instead of `has_been_retried`
- [x] Added `/campaigns/{id}/smart-retry-status` endpoint
- [x] Created monitoring script `check_smart_retries.py`
- [x] Created comprehensive documentation
- [ ] **TODO: Deploy to Railway** (API and celery-worker services)
- [ ] **TODO: Test with real campaign**
- [x] Added frontend UI component (`SmartRetryStatus` on the campaign detail page)

---

## Railway Deployment

The smart retry fix is already in the codebase (`smart_retries_poller.py`) but needs deployment:

```bash
# Option 1: Git push triggers auto-deploy
git add .
git commit -m "Add smart retry monitoring and fix multiple retry cycles"
git push origin main

# Option 2: Railway CLI
railway up --service api
railway up --service celery-worker
```

**Important:** Deploy BOTH services:

- `api` - for the new endpoint
- `celery-worker` - for the fixed poller logic

---

## Testing

1. Create a campaign with smart retries enabled
2. Set `retry_until` to 24 hours from now
3. Ensure some messages fail
4. Call the monitoring endpoint every 30 minutes
5. Verify `total_retries` increases every 2 hours
6. Verify `last_auto_retry_at` updates every 2 hours

---

## Quick Answer to "How do I know it's been retried every 2 hours?"

**Use the new API endpoint:**

```bash
curl https://buzz-api.eigensu.in/api/campaigns/YOUR_CAMPAIGN_ID/smart-retry-status
```

**Check these fields:**

- `last_auto_retry_at` - timestamp of last retry
- `last_retry_seconds_ago` - should be ~7200 (2 hours) when next retry happens
- `total_retries` - increases by 1 every 2 hours
- `retry_chain` - array grows with each retry

**Example:**

- First check: `total_retries: 0`, `last_auto_retry_at: null`
- After 2 hours: `total_retries: 1`, `last_retry_seconds_ago: 7200`
- After 4 hours: `total_retries: 2`, `last_retry_seconds_ago: 7200`
- After 6 hours: `total_retries: 3`, `last_retry_seconds_ago: 7200`

The `retry_chain` array will show all campaigns:

```json
{
  "retry_chain": [
    { "name": "Original", "created_at": "10:00", "is_root": true },
    { "name": "Original (retry)", "created_at": "12:00", "is_root": false },
    { "name": "Original (retry)", "created_at": "14:00", "is_root": false },
    { "name": "Original (retry)", "created_at": "16:00", "is_root": false }
  ],
  "total_retries": 3
}
```
