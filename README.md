# WhatsApp Bulk Sender

Enterprise-grade WhatsApp bulk messaging platform built with Next.js 16, FastAPI 0.135, MongoDB, Redis, and Celery.

## Stack

- Frontend: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui, TanStack Query v5
- Backend: FastAPI 0.135, Python 3.12, Pydantic v2, Motor (async MongoDB)
- Queue: Celery 5.6 + Redis 7, Flower for monitoring
- Storage: Cloudinary (media headers)
- DB: MongoDB 7

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Fill in your Meta API credentials, Cloudinary keys, and JWT secret
```

### 2. Start all services

```bash
docker compose up --build
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs
- Flower (Celery): http://localhost:5555

### 3. Initialize the database

```bash
docker compose exec backend python scripts/init_db.py
# Default admin: admin@example.com / changeme123
```

## Webhook Setup (Local Dev with Ngrok)

```bash
# Install ngrok: https://ngrok.com/download
ngrok http 8000

# Copy the HTTPS URL, e.g. https://abc123.ngrok.io
# In Meta Developer Console:
#   Webhook URL: https://abc123.ngrok.io/api/webhooks/meta
#   Verify Token: (value of META_WEBHOOK_VERIFY_TOKEN in .env)
#   Subscribe to: messages, message_status_updates
```

## Meta App Configuration

1. Create a Meta App at https://developers.facebook.com
2. Add WhatsApp product
3. Get Phone Number ID and Access Token → set in `.env`
4. Configure webhook URL and verify token (see above)
5. Subscribe to `messages` and `message_status_updates` fields

## Running Tests

```bash
# Unit tests (no external services needed)
docker compose exec backend pytest tests/unit -v

# Integration tests (requires running mongo + redis)
docker compose exec backend env INTEGRATION=1 pytest tests/integration -v
```

## Environment Variables

See `.env.example` for all required variables with descriptions.

Key variables:
- `META_PRIMARY_PHONE_ID` / `META_PRIMARY_ACCESS_TOKEN` — Primary WABA
- `META_FALLBACK_PHONE_ID` / `META_FALLBACK_ACCESS_TOKEN` — Fallback WABA
- `META_WEBHOOK_SECRET` — App secret for HMAC signature verification
- `JWT_SECRET` — 64-char random hex string
- `CLOUDINARY_*` — Cloudinary credentials for media uploads

## Production Checklist

- [ ] Set strong `JWT_SECRET` (64+ char random hex)
- [ ] Set `META_WEBHOOK_SECRET` to your Meta App Secret
- [ ] Use MongoDB Atlas or a replica set (not standalone)
- [ ] Use Redis with persistence (`appendonly yes`)
- [ ] Set `CELERY_CONCURRENCY` based on your CPU count
- [ ] Put backend behind a reverse proxy (nginx/caddy) with TLS
- [ ] Restrict CORS origins in `app/main.py`
- [ ] Enable MongoDB authentication
- [ ] Set up log aggregation (Datadog, Loki, etc.)

## API Documentation

Interactive docs available at http://localhost:8000/docs (Swagger UI) and http://localhost:8000/redoc.

## Bruno/Postman Collection

Import `api-collection.json` from the repo root into Bruno or Postman for pre-built requests covering:
- Auth flow (login → refresh → me)
- Campaign lifecycle (create → start → pause → cancel)
- Contact upload + preflight
- Webhook simulation
- Inbox endpoints
