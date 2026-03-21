# WhatsApp Bulk Sender — Requirements

## Overview
An enterprise-grade admin platform for dispatching bulk WhatsApp Template messages via Meta Cloud API, with a real-time inbox for inbound replies, robust retry/idempotency engine, and full observability.

## Functional Requirements

### FR-1: Authentication & RBAC
- FR-1.1: JWT-based auth with refresh tokens (FastAPI backend).
- FR-1.2: Roles: `super_admin`, `admin`, `viewer`.
- FR-1.3: `admin`+ can create/send campaigns; `viewer` is read-only.
- FR-1.4: All auth events written to audit log.

### FR-2: Contact Import & Validation
- FR-2.1: Accept `.xlsx`, `.xls`, `.csv` uploads (max 50MB).
- FR-2.2: Parse first sheet by default; allow sheet selection for multi-sheet Excel.
- FR-2.3: Normalize all phone numbers to E.164 using `phonenumbers` library.
- FR-2.4: Pre-flight validation screen showing:
  - Valid count, invalid count (with reason), duplicate count.
  - Duplicates within file and against global suppression list.
- FR-2.5: Column mapping UI: `name`, `phone`, and up to 10 template variable columns.
- FR-2.6: Export invalid rows as CSV from pre-flight screen.

### FR-3: Template Management
- FR-3.1: Sync approved templates from Meta API on demand and on schedule (every 6h).
- FR-3.2: Display template category (MARKETING / UTILITY), language, status.
- FR-3.3: Render variable inputs (`{{1}}`, `{{2}}`) dynamically from template JSON.
- FR-3.4: Support header types: TEXT, IMAGE, DOCUMENT (PDF).
- FR-3.5: Media upload to Cloudinary; enforce 5MB image / 16MB PDF limits client-side and server-side.

### FR-4: Campaign Creation Wizard
- FR-4.1: Step 1 — Upload contacts + column mapping.
- FR-4.2: Step 2 — Pre-flight validation review.
- FR-4.3: Step 3 — Select template + fill variables + media upload.
- FR-4.4: Step 4 — Schedule (send now or future datetime) + priority (MARKETING / UTILITY).
- FR-4.5: Step 5 — Review & confirm with estimated send time.
- FR-4.6: Mandatory "Unsubscribe" footer toggle for MARKETING category templates.

### FR-5: Messaging Engine
- FR-5.1: Message lifecycle: `queued → sending → sent → delivered → read → failed`.
- FR-5.2: Atomic claiming via `find_one_and_update` with `locked_until = now + 60s`.
- FR-5.3: Priority queue: UTILITY messages processed before MARKETING.
- FR-5.4: Automatic fallback to secondary WABA if primary fails; log `fallback_used: true`.
- FR-5.5: Token Bucket rate limiter in Redis capped at 80 messages/second.
- FR-5.6: Exponential backoff retry: 3 attempts, delays 30s / 5m / 30m.
- FR-5.7: Distributed lock (Redlock) per message to prevent double-send on worker crash.
- FR-5.8: Deduplication: store `wa_message_id` in Redis with 24h TTL.

### FR-6: Real-time Progress
- FR-6.1: SSE endpoint streams per-campaign counters: sent / delivered / read / failed.
- FR-6.2: Dashboard shows live progress bar per campaign.
- FR-6.3: Campaign detail page shows per-message status table with pagination.
- FR-6.4: Export failed recipients as CSV with Meta error code and description.

### FR-7: Webhook Receiver
- FR-7.1: Verify `X-Hub-Signature-256` on every inbound webhook.
- FR-7.2: Return `200 OK` immediately; process asynchronously via Celery.
- FR-7.3: Handle status updates: `sent`, `delivered`, `read`, `failed`.
- FR-7.4: Handle inbound messages: text, image, document, location, sticker.
- FR-7.5: Log malformed payloads to `webhook_errors` collection without crashing.
- FR-7.6: Deduplicate webhook events using `wa_message_id` Redis cache.

### FR-8: WhatsApp-style Inbox
- FR-8.1: Two-pane layout: conversation list (left) + chat thread (right).
- FR-8.2: Conversation list shows: contact name/phone, last message snippet, unread badge, timestamp.
- FR-8.3: Chat thread renders: text bubbles, image thumbnails, PDF chips, location maps.
- FR-8.4: Mark as read on open; unread count in sidebar badge.
- FR-8.5: Reply from inbox (text only, v1).
- FR-8.6: Mobile responsive: list collapses when thread is open.
- FR-8.7: Real-time new message indicator via SSE.

### FR-9: Suppression / Opt-out
- FR-9.1: Global suppression list (opt-outs + blocked numbers).
- FR-9.2: Inbound "STOP" keyword auto-adds sender to suppression list.
- FR-9.3: Suppressed numbers skipped at campaign dispatch time.
- FR-9.4: Manual add/remove from suppression list in Settings.

### FR-10: Observability & Audit
- FR-10.1: Structured JSON logs with `correlation_id` per job.
- FR-10.2: Audit log: who created/sent/cancelled which campaign and when.
- FR-10.3: Flower UI exposed for Celery worker monitoring.
- FR-10.4: Health check endpoint `/health` returning service statuses.

## Non-Functional Requirements

- NFR-1: API p95 latency < 200ms for read endpoints.
- NFR-2: Webhook receiver must respond within 500ms.
- NFR-3: System must handle 1M contacts per campaign (streamed, not loaded into memory).
- NFR-4: All secrets via environment variables; no hardcoded credentials.
- NFR-5: Docker Compose brings up full stack with a single `docker compose up`.
