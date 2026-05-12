# Tech Spec: Meta Webhook Processing Refactor

**Status:** Implemented  
**Author:** Engineering  
**Date:** May 2026

---

## 1. Background & Problem Statement

### What exists today

The Meta webhook handler at `POST /api/webhooks/meta` currently does all processing
**synchronously inside the FastAPI request/response cycle**:

```
Meta → POST /api/webhooks/meta
         │
         ├── verify HMAC signature
         ├── parse JSON
         ├── resolve restaurant_id (DB query)
         ├── save inbound_messages (DB write)
         ├── update message_logs + status_history (DB write)
         ├── increment campaign_jobs counters (DB write)
         ├── update outbound_messages (DB write)
         ├── handle auto-replies (Meta API call)
         ├── handle suppression (DB write)
         └── return 200
```

There is also a `webhook_task.py` Celery task (`process_webhook_task`) that was
originally designed to handle this processing asynchronously, but it is **never
called** — it is registered in Celery but the router does not enqueue it.

### Why this is a problem

**Meta's retry policy:** If Meta does not receive a `200 OK` within **5 seconds**,
it retries the webhook up to 20 times over 3 days. During a large campaign delivery
(e.g. 1,000 messages all delivering within seconds), the handler is hit with a burst
of concurrent status webhooks. Each one does 3–5 sequential DB operations. Under
load this can breach the 5-second window, causing:

- Meta retries → duplicate processing
- Cascading DB load
- Incorrect counter increments (double-counting)
- Missed status updates if the handler errors mid-way

**Secondary issues with the current implementation:**

1. **No deduplication.** The current handler has no Redis-based dedup. If Meta
   retries a webhook (which it does legitimately), the same status update is
   processed twice, incrementing `delivered_count` twice.

2. **Missing billing event recording.** `webhook_task.py` records
   `meta_billing_events` (WhatsApp conversation pricing). The current inline handler
   does not — this data is silently lost.

3. **Missing reply tracking.** `webhook_task.py` tracks `replies_count` on
   `campaign_jobs` and marks `replied: true` on `message_logs`. The current inline
   handler does not.

4. **Diverged logic.** Two parallel implementations exist (`webhooks.py` and
   `webhook_task.py`) that have drifted apart. `webhook_task.py` has richer logic
   (dedup, billing, reply tracking) but is dead code. `webhooks.py` is live but
   incomplete.

5. **Auto-replies block the response.** `_send_benefits_reply` makes a live Meta
   API call synchronously inside the webhook handler. If Meta's API is slow, this
   delays the 200 response.

---

## 2. Goals

- Return `200 OK` to Meta in **< 100ms** on every webhook, regardless of load.
- **Eliminate duplicate processing** via Redis deduplication.
- **Consolidate** all webhook processing logic into a single authoritative path.
- **Restore missing features**: billing events, reply tracking.
- Keep the Resend webhook handler (`POST /api/webhooks/resend`) as-is — it is
  already well-structured and low-volume.

---

## 3. Proposed Architecture

```
Meta → POST /api/webhooks/meta
         │
         ├── verify HMAC signature          (in-memory, ~0ms)
         ├── parse JSON                     (in-memory, ~0ms)
         ├── enqueue process_webhook_task   (single Redis write, ~1ms)
         └── return 200                     (total: ~5ms)

                    │
                    ▼ (async, Celery worker)
         process_webhook_task(payload)
              │
              ├── for each status update:
              │     ├── Redis dedup check
              │     ├── update message_logs + status_history
              │     ├── increment campaign_jobs counters
              │     ├── update outbound_messages
              │     ├── store error details (if failed)
              │     └── record meta_billing_events (if billable)
              │
              └── for each inbound message:
                    ├── Redis dedup check
                    ├── save inbound_messages (upsert)
                    ├── mark replied on message_logs
                    ├── increment replies_count on campaign_jobs
                    ├── handle STOP keyword → suppression_list
                    ├── handle benefits auto-reply (async Meta API call)
                    └── trigger unread threshold alert check
```

Template status updates (`message_template_status_update`) are low-volume and
fire email alerts — these can remain as FastAPI `BackgroundTasks` since they don't
need dedup and are not on the hot path.

