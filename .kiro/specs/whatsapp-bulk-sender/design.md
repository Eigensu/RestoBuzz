# WhatsApp Bulk Sender — Design

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Next.js 15 Frontend                       │
│  Campaign Wizard │ Live Dashboard │ Inbox │ Settings │ Auth UI   │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS / SSE
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                             │
│  /api/auth  /api/campaigns  /api/contacts  /api/templates        │
│  /api/inbox  /api/webhooks  /api/settings  /api/health           │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
  ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐  ┌─────▼──────┐
  │ MongoDB │   │   Redis    │  │ Celery  │  │ Cloudinary │
  │ (Motor) │   │ (Cache +   │  │ Workers │  │  (Media)   │
  │         │   │  Queues +  │  │         │  └────────────┘
  │         │   │  Locks +   │  │         │
  │         │   │  Rate Lim) │  │         │
  └─────────┘   └───────────┘  └────┬────┘
                                     │
                              ┌──────▼──────┐
                              │  Meta Cloud │
                              │     API     │
                              └─────────────┘
```

## Directory Structure

```
whatsapp-bulk-sender/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/                    # Not used (MongoDB), kept for reference
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory
│   │   ├── config.py               # Pydantic Settings
│   │   ├── database.py             # Motor client + indexes
│   │   ├── dependencies.py         # Auth + DB injection
│   │   │
│   │   ├── models/                 # Pydantic v2 schemas
│   │   │   ├── user.py
│   │   │   ├── campaign.py
│   │   │   ├── contact.py
│   │   │   ├── message.py
│   │   │   ├── inbox.py
│   │   │   └── suppression.py
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── campaigns.py
│   │   │   ├── contacts.py
│   │   │   ├── templates.py
│   │   │   ├── webhooks.py
│   │   │   ├── inbox.py
│   │   │   ├── settings.py
│   │   │   └── health.py
│   │   │
│   │   ├── services/
│   │   │   ├── meta_api.py         # Meta Cloud API client
│   │   │   ├── cloudinary.py       # Media upload
│   │   │   ├── contact_parser.py   # xlsx/csv parsing + E.164
│   │   │   ├── rate_limiter.py     # Token bucket (Redis)
│   │   │   ├── deduplication.py    # Redis wa_message_id cache
│   │   │   └── suppression.py      # Opt-out checks
│   │   │
│   │   ├── workers/
│   │   │   ├── celery_app.py       # Celery + Redis broker config
│   │   │   ├── send_task.py        # Core send + retry logic
│   │   │   ├── webhook_task.py     # Async webhook processing
│   │   │   └── template_sync.py    # Periodic template fetch
│   │   │
│   │   ├── core/
│   │   │   ├── security.py         # JWT + password hashing
│   │   │   ├── rbac.py             # Role decorators
│   │   │   ├── redlock.py          # Distributed lock wrapper
│   │   │   └── logging.py          # Structured JSON logger
│   │   │
│   │   └── sse/
│   │       └── campaign_stream.py  # SSE event generator
│   │
│   └── tests/
│       ├── unit/
│       │   ├── test_e164.py
│       │   ├── test_rate_limiter.py
│       │   └── test_deduplication.py
│       └── integration/
│           ├── test_idempotency.py
│           └── test_webhook.py
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.ts
    ├── tailwind.config.ts
    ├── components.json             # shadcn/ui config
    │
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                # Redirect to /dashboard
    │   ├── (auth)/
    │   │   └── login/page.tsx
    │   └── (dashboard)/
    │       ├── layout.tsx          # Sidebar + topbar shell
    │       ├── dashboard/page.tsx  # Campaign overview
    │       ├── campaigns/
    │       │   ├── page.tsx        # Campaign list
    │       │   ├── new/page.tsx    # Wizard
    │       │   └── [id]/page.tsx   # Detail + live progress
    │       ├── inbox/
    │       │   └── page.tsx        # Two-pane inbox
    │       ├── templates/page.tsx
    │       ├── contacts/page.tsx   # Suppression list
    │       └── settings/page.tsx
    │
    ├── components/
    │   ├── ui/                     # shadcn primitives
    │   ├── campaign/
    │   │   ├── Wizard.tsx
    │   │   ├── StepUpload.tsx
    │   │   ├── StepPreflight.tsx
    │   │   ├── StepTemplate.tsx
    │   │   ├── StepSchedule.tsx
    │   │   └── StepReview.tsx
    │   ├── inbox/
    │   │   ├── ConversationList.tsx
    │   │   ├── ChatThread.tsx
    │   │   ├── MessageBubble.tsx
    │   │   └── MediaChip.tsx
    │   ├── dashboard/
    │   │   ├── CampaignCard.tsx
    │   │   └── LiveProgressBar.tsx
    │   └── shared/
    │       ├── DataTable.tsx
    │       └── StatusBadge.tsx
    │
    ├── lib/
    │   ├── api.ts                  # Axios/fetch client
    │   ├── auth.ts                 # JWT helpers
    │   ├── sse.ts                  # SSE hook
    │   └── utils.ts
    │
    └── types/
        └── index.ts                # Shared TS types
