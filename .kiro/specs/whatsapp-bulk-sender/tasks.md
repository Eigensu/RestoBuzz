# WhatsApp Bulk Sender — Implementation Tasks

## Phase 1: Infrastructure & Backend Foundations

- [ ] 1.1 Docker Compose setup
  - `docker-compose.yml` with mongo, redis, backend, worker, flower, frontend services
  - Named volumes for mongo and redis persistence
  - Health checks on all services
  - `.env.example` with all required variables

- [ ] 1.2 FastAPI app factory (`app/main.py`)
  - CORS middleware (allow frontend origin)
  - Lifespan handler: connect Motor, ping Redis on startup
  - Mount all routers with `/api` prefix
  - Global exception handler returning structured JSON errors

- [ ] 1.3 Configuration (`app/config.py`)
  - Pydantic `BaseSettings` reading from `.env`
  - Typed fields for all env vars with validation

- [ ] 1.4 MongoDB setup (`app/database.py`)
  - Motor async client singleton
  - `init_indexes()` coroutine creating all required indexes on startup
  - Collection accessors as typed helpers

- [ ] 1.5 Pydantic v2 models (`app/models/`)
  - `user.py`: UserInDB, UserCreate, UserResponse, TokenPair
  - `campaign.py`: CampaignJob, CampaignCreate, CampaignStatus enum
  - `message.py`: MessageLog, StatusHistory, MessageStatus enum
  - `inbox.py`: InboundMessage, Conversation
  - `contact.py`: ContactRow, PreflightResult, ColumnMapping
  - `suppression.py`: SuppressionEntry

- [ ] 1.6 Auth system (`app/core/security.py`, `app/routers/auth.py`)
  - bcrypt password hashing
  - JWT access + refresh token generation/validation
  - `/login`, `/refresh`, `/logout`, `/me` endpoints
  - `get_current_user` dependency
  - `require_role(role)` RBAC decorator

- [ ] 1.7 Structured logging (`app/core/logging.py`)
  - JSON formatter with `correlation_id`, `timestamp`, `level`, `message`
  - Middleware to inject `correlation_id` per request

## Phase 2: Celery Workers, Rate Limiting & Meta API

- [ ] 2.1 Celery app (`app/workers/celery_app.py`)
  - Redis broker + result backend
  - Two queues: `utility` (priority 10) and `marketing` (priority 5)
  - Beat schedule: template sync every 6 hours

- [ ] 2.2 Meta API client (`app/services/meta_api.py`)
  - `send_template_message(phone, template_name, variables, media_url)` async method
  - Primary + fallback WABA support
  - Returns `(wa_message_id, endpoint_used)` or raises typed exception
  - Handles Meta error codes: 130429 (rate limit), 131026 (invalid number), etc.

- [ ] 2.3 Token Bucket rate limiter (`app/services/rate_limiter.py`)
  - Lua script loaded once, executed atomically via `redis.evalsha`
  - `async def acquire(waba_id) -> bool`
  - Configurable capacity and refill rate from settings

- [ ] 2.4 Distributed lock (`app/core/redlock.py`)
  - Thin wrapper around `redis-py` implementing single-instance Redlock
  - `async with RedLock(redis, key, ttl)` context manager

- [ ] 2.5 Deduplication service (`app/services/deduplication.py`)
  - `async def is_duplicate(wa_message_id) -> bool`
  - `async def mark_seen(wa_message_id, ttl=86400)`

- [ ] 2.6 Send message task (`app/workers/send_task.py`)
  - `dispatch_campaign_task(job_id)`: streams message_logs in batches, enqueues per-message tasks
  - `send_message_task(message_log_id)`: full send flow with lock, claim, rate limit, API call, retry
  - Exponential backoff: `countdown = 30 * (4 ** retry_count)` (30s, 120s, 480s)
  - Max retries: 3; on final failure set status=failed with error details

- [ ] 2.7 Webhook task (`app/workers/webhook_task.py`)
  - `process_webhook_task(payload)`: route to status update or inbound message handler
  - Status update: dedup check → update message_logs → atomic $inc on campaign_jobs counters
  - Inbound: dedup → upsert inbound_messages → STOP keyword check → SSE emit

- [ ] 2.8 Template sync task (`app/workers/template_sync.py`)
  - Fetch all approved templates from Meta API
  - Upsert into `templates` collection
  - Log sync result

- [ ] 2.9 Suppression service (`app/services/suppression.py`)
  - `async def is_suppressed(phone) -> bool` (checks MongoDB)
  - `async def add(phone, reason, added_by)`

## Phase 3: Contact Import, Campaign API & SSE

- [ ] 3.1 Contact parser (`app/services/contact_parser.py`)
  - Stream-parse `.xlsx`/`.xls` (openpyxl) and `.csv` (csv module) without loading full file
  - Normalize each phone with `phonenumbers` library to E.164
  - Return `PreflightResult`: valid rows, invalid rows (with reason), duplicate rows

- [ ] 3.2 Contacts router (`app/routers/contacts.py`)
  - `POST /upload`: accept multipart file, run parser, return preflight JSON
  - `POST /validate`: accept column mapping + file reference, return mapped rows

- [ ] 3.3 Campaigns router (`app/routers/campaigns.py`)
  - Full CRUD + start/pause/cancel actions
  - `GET /{id}/messages`: paginated message logs with status filter
  - `GET /{id}/export-failed`: StreamingResponse CSV

