# Local Dev Setup (No Docker)

## Prerequisites

- Node.js 22+ and pnpm 9+
- Python 3.12+
- MongoDB running locally (port 27017)
- Redis running locally (port 6379)

### Install MongoDB (macOS)

```bash
brew tap mongodb/brew
brew install mongodb-community@7.0
brew services start mongodb-community@7.0
```

### Install Redis (macOS)

```bash
brew install redis
brew services start redis
```

---

## 1. Open the workspace

Open `whatsapp-bulk-sender.code-workspace` in VS Code (File → Open Workspace from File).

---

## 2. Frontend setup

```bash
pnpm install
```

---

## 3. Backend setup

```bash
cd apps/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy and fill in your env:

```bash
cp .env.example .env
# Edit .env with your Meta API keys, Cloudinary, JWT secret
```

Init the database (creates indexes + default admin user):

```bash
cd apps/backend
source .venv/bin/activate
python scripts/init_db.py
# Default login: admin@example.com / changeme123
```

---

## 4. Run everything (4 terminals)

**Terminal 1 — Backend API**

```bash
cd apps/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Celery Worker**

```bash
cd apps/backend
source .venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info -Q utility,marketing
```

**Terminal 3 — Celery Beat (scheduler)**

```bash
cd apps/backend
source .venv/bin/activate
celery -A app.workers.celery_app beat --loglevel=info
```

**Terminal 4 — Frontend**

```bash
pnpm dev:frontend
# or: cd apps/frontend && pnpm dev
```

**Optional — Flower (Celery monitor)**

```bash
cd apps/backend
source .venv/bin/activate
celery -A app.workers.celery_app flower --port=5555
```

---

## URLs

| Service     | URL                        |
| ----------- | -------------------------- |
| Frontend    | http://localhost:3000      |
| Backend API | http://localhost:8000/docs |
| Flower      | http://localhost:5555      |

---

## Run Tests

```bash
cd apps/backend
source .venv/bin/activate
pytest tests/unit -v
```

---

## VS Code Tasks (shortcut)

Use `Cmd+Shift+P` → "Tasks: Run Task" to run any of the pre-configured tasks:

- Setup Backend Venv
- Install Frontend Deps
- Run Frontend Dev
- Run Backend Dev
- Run Celery Worker
- Run Flower
- Init DB
- Run Unit Tests

Critical fixes

Resolve the webhook contradiction.

The prompt says to validate the Hub signature, but also says to “always return 200 OK to Meta immediately.” Those two rules conflict. Meta’s webhook flow expects successful verification to return the hub.challenge with 200, but failed verification/signature checks should return 401. The spec should say: verify raw body first, reject invalid signatures, ACK valid payloads immediately, then process asynchronously. 

Replace Motor in a greenfield 2026 build.

MongoDB now recommends the PyMongo Async API instead of Motor; Motor is deprecated and only in limited support. If this is meant to be production-grade from day one, the prompt should switch from Motor to PyMongo Async unless you have a legacy constraint. 

Your webhook dedupe key is wrong.

“Store wa_message_id in Redis for 24 hours” is too coarse. A single WhatsApp message can legitimately produce multiple status events over time, so deduping only on wa_message_id risks dropping real delivered and read transitions. Use an event fingerprint like wa_message_id + event_type/status + timestamp, or hash a normalized webhook payload.

Add outbound idempotency, not just inbound dedupe.

The prompt handles duplicate webhook processing, but not duplicate sends caused by worker crash/retry before wa_message_id exists. You need an internal idempotency key such as campaign_id + recipient_id + template_id + variable_hash + media_hash, enforced before calling Meta.

Do not mix Mongo claiming and Redlock unless you define exact boundaries.

find_one_and_update with locked_until is already a lease-based claim mechanism. If you also add Redlock, the prompt should specify what Redis locks protect: scheduler singleton, per-recipient serialization, template sync, or something else. Otherwise you end up with two overlapping ownership systems and harder failure modes.

Make rate limits and priorities configurable, not hardcoded.

Meta’s official collection documents Cloud API throughput at 80 mps by default with eligibility for up to 1000 mps, so hardcoding 80 everywhere is brittle. Also, “Marketing vs Utility” is too narrow; template metadata includes category and Meta supports authentication templates too, so priority should be configurable by category/sender, not a fixed two-lane queue. 

Model the 24-hour session rule in the inbox.

Your inbox spec needs explicit composer rules: inside the active user-initiated session, agents can send free-form replies; outside it, they should be forced into approved templates. Meta’s own quickstart/docs call out the 24-hour user-initiated conversation session. 

Important gaps

The media strategy is too narrow.

The prompt forces Cloudinary URLs, but Meta supports both public self-hosted media links and Meta-hosted media IDs for images/documents. A better spec is: support both modes, use Meta-hosted upload for reliability-sensitive campaigns, and use public-link mode only when intentional. 

Snapshot templates at campaign creation.

The template APIs expose category, components, language, name, and status. If you only fetch live template JSON at send time, a template edit can silently change an in-flight campaign. Add a TemplateSnapshot stored when the campaign is created. 

Remove “or” decisions from core architecture.

“NextAuth.js or JWT-based FastAPI Auth” and “WebSockets or SSE” are too open-ended for an enterprise prompt. Pick one auth authority model and one real-time transport per use case, or explicitly assign them: for example, SSE for campaign progress, WebSocket for inbox live updates.

Define what “Premium” and “Standard” fallback actually mean.

In the current text, those are undefined terms. The prompt should say whether fallback means another phone number, another WABA, or another provider abstraction, and what checks must pass before fallback is allowed: template parity, branding, suppression list consistency, audit attribution, and reporting.

Import/export needs hardening.

Add max file size, max rows, streaming parse for large files, BOM/encoding handling, explicit default-country handling for numbers without +, ambiguous-number rules, and protection against Excel/CSV formula injection in exported failure reports.

Compliance is underspecified.

An “unsubscribe footer toggle” is not enough. Add opt-in evidence storage, auto-suppression on inbound opt-out keywords, quiet hours/send windows, suppression re-check right before dispatch, GDPR/CCPA retention/deletion flows, and role-restricted export of PII.

The data model is too thin for operations.

CampaignJob and MessageLog need more than the fields listed. You’ll want created_by, scheduled_at, started_at, finished_at, waba_id, phone_number_id, current_status, last_error_code, next_retry_at, locked_by, correlation_id, template_language, variables_payload, and probably separate MessageAttempt, Conversation, Contact, and WebhookEvent collections.

Observability and acceptance criteria need to be explicit.

“Structured logs” is not enough. Add metrics and alerts for queue depth, claim lag, 429s, duplicate webhook drops, send latency, status lag, opt-out rate, dead-letter count, and dashboard freshness. Also define success criteria: p95 webhook ACK latency, max campaign size, recovery behavior after worker crash, minimum test coverage, and load-test targets.

Best single-sentence summary

Your prompt is strong on features, but weak on contracts: webhook rules, idempotency keys, queue ownership, auth model, session rules, and operational acceptance criteria need to be spelled out much more tightly.

these are