```

## Data Models (MongoDB)

### users
```json
{
  "_id": "ObjectId",
  "email": "string (unique)",
  "hashed_password": "string",
  "role": "super_admin | admin | viewer",
  "is_active": "bool",
  "created_at": "datetime",
  "last_login": "datetime"
}
```

### campaign_jobs
```json
{
  "_id": "ObjectId",
  "name": "string",
  "template_id": "string",
  "template_name": "string",
  "template_variables": "object",
  "media_url": "string | null",
  "priority": "MARKETING | UTILITY",
  "status": "draft | queued | running | paused | completed | failed",
  "total_count": "int",
  "sent_count": "int",
  "delivered_count": "int",
  "read_count": "int",
  "failed_count": "int",
  "scheduled_at": "datetime | null",
  "started_at": "datetime | null",
  "completed_at": "datetime | null",
  "created_by": "ObjectId (ref: users)",
  "include_unsubscribe": "bool",
  "created_at": "datetime"
}
```
Indexes: `status`, `created_by`, `scheduled_at`

### message_logs
```json
{
  "_id": "ObjectId",
  "job_id": "ObjectId (ref: campaign_jobs)",
  "recipient_phone": "string (E.164)",
  "recipient_name": "string",
  "template_variables": "object",
  "wa_message_id": "string | null",
  "status": "queued | sending | sent | delivered | read | failed",
  "status_history": [
    { "status": "string", "timestamp": "datetime", "meta": "object" }
  ],
  "retry_count": "int (default 0)",
  "locked_until": "datetime | null",
  "endpoint_used": "primary | fallback",
  "fallback_used": "bool",
  "error_code": "string | null",
  "error_message": "string | null",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```
Indexes: `(job_id, status)`, `wa_message_id (unique sparse)`, `locked_until`

### inbound_messages
```json
{
  "_id": "ObjectId",
  "wa_message_id": "string (unique)",
  "from_phone": "string (E.164)",
  "sender_name": "string | null",
  "message_type": "text | image | document | location | sticker | unknown",
  "body": "string | null",
  "media_url": "string | null",
  "media_mime_type": "string | null",
  "location": { "lat": "float", "lng": "float", "name": "string" } ,
  "is_read": "bool (default false)",
  "received_at": "datetime",
  "raw_payload": "object"
}
```
Indexes: `(from_phone, received_at)`, `is_read`, `wa_message_id (unique)`

### suppression_list
```json
{
  "_id": "ObjectId",
  "phone": "string (E.164, unique)",
  "reason": "opt_out | blocked | bounce",
  "added_by": "ObjectId | null",
  "added_at": "datetime"
}
```
Index: `phone (unique)`

### audit_logs
```json
{
  "_id": "ObjectId",
  "user_id": "ObjectId",
  "action": "string",
  "resource_type": "campaign | user | settings | suppression",
  "resource_id": "string | null",
  "metadata": "object",
  "ip_address": "string",
  "timestamp": "datetime"
}
```
Index: `(user_id, timestamp)`, `resource_type`

### webhook_errors
```json
{
  "_id": "ObjectId",
  "raw_body": "string",
  "headers": "object",
  "error": "string",
  "received_at": "datetime"
}
```

## API Endpoints

### Auth — `/api/auth`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| POST | `/login` | Email + password → JWT pair | Public |
| POST | `/refresh` | Refresh access token | Authenticated |
| POST | `/logout` | Invalidate refresh token | Authenticated |
| GET | `/me` | Current user profile | Authenticated |

### Campaigns — `/api/campaigns`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET | `/` | List campaigns (paginated) | viewer+ |
| POST | `/` | Create campaign job | admin+ |
| GET | `/{id}` | Campaign detail | viewer+ |
| POST | `/{id}/start` | Enqueue campaign | admin+ |
| POST | `/{id}/pause` | Pause running campaign | admin+ |
| POST | `/{id}/cancel` | Cancel campaign | admin+ |
| GET | `/{id}/messages` | Message logs (paginated, filterable) | viewer+ |
| GET | `/{id}/export-failed` | Download failed CSV | admin+ |
| GET | `/{id}/stream` | SSE live progress | viewer+ |

### Contacts — `/api/contacts`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| POST | `/upload` | Upload + parse file → preflight result | admin+ |
| POST | `/validate` | Validate column mapping | admin+ |

### Templates — `/api/templates`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET | `/` | List synced templates | viewer+ |
| POST | `/sync` | Trigger Meta API sync | admin+ |

### Webhooks — `/api/webhooks`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET | `/meta` | Hub verification challenge | Public |
| POST | `/meta` | Inbound events (status + messages) | Public (sig-verified) |

### Inbox — `/api/inbox`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET | `/conversations` | List conversations (paginated) | viewer+ |
| GET | `/conversations/{phone}` | Messages for a contact | viewer+ |
| POST | `/conversations/{phone}/read` | Mark all as read | viewer+ |
| POST | `/conversations/{phone}/reply` | Send reply message | admin+ |
| GET | `/stream` | SSE new message events | viewer+ |

### Settings — `/api/settings`
| Method | Path | Description | Role |
|--------|------|-------------|------|
| GET | `/waba` | WABA config (masked) | admin+ |
| PUT | `/waba` | Update WABA credentials | super_admin |
| GET | `/suppression` | List suppression entries | admin+ |
| POST | `/suppression` | Add number | admin+ |
| DELETE | `/suppression/{phone}` | Remove number | admin+ |

### Health — `/api/health`
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | MongoDB + Redis + Celery status |

## Messaging Engine — Detailed Flow

```
Campaign Start
     │
     ▼
[Celery: dispatch_campaign_task]
     │  Reads campaign_jobs, streams message_logs in batches of 100
     │
     ▼
[Redis Priority Queue]
  UTILITY queue (higher priority)
  MARKETING queue
     │
     ▼
[Celery: send_message_task]  ← pulled by N workers
     │
     ├─ 1. Acquire Redlock(message_id, ttl=60s)
     │       └─ If lock fails → skip (another worker has it)
     │
     ├─ 2. find_one_and_update: status=queued → sending, locked_until=now+60s
     │       └─ If doc not found → already claimed, exit
     │
     ├─ 3. Check suppression list
     │       └─ If suppressed → mark failed(suppressed), release lock
     │
     ├─ 4. Token Bucket check (Redis)
     │       └─ If throttled → requeue with 1s delay
     │
     ├─ 5. POST to Meta Cloud API (primary WABA)
     │       └─ On 4xx/5xx → try fallback WABA
     │           └─ On fallback success → fallback_used=true
     │           └─ On fallback fail → schedule retry (exp backoff)
     │
     ├─ 6. On success → status=sent, store wa_message_id in Redis (24h TTL)
     │
     └─ 7. Release Redlock
```

## Rate Limiter — Token Bucket (Redis)

```python
# Lua script executed atomically in Redis
# Key: rate_limit:{waba_id}
# Capacity: 80 tokens, refill rate: 80/sec

SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])   -- 80
local refill_rate = tonumber(ARGV[2]) -- 80 per second
local now = tonumber(ARGV[3])         -- unix ms

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = (now - last_refill) / 1000
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 10)
    return 1  -- allowed