---

## 4. Detailed Changes

### 4.1 `routers/webhooks.py` — Thin receiver

The handler becomes a pure receiver: verify, parse, enqueue, return.

```python
from app.workers.webhook_task import process_webhook_task

@router.post("/meta", status_code=200)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if not _verify_signature(body, sig):
        logger.warning("webhook_invalid_signature")
        raise WebhookSignatureError("Invalid webhook signature")

    try:
        payload = json.loads(body)
    except Exception as e:
        logger.error("webhook_json_parse_error", error=str(e))
        # Still store parse errors for debugging
        background_tasks.add_task(_store_parse_error, db, body, request.headers, str(e))
        return {"status": "ok"}

    logger.info("webhook_received", entry_count=len(payload.get("entry", [])))

    # Handle template status updates inline (low-volume, no dedup needed)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if value.get("event") == "message_template_status_update":
                background_tasks.add_task(
                    _handle_template_status, db, value, background_tasks
                )

    # Enqueue everything else to Celery.
    # If Redis is unavailable, apply_async will raise. Fall back to
    # BackgroundTasks so the webhook data is never lost and Meta still
    # receives a 200 — processing will be slower but correct.
    try:
        process_webhook_task.apply_async(args=[payload], queue="webhooks")
    except Exception as e:
        logger.error(
            "webhook_enqueue_failed_falling_back_to_background",
            error=str(e),
        )
        background_tasks.add_task(_process_webhook_sync, db, payload)

    return {"status": "ok"}
```

All the `_handle_incoming_messages`, `_handle_message_status_update`,
`_handle_webhook_change`, `_process_payload`, `_resolve_restaurant_id`,
`_parse_message_content`, `_handle_auto_replies`, `_send_benefits_reply` functions
are **removed** from `webhooks.py` and consolidated into `webhook_task.py`.

`_handle_template_status`, `_verify_signature`, and the new
`_process_webhook_sync` fallback stay in `webhooks.py`.

> **Emergency fallback — `_process_webhook_sync`:** This function mirrors the
> Celery task logic but runs inside a FastAPI `BackgroundTask`. It is only invoked
> when `apply_async` raises (i.e. Redis is unreachable). It prevents data loss at
> the cost of slower processing and no deduplication guarantee. Log the
> `webhook_enqueue_failed_falling_back_to_background` event and page on-call if
> it fires in production.

---

### 4.2 `workers/webhook_task.py` — Authoritative processor

The existing task is extended to cover everything the inline handler was doing.
Key additions vs. the current `webhook_task.py`:

#### a) Restaurant ID resolution

The current task does not resolve `restaurant_id` — it's missing from
`inbound_messages` docs. Add resolution from `metadata.phone_number_id`:

```python
async def _resolve_restaurant(db, value: dict) -> tuple[str | None, str | None]:
    """Returns (restaurant_id, phone_number_id)."""
    metadata = value.get("metadata", {})
    phone_number_id = str(metadata.get("phone_number_id", "")) or None
    if not phone_number_id:
        return None, None
    rest = await db.restaurants.find_one({"wa_phone_ids": phone_number_id})
    if not rest:
        return None, phone_number_id
    return rest.get("id") or str(rest["_id"]), phone_number_id
```

#### b) `outbound_messages` status update

Add alongside the existing `message_logs` update in `_handle_statuses`:

```python
# Update outbound_messages (system/auto-reply messages)
await db.outbound_messages.update_one(
    {"wa_message_id": wa_id},
    {"$set": {"status": status, "updated_at": now}},
)
```

#### c) Benefits auto-reply

Move `_send_benefits_reply` from `webhooks.py` into `webhook_task.py`. Since
this is now inside a Celery task, the Meta API call no longer blocks the HTTP
response.

#### d) Unread threshold alert

After saving inbound messages, enqueue the alert check. Since we're already in
a Celery task, use a Celery chain or call the alert service directly:

```python
from app.services.alert_service import alert_service

if restaurant_id and messages_saved:
    # Run in a separate async call — doesn't block message processing
    await alert_service.check_unread_threshold_alert(db, restaurant_id)
```

