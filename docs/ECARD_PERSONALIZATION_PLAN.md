# Personalized E-Card Campaigns — Design & Implementation Plan

> Status: **Proposed** · Owner: TBD · Prereq: Cloudinary already configured
> (`app/services/cloudinary_service.py`); per-message `media_url` already flows
> through the send pipeline (`app/workers/send_task.py`, `app/services/meta_api.py`).

## Context

We want to send a WhatsApp e-membership card where **the artwork is identical for
everyone but the member's name is rendered onto the card image**, driven by an
uploaded Excel of `name, number`. Each recipient gets their own card plus a fixed
message and a **"Get the benefits" quick-reply button** (which reuses the existing
benefits auto-reply).

### Why this is a small change, not a new subsystem

The send path already carries a **per-message `media_url`**:

- `campaigns.py` writes one `media_url` per recipient into each `message_logs` doc
  (currently the same constant `body.media_url` for all — `campaigns.py:276`).
- `meta_api._build_payload` injects that URL as the template's image header at send
  time via `{"link": media_url}` (`meta_api.py:89-96`). Meta fetches it per message.

So "name changes per card" reduces to: **compute a different `media_url` per
recipient** — a Cloudinary transformation URL that overlays the name onto a single
base card. Dispatch, smart-retries, delivery/read webhooks and counters are all
**unchanged**.

Design goals:
- **No pipeline changes** — reuse `message_logs.media_url`, `send_task`, `meta_api`.
- **No per-recipient image storage** — one base upload; names overlaid via URL.
- **WYSIWYG** — the wizard preview *is* the Cloudinary URL that gets sent.

---

## 1. Rendering: Cloudinary text-overlay URL

Upload the blank card **once** (existing `POST /media/upload` → `public_id`). Build a
per-recipient URL by adding a text-overlay layer:

```
https://res.cloudinary.com/<cloud>/image/upload/
  co_rgb:ffffff,l_text:Georgia_64_bold:Aarav%20Mehta,g_north,y_420,c_fit,w_900/
  fielia_card
```

- `l_text:<font>_<size>_<style>:<text>` — the overlaid name.
- `g_<gravity>,x_,y_` — position of the name box on the card.
- `co_rgb:<hex>` — text color.
- `c_fit,w_<px>` — max width so long names shrink instead of overflowing.

**Name encoding is the one sharp edge.** Cloudinary text layers treat `,` `/` `%` as
delimiters — names must be double-encoded (` ` → `%20`, `,` → `%252C`, etc.). Use the
Cloudinary SDK's transformation builder or a dedicated encode helper; do **not**
hand-concatenate. Reject/normalize empty names.

Custom brand font: upload the `.ttf`/`.otf` to Cloudinary once and reference it by
`public_id` in `l_text` (falls back to a built-in font if omitted).

---

## 2. Data model

Add an optional **`personalization`** block on the `campaign_jobs` doc (absent = today's
behavior, static header):

```jsonc
{
  "personalization": {
    "type": "ecard_name_overlay",
    "base_public_id": "whatsapp-media/abc123",   // uploaded blank card
    "overlay": {
      "font": "Georgia",       // or a Cloudinary custom-font public_id
      "font_size": 64,
      "font_weight": "bold",
      "color": "ffffff",
      "gravity": "north",
      "x": 0,
      "y": 420,
      "max_width": 900
    }
  }
}
```

The base card and overlay config are chosen once per campaign; only the name varies.

---

## 3. New service — `app/services/ecard_service.py`

```python
def build_card_url(base_public_id: str, name: str, overlay: dict) -> str:
    """Cloudinary delivery URL for `base_public_id` with `name` overlaid.
    Encodes the name safely for l_text and applies c_fit,w_<max_width>."""
```

Pure and unit-testable (no network). Tests: spaces, commas, `&`, emoji, very long
names, empty name, custom-font public_id.

---

## 4. Campaign creation change (the only send-path edit)

In `campaigns.py`, where `message_docs` is built (`campaigns.py:265-293`):

```python
perso = job_doc.get("personalization")
...
"media_url": (
    build_card_url(perso["base_public_id"], c.get("name", ""), perso["overlay"])
    if perso else body.media_url
),
```

That's it — `send_task`/`meta_api` need **no** changes.

**Guard:** e-card campaigns require a non-empty name per contact. Extend the existing
"strip email-only contacts" step (`campaigns.py:251`) to also flag/skip rows with a
blank name (surface the count in the preflight summary from `parse_contacts`).

---

## 5. WhatsApp template (the real lead-time item)

Submit **one** approved template for the restaurant's WABA:

- **HEADER**: `IMAGE` (personalized per recipient at send time).
- **BODY**: the fixed Fielia welcome copy (no variables — the name is on the card).
- **BUTTONS**: one `QUICK_REPLY` — **"Get the benefits"**. Tapping it hits the existing
  `get_benefits` handler (`webhook_task.py:559-583`) which sends `settings.benefits_link`.
  Confirm the button payload/text matches that handler (`payload == "get_benefits"` or
  text `"get the benefits"`).

⚠️ Meta approval takes hours–a day. **Submit this first**, in parallel with the build.

Template creation already supports image headers via
`templates.py` + `create_media_handle_from_url` — reuse the existing template UI to
submit it.

---

## 6. Frontend — wizard step

Reuse the existing WhatsApp campaign wizard. Add a "Personalize card" step shown when
the chosen template has an IMAGE header:

1. Upload blank card → `POST /media/upload` → `base_public_id`.
2. Live preview: position the name box (drag or x/y inputs), pick font/size/color.
   The preview `<img src>` is literally `build_card_url(base, "Sample Name", overlay)`
   — WYSIWYG, no separate render.
3. Persist `personalization` with the campaign create payload.

Excel import is unchanged — `parse_contacts` already auto-detects `name`/`phone`
(`contact_parser.py:28`, `:14`).

---

## 7. Constraints & checks

- **Image header cap**: WhatsApp header images ≤ 5 MB, JPG/PNG. Cloudinary output of a
  reasonable card is well under this; add `f_jpg,q_auto` to the transformation to be safe.
- **Meta fetches each URL at send time** — per-message `{"link": url}` header override is
  supported for approved image-header templates. No re-approval per recipient.
- **Long/RTL/emoji names** — covered by `c_fit,w_` + safe encoding; unit-test these.
- **Cost/latency** — zero extra uploads; one base image; URLs are CDN-cached by name.

---

## 8. Work breakdown

| # | Task | Est. |
|---|------|------|
| 0 | Submit the IMAGE-header + quick-reply template to Meta (unblock approval) | 30 min + wait |
| 1 | `ecard_service.build_card_url` + unit tests | 0.5 d |
| 2 | `personalization` on campaign create + per-recipient `media_url` + name guard | 0.5 d |
| 3 | Wizard "Personalize card" step with live Cloudinary preview | 1–1.5 d |
| 4 | E2E test: import 3-row sheet → 3 distinct card URLs → send on test WABA | 0.5 d |

No changes to dispatch, smart-retries, webhooks, billing, or counters.