else
    return 0  -- throttled
end
"""
```

## Webhook Processing Flow

```
POST /api/webhooks/meta
     │
     ├─ 1. Verify X-Hub-Signature-256 (HMAC-SHA256)
     │       └─ Mismatch → 403 (log attempt)
     │
     ├─ 2. Return 200 OK immediately
     │
     └─ 3. Enqueue [Celery: process_webhook_task]
               │
               ├─ Status update event:
               │   ├─ Check Redis dedup (wa_message_id)
               │   ├─ Update message_logs.status_history
               │   └─ Increment campaign_jobs counters (atomic $inc)
               │
               └─ Inbound message event:
                   ├─ Check Redis dedup
                   ├─ Upsert inbound_messages
                   ├─ Check body for "STOP" → add to suppression_list
                   └─ Emit SSE event to inbox stream
```

## Frontend State Management

- Server state: TanStack Query (React Query) for all API calls.
- SSE: Custom `useSSE(url)` hook wrapping `EventSource`.
- Forms: React Hook Form + Zod validation.
- Global UI state: Zustand (auth user, sidebar open state).
- No Redux — keep it simple.

## Docker Compose Services

| Service | Image | Port |
|---------|-------|------|
| `mongo` | mongo:7 | 27017 |
| `redis` | redis:7-alpine | 6379 |
| `backend` | ./backend | 8000 |
| `worker` | ./backend (celery) | — |
| `flower` | ./backend (flower) | 5555 |
| `frontend` | ./frontend | 3000 |

All services share a `app_network` bridge network. Mongo and Redis data persisted via named volumes.

## Environment Variables

### Backend (.env)
```
MONGODB_URL=mongodb://mongo:27017/whatsapp_bulk
REDIS_URL=redis://redis:6379/0
JWT_SECRET=<random 64 char hex>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

META_API_VERSION=v19.0
META_PRIMARY_PHONE_ID=<phone_number_id>
META_PRIMARY_ACCESS_TOKEN=<token>
META_FALLBACK_PHONE_ID=<phone_number_id>
META_FALLBACK_ACCESS_TOKEN=<token>
META_WEBHOOK_VERIFY_TOKEN=<random string>
META_WEBHOOK_SECRET=<app secret for HMAC>

CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=

CELERY_CONCURRENCY=4
RATE_LIMIT_MPS=80
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=WA Bulk Sender
```