#### e) Full `_handle_messages` additions

The current `webhook_task._handle_messages` is missing:

- `restaurant_id` and `wa_phone_id` fields on `inbound_messages` docs
- `button` and `interactive` message type parsing
- `audio` and `video` media type handling

Merge the richer type handling from `webhooks.py` into `webhook_task.py`.

---

### 4.3 `workers/celery_app.py` — Queue routing

Add a dedicated `webhooks` queue for webhook processing to isolate it from
campaign send traffic:

```python
task_queues={
    "utility": {"exchange": "utility", "routing_key": "utility"},
    "marketing": {"exchange": "marketing", "routing_key": "marketing"},
    "email": {"exchange": "email", "routing_key": "email"},
    "webhooks": {"exchange": "webhooks", "routing_key": "webhooks"},  # NEW
},
task_routes={
    ...
    "app.workers.webhook_task.process_webhook_task": {
        "queue": "webhooks",
    },
},
```

This prevents a burst of webhook tasks from starving campaign send tasks on the
`marketing` queue.

> **Note:** The Railway `celery-worker` service will need its start command updated
> to consume the `webhooks` queue, or a dedicated webhook worker can be added.
> Simplest option: add `--queues marketing,utility,webhooks` to the existing worker.

---

### 4.4 Deduplication

`webhook_task.py` already has Redis dedup via `is_duplicate` / `mark_seen` for
both statuses and inbound messages. This is preserved with the following
refinements.

#### Key format

Use a composite key that includes the **status** field:

```
wa_dedup:{restaurant_id}:{wa_id}:{status}
```

Example: `wa_dedup:rest_abc:wamid.XYZ:delivered`

**Why include `status`?** A single `wa_id` progresses through multiple statuses
(`sent` → `delivered` → `read`). If the key were keyed only on `wa_id`, the
`delivered` event would mark the key seen and the subsequent `read` event would
be silently dropped — losing the read receipt and the associated billing event.
Including `status` lets each transition pass through exactly once.

#### TTL

Set to **24 hours**. Meta's full retry window is 72 hours, but empirically >99%
of retries arrive within the first 24 hours. A 24h TTL keeps Redis memory
bounded while covering the realistic retry surface.

```python
DEDUP_TTL_SECONDS = 86_400  # 24 hours
```

---

## 5. RestoBuzz Domain-Specific Logic Checks

These are required correctness checks specific to the RestoBuzz deployment
(brands: Scarlett House, Soraia, etc.).

### 5.1 Atomic counter increments

All counter fields on `campaign_jobs` **must** use MongoDB's `$inc` operator.
Never read-modify-write a counter in application code — under concurrent Celery
workers this will produce race conditions and under-counts.

```python
# CORRECT — atomic
await db.campaign_jobs.update_one(
    {"_id": job_id},
    {"$inc": {"delivered_count": 1}},
)

# WRONG — race condition under concurrency
job = await db.campaign_jobs.find_one({"_id": job_id})
await db.campaign_jobs.update_one(
    {"_id": job_id},
    {"$set": {"delivered_count": job["delivered_count"] + 1}},
)
```

Affected counters: `delivered_count`, `read_count`, `failed_count`,
`replies_count`, `sent_count`.

### 5.2 Suppression handling

When an inbound message body matches `STOP` or `UNSUBSCRIBE` (case-insensitive),
update `suppression_list` **globally** (not scoped to a single restaurant).
A contact who opts out of one brand's messages should not receive messages from
any other brand on the same platform account.

```python
STOP_KEYWORDS = {"stop", "unsubscribe", "opt out", "optout"}

if message_body.strip().lower() in STOP_KEYWORDS:
    await db.suppression_list.update_one(
        {"wa_number": sender_wa_number},
        {"$set": {"suppressed": True, "suppressed_at": now, "reason": "STOP"}},
        upsert=True,
    )
```

### 5.3 Billing event category capture

WhatsApp charges different rates for **Marketing** vs. **Utility** vs.
**Authentication** conversations. The `pricing` object in the webhook payload
carries this. `record_meta_billing_events` must capture it:

