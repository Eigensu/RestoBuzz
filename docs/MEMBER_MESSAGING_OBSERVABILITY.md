# Member Messaging Observability

Two questions this answers:

1. **Per member** — how many campaign messages has this member received, and how
   many did they read? Shown as a column in the members list.
2. **Per period** — how many new members did marketing actually produce? Shown
   in Reports → Members.

## Why a separate collection

`message_logs` carries a TTL of `MESSAGE_LOG_TTL_DAYS` (30 — `app/database.py`).
Aggregating it would silently produce a *rolling 30-day* number that resets as
rows expire, which is not what "how many messages has this member received"
means.

So counters live in **`member_message_stats`**, written as sends and webhooks are
observed, with **no TTL**. It is keyed by `(restaurant_id, phone_key)` rather
than by member `_id` because r2's members live in an external database
(Fielia's `test.cards`, see `member_match_service`) that we cannot write to. A
phone-keyed rollup in our own DB works for internal and external members alike.

`phone_key` is the last 10 digits (`dormancy_service.normalize_phone_for_match`),
matching the convention already used across the codebase, so a member row, a
Fielia card, and a `message_logs.recipient_phone` all collapse to one key.

### Shape

```jsonc
{
  "restaurant_id": "r1",
  "phone_key": "9876543210",
  "sent_count": 12,          // Meta accepted it
  "received_count": 11,      // reached the device
  "read_count": 7,           // read receipt came back
  "first_sent_at": "…", "last_sent_at": "…",
  "last_received_at": "…", "last_read_at": "…",
  "last_campaign_id": ObjectId,
  "touches": [               // capped at TOUCH_HISTORY_LIMIT (20)
    { "campaign_id": ObjectId, "at": "…" }
  ]
}
```

## Counting rules

Written from two places:

| Where | When | Effect |
|---|---|---|
| `send_task._do_send` | Meta accepts the message | `sent_count +1`, append touch |
| `webhook_task._handle_statuses` | status webhook | received / read per the table below |

Increments are driven by the **status transition**, using the before-image
`message_logs` already fetches, not by the raw webhook. Meta redelivers status
webhooks and the Redis dedup is best-effort (it expires), so the transition rule
is the real guard. These counters can never be recomputed once `message_logs`
expires, which makes any double-count permanent.

| prev → new | received | read |
|---|---|---|
| `sent` → `delivered` | +1 | — |
| `delivered` → `delivered` | — | — |
| `sent` → `read` (delivered webhook skipped) | +1 | +1 |
| `delivered` → `read` | — | +1 |
| `read` → anything | — | — |

A message therefore contributes at most 1 to each counter, and `read_count` can
never exceed `received_count`.

Stats writes are wrapped in try/except: bookkeeping must never break a send or a
webhook.

## Accuracy caveats — say these out loud when reading the numbers

- **"Read" depends on WhatsApp read receipts**, which recipients can switch off.
  A member showing 0 reads may have them disabled rather than be ignoring you.
  The members-list cell says so in its tooltip.
- **`sent - received`** is messages Meta accepted but never confirmed delivered
  (unreachable number, deleted account, phone off for the whole validity window).
- **History before this shipped is gone.** `message_logs` older than 30 days was
  already deleted by MongoDB and is not recoverable from any source.

## Acquisition attribution

`GET /reports/members/acquisition` splits new members in a date range into three
buckets, kept apart because they are not equally certain:

- **`direct`** — created by their own reply to a campaign
  (`source: "campaign_reply"`, stamped by `webhook_task._handle_interested_reply`).
  Causal, nothing inferred.
- **`assisted`** — joined by some other route within
  `ATTRIBUTION_WINDOW_DAYS` (7) of a campaign reaching their phone, per the
  `touches` array. A strong signal, but correlation, not proof.
- **`organic`** — no campaign contact before joining.

Attribution is computed at query time, so it works retroactively as touch
history accumulates and needs no hook at member-creation time — which matters
because r2's members are created in Fielia's database, where we have no hook at
all.

`tracking_started_at` in the response is the earliest `first_sent_at` we hold for
the restaurant. Attribution is blind to campaigns before that, so an early, low
number is a coverage artifact and not a marketing verdict. The UI prints it.

## Backfill

```bash
python scripts/backfill_member_message_stats.py              # dry run
python scripts/backfill_member_message_stats.py --apply      # seed new rollups
python scripts/backfill_member_message_stats.py --apply --overwrite
```

`--apply` only creates rollups that don't exist yet. `--overwrite` replaces
existing ones with a full recomputation from `message_logs` — **only safe in the
first days after deploy**, while the logs still cover everything the counters
have seen. Run it months later and you replace lifetime counts with the last 30
days.

Recovery is capped at ~30 days regardless. Counts are exact from deploy forward.
