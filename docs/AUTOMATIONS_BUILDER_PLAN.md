# Automations Builder — Design & Implementation Plan (Part 3)

> Status: **Proposed** · Owner: TBD · Prereq: the hardcoded "Interested members"
> rule (shipped on `feat/smart-retries`, commit `19b4acc`).

## Context

We shipped a single **hardcoded** automation: when a contact replies to a
WhatsApp campaign with a positive keyword, they're upserted as an `interested`
member (`apps/backend/app/workers/webhook_task.py::_handle_interested_reply`).

That logic is useful but frozen — restaurants can't change the keywords, choose a
different action, or add their own rules. **Part 3** turns it into a
**user-configurable rules engine**: a restaurant admin builds
`trigger → conditions → actions` rules in the UI, and the webhook pipeline
evaluates them at runtime. The existing hardcoded rule becomes the first
**seeded default automation**, so behavior is unchanged on day one.

Design goals:
- **No behavior regression** — migrate the hardcoded rule to a seeded record; the
  engine produces the identical effect.
- **Extensible** — adding a new trigger or action type is a small, localized change.
- **Safe** — a broken/expensive rule must never block or crash webhook
  processing (it's on the hot path for every inbound message).
- **Restaurant-scoped & admin-gated** — same access model as the rest of the app.

---

## 1. Data model

New Mongo collection **`automations`** — one document per rule:

```jsonc
{
  "_id": ObjectId,
  "restaurant_id": "r1",
  "name": "Tag interested repliers",
  "enabled": true,
  "trigger": {
    "type": "campaign_reply",          // enum, see §2
    "match": {
      "mode": "keywords",              // "keywords" | "any" | "exact"
      "keywords": ["yes", "yeah", "interested", "sure", "ok", "👍"],
      "case_sensitive": false
    },
    "campaign_scope": "all"            // "all" | { "campaign_ids": [...] }
  },
  "conditions": [                       // ALL must pass (AND). Empty = always.
    // e.g. { "field": "is_existing_member", "op": "eq", "value": false }
  ],
  "actions": [
    {
      "type": "tag_as_member",         // enum, see §3
      "params": { "segment": "interested", "member_type": "interested" }
    }
  ],
  "stats": { "fired_count": 0, "last_fired_at": null },
  "created_by": "user_id",
  "created_at": ISODate,
  "updated_at": ISODate
}
```

Index: `{ restaurant_id: 1, enabled: 1 }` (the engine's lookup key).

Pydantic models in **`apps/backend/app/models/automation.py`** (mirror the style
of `app/models/campaign.py`): `AutomationTrigger`, `AutomationCondition`,
`AutomationAction`, `AutomationCreate`, `AutomationUpdate`, `AutomationResponse`,
`AutomationListResponse`. Use `Literal` enums for `trigger.type`, `match.mode`,
and `action.type` so unknown values are rejected at the API boundary.

---

## 2. Triggers (extensible registry)

Start with **`campaign_reply`** (the only one the current pipeline needs). The
trigger fires inside `_process_inbound_message` after reply-matching, when an
inbound message was matched to an outbound campaign message (`orig_msg`).

Trigger evaluation inputs (an "event context" dict): `restaurant_id`,
`inbound_msg`, `body`, `from_phone`, `sender_name`, `orig_msg` (the matched
campaign `message_log`), and the resolved `campaign_job`.

Future trigger types (design for them, don't build): `inbound_message` (any
message, no campaign needed), `message_delivered`, `member_dormant`,
`campaign_completed`. Each new type is a new `match`/evaluator branch — the
engine shape doesn't change.

---

## 3. Actions (extensible registry)

Ship two, structured so a third is a ~30-line addition:

| `action.type`        | params                                  | effect |
|----------------------|-----------------------------------------|--------|
| `tag_as_member`      | `segment`, `member_type`                | The current behavior: upsert member by `(restaurant_id, phone)`, `$addToSet` the tag, `$setOnInsert` a new doc. |
| `add_to_suppression` | `reason`                                | Reuse `app/services/suppression.py::add_suppression`. |

Roadmap actions (not now): `send_auto_reply` (generalizes the benefits
auto-reply at `webhook_task.py::_send_benefits_reply`), `notify_staff`,
`add_tag` (tag-only, no member creation), `webhook_post`.

Each action is a small async function `async def run(db, ctx, params) -> None`
registered in a dict keyed by type. The engine looks up and awaits them.

---

## 4. The engine

New service **`apps/backend/app/services/automation_service.py`**:

```python
async def run_automations(db, trigger_type: str, ctx: dict) -> None:
    """Load enabled automations for ctx['restaurant_id'] matching trigger_type,
    evaluate trigger.match + conditions, and run actions. Never raises."""
```

Behavior:
- Query `automations` by `{restaurant_id, enabled: True, "trigger.type": trigger_type}`.
- For each: check `campaign_scope`, evaluate `trigger.match` against `body`, then
  evaluate `conditions` (AND). On full match, run each action via the registry;
  `$inc stats.fired_count` and set `last_fired_at`.
- **Hot-path safety:** wrap the whole call (and each action) in try/except —
  log `automation_eval_failed` and continue. A bad rule must never break
  inbound webhook processing. Consider a per-message cap on rules evaluated.
- **Caching:** automations change rarely. Cache the per-restaurant rule set in
  Redis (short TTL, e.g. 60s) keyed by `restaurant_id`, invalidated on any
  CRUD write, to avoid a Mongo read on every inbound message.

### Integration point

In `webhook_task.py::_process_inbound_message`, **replace** the direct
`_handle_interested_reply(...)` call with:

```python
await run_automations(db, "campaign_reply", {
    "restaurant_id": restaurant_id, "body": body, "from_phone": from_phone,
    "sender_name": sender_name, "orig_msg": orig_msg, "inbound_msg": msg,
})
```

Keep the STOP-keyword check ahead of it (STOP suppression is not an automation).
Once migrated, `_handle_interested_reply` can be deleted (its logic moves into
the `tag_as_member` action).

---

## 5. Migration of the hardcoded rule

Add a one-time seeder (script in `apps/backend/scripts/` + idempotent startup
check): for every restaurant without a `campaign_reply` automation, insert the
default "Tag interested repliers" rule using the exact current keyword set and
`tag_as_member → interested`. This guarantees zero behavior change at cutover.

`INTERESTED_KEYWORDS` in `webhook_task.py` becomes the seeder's default list
(single source of truth) and can then be removed from the hot path.

---

## 6. API

New router **`apps/backend/app/routers/automations.py`**, registered in
`app/main.py` alongside the others (`app.include_router(automations.router,
prefix="/api")`, near line 100). Reuse existing dependencies from
`app/dependencies.py`:

| Method & path                | Role                    | Purpose |
|------------------------------|-------------------------|---------|
| `GET /automations`           | `require_role("viewer")`| list rules for active restaurant |
| `POST /automations`          | `require_role("admin")` | create rule |
| `PATCH /automations/{id}`    | `require_role("admin")` | update / enable-disable |
| `DELETE /automations/{id}`   | `require_role("admin")` | delete rule |

Scope every query by the active restaurant via `get_active_restaurant`
(as `members.py` does). Validate `action.type` / `trigger.type` against the
registries so the UI can't persist an unsupported type. Invalidate the Redis
rule cache on every write.

---

## 7. Frontend

New route **`apps/frontend/app/(dashboard)/automations/page.tsx`** + a nav entry
in `app/(dashboard)/layout.tsx` `NAV` array (near line 44, after Members; e.g.
`{ href: "/automations", label: "Automations", icon: Zap }`).

UI (follow the Members page patterns — TanStack Query, `@/lib/api`, `toast`,
`BRAND_GRADIENT`):
1. **List view** — cards/rows showing name, enabled toggle, trigger summary
   ("When someone replies yes/interested to any campaign"), action summary
   ("Add to Interested members"), and `fired_count`.
2. **Builder modal/page** — a guided form, not raw JSON:
   - **Trigger:** dropdown (initially just "Campaign reply") → match mode
     (keywords / any / exact) → editable keyword chips → campaign scope
     (all / pick campaigns).
   - **Action:** dropdown ("Add to member segment" / "Suppress") → params
     (segment name, e.g. "interested").
   - Save → `POST/PATCH /automations`.
3. Enable/disable toggle → `PATCH`. Delete with confirm.

Add an `Automation` type to `apps/frontend/types/index.ts`.

Optional: a per-campaign **"Capture interested replies"** convenience toggle in
the WhatsApp campaign create flow
(`app/(dashboard)/campaigns/whatsapp/new`) that writes a scoped automation —
nice onboarding, but the standalone Automations page is the primary surface.

---

## 8. Build order

1. Models + collection + index (`models/automation.py`).
2. Engine service with the two actions + trigger evaluator, fully unit-tested
   with `AsyncMock` (mirror `tests/unit/test_interested_reply.py`).
3. Swap the webhook call to `run_automations`; seeder for the default rule.
   **Verify parity** — existing interested-capture behavior is unchanged.
4. API router + cache invalidation.
5. Frontend list + builder + nav entry.
6. (Later) additional triggers/actions, per-campaign toggle.

Phases 1–3 are shippable on their own (engine running the seeded default, no UI);
4–5 add user authoring.

---

## 9. Verification

- **Unit:** engine matches keywords correctly, respects `enabled`,
  `campaign_scope`, and conditions; each action does the right DB write; a
  throwing action is swallowed and logged (hot-path safety).
- **Parity:** with only the seeded default rule, replying "yeah" to a campaign
  produces the same `interested`-tagged member as the pre-migration code.
- **API:** CRUD scoped by restaurant; non-admin blocked; invalid action/trigger
  type rejected; cache invalidated after writes.
- **E2E:** create a rule in the UI → send a synthetic inbound webhook → confirm
  the action fires and `stats.fired_count` increments.
- **Negative:** disabled rule never fires; STOP keyword still suppresses and is
  not treated as an automation; malformed rule doesn't break webhook ingestion.