```python
pricing = status_obj.get("pricing", {})
await db.meta_billing_events.insert_one({
    "restaurant_id": restaurant_id,
    "wa_message_id": wa_id,
    "billable": pricing.get("billable", False),
    "pricing_model": pricing.get("pricing_model"),          # "CBP"
    "category": pricing.get("category"),                    # "marketing" | "utility" | "authentication"
    "recorded_at": now,
})
```

Silently dropping the `category` field means billing reconciliation against
Meta's invoices becomes impossible.

### 5.4 Media ID capture for inbound messages

Restaurant customers frequently send photos (receipts, reservation screenshots,
food photos). `_handle_messages` must store the `media_id` so the image URL can
be fetched later via the Media API:

```python
# Inside message type parsing
if msg_type in ("image", "video", "audio", "document", "sticker"):
    media_obj = message.get(msg_type, {})
    content = {
        "media_id": media_obj.get("id"),        # required for later fetch
        "mime_type": media_obj.get("mime_type"),
        "sha256": media_obj.get("sha256"),
        "caption": media_obj.get("caption"),    # images/videos may have captions
    }
```

Without `media_id`, the raw media is permanently inaccessible after the webhook
is processed.

---

## 6. Dead Letter Strategy

If `webhook_task` crashes on a specific payload (e.g. malformed structure,
unexpected field type), Celery will retry up to `max_retries` times and then
either silently discard the task or raise `MaxRetriesExceededError` depending on
configuration. Either outcome loses the raw webhook data.

### Required: `on_failure` handler

Add an `on_failure` callback to `process_webhook_task` that persists the raw
payload to a `failed_webhooks` collection before the task is abandoned:

```python
@celery_app.task(
    bind=True,
    name="app.workers.webhook_task.process_webhook_task",
    max_retries=3,
    default_retry_delay=30,
)
def process_webhook_task(self, payload: dict):
    ...

def on_failure(self, exc, task_id, args, kwargs, einfo):
    """Persist the raw payload so it can be replayed after a bug fix."""
    import asyncio
    from app.db import get_sync_db  # or use a sync motor client

    raw_payload = args[0] if args else {}
    db = get_sync_db()
    db.failed_webhooks.insert_one({
        "task_id": task_id,
        "payload": raw_payload,
        "error": str(exc),
        "traceback": str(einfo),
        "failed_at": datetime.utcnow(),
    })
```

This gives you a replay queue: once the bug is fixed, iterate over
`failed_webhooks` and re-enqueue each document.

---

## 7. What Is NOT Changing

| Component                                 | Change                              |
| ----------------------------------------- | ----------------------------------- |
| `POST /api/webhooks/resend`               | No change — already well-structured |
| `GET /api/webhooks/meta` (verification)   | No change                           |
| `webhook_task.py` billing event recording | Preserved as-is                     |
| `webhook_task.py` reply tracking          | Preserved as-is                     |
| Alert service                             | No change                           |
| All other routers                         | No change                           |

---

## 8. Migration & Rollout

Since this is a pure internal refactor with no API contract changes, no migration
is needed. The rollout is:

1. Implement changes in a feature branch
2. Deploy `celery-worker` first (so the task is registered before the router
   starts enqueuing)
3. Deploy `RestoBuzz` (API) — the router now enqueues instead of processing inline
4. Monitor logs for `process_webhook_task` execution and verify
   `delivered_count`/`read_count` increments on a test campaign

**Rollback:** Revert the `webhooks.py` change to restore inline processing. The
Celery task change is additive and safe to leave deployed.

---

## 9. Risk & Mitigations