- [ ] 3.4 SSE stream (`app/sse/campaign_stream.py`)
  - `GET /api/campaigns/{id}/stream`: EventSource endpoint
  - Polls campaign_jobs counters every 1s, emits JSON event
  - Closes stream when campaign status is terminal

- [ ] 3.5 Templates router (`app/routers/templates.py`)
  - `GET /`: list from DB
  - `POST /sync`: trigger Celery task, return 202

- [ ] 3.6 Settings router (`app/routers/settings.py`)
  - WABA config CRUD (super_admin only for writes)
  - Suppression list CRUD

- [ ] 3.7 Audit log middleware
  - Decorator `@audit(action, resource_type)` for mutating endpoints
  - Writes to `audit_logs` collection async (fire-and-forget)

## Phase 4: Webhooks & Inbox

- [ ] 4.1 Webhook router (`app/routers/webhooks.py`)
  - `GET /meta`: return hub challenge
  - `POST /meta`: HMAC-SHA256 verification → 200 OK → enqueue task
  - Log malformed payloads to `webhook_errors` without raising

- [ ] 4.2 Inbox router (`app/routers/inbox.py`)
  - `GET /conversations`: group inbound_messages by from_phone, return last message + unread count
  - `GET /conversations/{phone}`: paginated message thread
  - `POST /conversations/{phone}/read`: set is_read=true for all
  - `POST /conversations/{phone}/reply`: call Meta API send text message
  - `GET /stream`: SSE for new inbound messages

## Phase 5: Frontend

- [ ] 5.1 Project setup
  - Next.js 15 with App Router, TypeScript strict mode
  - Tailwind CSS + shadcn/ui init
  - TanStack Query provider, Zustand store
  - Axios instance with JWT interceptor (auto-refresh on 401)

- [ ] 5.2 Auth pages
  - `/login`: email + password form, stores JWT in httpOnly cookie via API route
  - Auth middleware (`middleware.ts`): redirect unauthenticated to `/login`

- [ ] 5.3 Dashboard layout
  - Sidebar with nav links + unread inbox badge
  - Topbar with user menu + logout
  - Responsive: sidebar collapses to icon-only on mobile

- [ ] 5.4 Campaign list page (`/campaigns`)
  - Table with name, status badge, progress bar, sent/total, created date
  - "New Campaign" button → wizard

- [ ] 5.5 Campaign wizard (`/campaigns/new`)
  - Step 1 — Upload: drag-and-drop file input, sheet selector for Excel
  - Step 2 — Preflight: valid/invalid/duplicate counts, invalid rows table, export invalid CSV
  - Step 3 — Template: searchable template selector, variable inputs, media upload with size validation
  - Step 4 — Schedule: date-time picker, priority toggle, unsubscribe footer toggle
  - Step 5 — Review: summary card, "Launch Campaign" button

- [ ] 5.6 Campaign detail page (`/campaigns/[id]`)
  - Live progress bars (Sent / Delivered / Read / Failed) via SSE
  - Message logs table with status filter + pagination
  - "Export Failed" button

- [ ] 5.7 Inbox page (`/inbox`)
  - Two-pane layout using CSS Grid
  - Left: conversation list with search, unread badges, last message snippet
  - Right: chat thread with message bubbles (sent=right, received=left)
  - Render image thumbnails, PDF chips (name + download link), location map chip
  - Reply input at bottom (text only)
  - Mobile: list hidden when thread open, back button to return
  - SSE hook for real-time new messages

- [ ] 5.8 Templates page (`/templates`)
  - Grid of template cards: name, category badge, language, status
  - "Sync Templates" button with loading state

- [ ] 5.9 Settings page (`/settings`)
  - WABA config form (masked token display)
  - Suppression list table with add/remove

## Phase 6: Testing

- [ ] 6.1 Unit: E.164 normalization (`tests/unit/test_e164.py`)
  - Valid international numbers, local numbers with country hint, malformed inputs

- [ ] 6.2 Unit: Token bucket rate limiter (`tests/unit/test_rate_limiter.py`)
  - Burst allowance, throttle at capacity, refill over time (mock Redis)

- [ ] 6.3 Unit: Deduplication (`tests/unit/test_deduplication.py`)
  - First call returns False, second returns True, TTL expiry

- [ ] 6.4 Integration: Idempotency (`tests/integration/test_idempotency.py`)
  - Two concurrent workers claiming same message → only one proceeds
  - Worker crash + lock expiry → message re-claimed correctly

- [ ] 6.5 Integration: Webhook processing (`tests/integration/test_webhook.py`)
  - Valid signature → 200 + task enqueued
  - Invalid signature → 403
  - Duplicate wa_message_id → no double-update
  - STOP keyword → suppression list entry created

## Phase 7: Docs & DevEx

- [ ] 7.1 README.md
  - Prerequisites, quick start (`docker compose up`)
  - Ngrok setup for webhook testing
  - Meta App webhook configuration steps
  - Environment variable reference
  - Deployment notes (production checklist)

- [ ] 7.2 Bruno/Postman collection
  - Auth flow (login → get token)
  - Full campaign lifecycle
  - Webhook simulation requests
  - Inbox endpoints

- [ ] 7.3 Database init script
  - `scripts/init_db.py`: creates indexes, seeds a default super_admin user