| Risk                                                          | Likelihood | Mitigation                                                                                                   |
| ------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ |
| Celery worker down → webhooks silently dropped                | Low        | Redis queue persists tasks; worker restart drains queue. Add worker health alert.                            |
| Redis down → `apply_async` fails                              | Very low   | Wrapped in try/except; falls back to `_process_webhook_sync` via BackgroundTasks. Alert on-call if it fires. |
| Dedup TTL too short → duplicate processing on Meta retry      | Low        | Key format `wa_dedup:{restaurant_id}:{wa_id}:{status}` + 24h TTL covers realistic retry window per status.   |
| Same `wa_id` dedup blocks `read` after `delivered`            | Medium     | Resolved by including `status` in the dedup key — each status transition is independently deduplicated.      |
| Task queue backlog during burst                               | Medium     | Dedicated `webhooks` queue + auto-scaling worker on Railway.                                                 |
| Malformed payload crashes task → data lost after max retries  | Low        | `on_failure` handler persists raw payload to `failed_webhooks` for manual replay after bug fix.              |
| Race condition on counter increments under concurrent workers | Medium     | All counters use MongoDB `$inc` — atomic at the DB level, no read-modify-write in application code.          |
| Template status alerts delayed                                | None       | These remain as inline `BackgroundTasks`.                                                                    |

---

## 10. Files Changed

| File                                  | Change type                                                                                                                                                              |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/routers/webhooks.py`             | Major simplification — remove inline processing; add `_process_webhook_sync` fallback; fix queue name to `webhooks`                                                      |
| `app/workers/webhook_task.py`         | Extend with restaurant resolution, outbound_messages update, auto-replies, alert trigger, richer message type parsing, `on_failure` dead letter handler, `$inc` counters |
| `app/workers/celery_app.py`           | Add `webhooks` queue + task route                                                                                                                                        |
| `app/utils/deduplication.py`          | Update key format to `wa_dedup:{restaurant_id}:{wa_id}:{status}`; set TTL to 86400s                                                                                      |
| Railway `celery-worker` start command | Add `--queues webhooks` (or update existing queues list)                                                                                                                 |

---

## 11. Infrastructure & Environment Changes

### 11.1 Railway Redis — `maxmemory-policy`

**Required.** Railway's managed Redis defaults to `allkeys-lru`. Under memory
pressure this policy silently evicts keys — including Celery task messages sitting
in the broker queue. A webhook payload gets enqueued, Redis evicts it before the
worker picks it up, and it disappears with no error or log entry.

Set the policy to `noeviction` in the Railway Redis service settings:

```
maxmemory-policy noeviction
```

With `noeviction`, Redis returns an error when memory is full instead of evicting
data. This triggers the `apply_async` exception handler in `webhooks.py`, which
falls back to `_process_webhook_sync` via `BackgroundTasks` — slower, but no
silent data loss.

> **How to set it:** Railway Redis → Settings → Configuration → `maxmemory-policy`
> → set to `noeviction`. Or via `redis-cli CONFIG SET maxmemory-policy noeviction`
> on the Railway Redis shell.

The local `docker-compose.yml` Redis service has been updated to match:
`redis-server --maxmemory-policy noeviction`.

### 11.2 Celery worker start command — add `webhooks` queue

**Required.** The Railway `celery-worker` service start command must include the
new `webhooks` queue or tasks will sit in the queue unprocessed.

Update from:

```
celery -A app.workers.celery_app worker --loglevel=info -Q utility,marketing,email
```

To:

```
celery -A app.workers.celery_app worker --loglevel=info -Q utility,marketing,email,webhooks
```

The local `docker-compose.yml` worker command has already been updated.

### 11.3 `visibility_timeout` — not applicable

The recommendation to set `visibility_timeout` in `CELERY_BROKER_URL` is not
relevant here. That is an SQS/Redis Streams transport option. This project uses
Celery with a standard Redis list broker, where the equivalent guarantees are
already provided by `task_acks_late=True` and `task_reject_on_worker_lost=True`
in `celery_app.py`. No change needed.

---

## 12. Success Metrics

- `POST /api/webhooks/meta` p99 response time < 100ms (down from potentially
  seconds under load)
- `delivered_count` and `read_count` on `campaign_jobs` increment correctly
  within ~2 seconds of Meta sending the status callback
- No duplicate counter increments (check Redis dedup is firing; key format
  includes status)
- `meta_billing_events` collection is being populated with `category` field
  (`marketing` / `utility` / `authentication`)
- `replies_count` increments when a recipient replies to a campaign message
- Inbound media messages have `media_id` populated in `inbound_messages`
- `failed_webhooks` collection remains empty under normal operation; any entries
  trigger an investigation
- `webhook_enqueue_failed_falling_back_to_background` log event never fires
  under normal Redis availability
