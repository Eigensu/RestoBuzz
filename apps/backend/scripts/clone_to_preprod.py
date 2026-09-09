"""Clone the production MongoDB into a preprod/UAT database, masking PII.

Copies every collection from the source (prod) database into a destination
database (default name: dishpatch-uat), replacing customer-identifying
fields (names, phones, emails, WhatsApp identity IDs) with deterministic
fake values. "Deterministic" means the same original value always produces
the same masked value, everywhere it appears — this is what keeps a masked
member's phone number matching their masked conversation thread, their
masked wa_identities record, etc. Re-running the script reproduces the same
masked dataset rather than randomizing it again.

Setup:
    Put the destination connection details in RestoBuzz/.env.preprod.local
    (git-ignored — matches the `.env.*.local` pattern in .gitignore):

        PREPROD_MONGO_URI=mongodb+srv://user:pass@host/?appName=...
        PREPROD_DB_NAME=dishpatch-uat

Usage:
    python scripts/clone_to_preprod.py            # interactive, asks to confirm
    python scripts/clone_to_preprod.py --yes       # non-interactive
    python scripts/clone_to_preprod.py --only members,restaurants
    python scripts/clone_to_preprod.py --dev-password "SomeOtherPassword1!"

Safety:
    - Refuses to run if the destination resolves to the same host+db as the
      source (never overwrites prod).
    - Never writes to the source connection — read-only cursors only.
    - Drops the destination database first, so re-runs produce a clean,
      reproducible clone rather than an accumulating mess.
    - Restaurants' WhatsApp phone_id/waba_id are replaced with fake IDs by
      default, so preprod cannot fire a real WhatsApp send even if a real
      access token is later set in its environment (the access token itself
      is never in Mongo — see app/models/restaurant.py).
    - Dead-letter/raw-payload collections (failed_webhooks, webhook_errors,
      sync_logs) are skipped entirely: they hold unstructured raw webhook
      payloads that field-name-based masking can't safely reach.
"""

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import BulkWriteError, PyMongoError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.preprod.local"

sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.services.dormancy_service import normalize_phone_for_match  # noqa: E402

MASK_SALT = "restobuzz-preprod-mask-v1"

# Raw/dead-letter collections holding unpredictable payloads — not safe to
# mask by field name, and not needed to test features. Skipped entirely.
EXCLUDED_COLLECTIONS = {"failed_webhooks", "webhook_errors", "sync_logs"}


def _digest(value: str) -> str:
    return hashlib.sha256(f"{MASK_SALT}:{value}".encode()).hexdigest()


def mask_identifier(value):
    """Mask a phone/bsuid/contact_key style identifier.

    Pure function of the exact input string, so the same real phone number
    or bsuid always masks to the same fake value no matter which collection
    or field it shows up in — that's what keeps cross-collection joins
    (member <-> conversation <-> wa_identity) intact after masking.
    """
    if value in (None, ""):
        return value
    s = str(value)
    plus = s.startswith("+")
    core = s[1:] if plus else s
    digest = _digest(s)
    if not core.isdigit():
        return digest[: max(8, len(s))]
    hexdigits = (digest * ((len(core) // len(digest)) + 2))[: len(core)]
    out = "".join(str(int(c, 16) % 10) for c in hexdigits)
    if out[0] == "0":
        out = "9" + out[1:]
    return ("+" + out) if plus else out


def mask_email(value):
    if value in (None, ""):
        return value
    token = _digest(str(value).lower())[:12]
    return f"user.{token}@preprod.example"


def mask_name(seed):
    if seed in (None, ""):
        return seed
    token = _digest(str(seed))[:6].upper()
    return f"Test Contact {token}"


def mask_meta_id(prefix: str, value):
    if value in (None, ""):
        return value
    token = _digest(str(value))[:10]
    return f"preprod-{prefix}-{token}"


DEV_PASSWORD_HASH = None  # set in main() once --dev-password is known


def mask_users_doc(doc):
    # Staff/admin accounts, not customer PII — email/name/phone are kept so
    # the team can still recognize and log into their own accounts. Only the
    # password is replaced, with a single known preprod credential.
    doc["hashed_password"] = DEV_PASSWORD_HASH
    return doc


def mask_restaurant_doc(doc):
    for wp in doc.get("wa_phones") or []:
        if wp.get("phone_id"):
            wp["phone_id"] = mask_meta_id("phone", wp["phone_id"])
        if wp.get("waba_id"):
            wp["waba_id"] = mask_meta_id("waba", wp["waba_id"])
    if doc.get("wa_phone_ids"):
        doc["wa_phone_ids"] = [mask_meta_id("phone", pid) for pid in doc["wa_phone_ids"]]
    return doc


def mask_member_doc(doc):
    phone = doc.get("phone")
    doc["name"] = mask_name(phone or doc.get("name"))
    doc["phone"] = mask_identifier(phone)
    if doc.get("normalized_phone"):
        doc["normalized_phone"] = mask_identifier(doc["normalized_phone"])
    if doc.get("email"):
        doc["email"] = mask_email(doc["email"])
    return doc


def mask_reservego_doc(doc):
    phone = doc.get("phone")
    if "guest_name" in doc:
        doc["guest_name"] = mask_name(phone or doc.get("guest_name"))
    if "phone" in doc:
        doc["phone"] = mask_identifier(phone)
    if doc.get("normalized_phone"):
        doc["normalized_phone"] = mask_identifier(doc["normalized_phone"])
    if doc.get("email"):
        doc["email"] = mask_email(doc["email"])
    return doc


def mask_inbound_message_doc(doc):
    phone = doc.get("from_phone")
    name_seed = phone or doc.get("bsuid") or doc.get("sender_name")
    if "from_phone" in doc:
        doc["from_phone"] = mask_identifier(phone)
    if doc.get("bsuid"):
        doc["bsuid"] = mask_identifier(doc["bsuid"])
    if doc.get("contact_key"):
        doc["contact_key"] = mask_identifier(doc["contact_key"])
    if doc.get("sender_name"):
        doc["sender_name"] = mask_name(name_seed)
    return doc


def mask_outbound_message_doc(doc):
    if "to_phone" in doc:
        doc["to_phone"] = mask_identifier(doc.get("to_phone"))
    if doc.get("contact_key"):
        doc["contact_key"] = mask_identifier(doc["contact_key"])
    return doc


def mask_message_log_doc(doc):
    phone = doc.get("recipient_phone")
    if "recipient_phone" in doc:
        doc["recipient_phone"] = mask_identifier(phone)
    if doc.get("recipient_name"):
        doc["recipient_name"] = mask_name(phone or doc.get("recipient_name"))
    return doc


def mask_wa_identity_doc(doc):
    if doc.get("phone"):
        doc["phone"] = mask_identifier(doc["phone"])
    if doc.get("bsuid"):
        doc["bsuid"] = mask_identifier(doc["bsuid"])
    if doc.get("username"):
        doc["username"] = f"preprod_{_digest(doc['username'])[:8]}"
    return doc


def mask_suppression_doc(doc):
    if doc.get("phone"):
        doc["phone"] = mask_identifier(doc["phone"])
    return doc


def mask_email_log_doc(doc):
    email = doc.get("recipient_email")
    if doc.get("recipient_name"):
        doc["recipient_name"] = mask_name(email or doc.get("recipient_name"))
    if email:
        doc["recipient_email"] = mask_email(email)
    return doc


def mask_email_suppression_doc(doc):
    if doc.get("email"):
        doc["email"] = mask_email(doc["email"])
    return doc


def make_member_message_stats_masker(phone_key_map: dict):
    def _mask(doc):
        old_key = doc.get("phone_key")
        if old_key:
            doc["phone_key"] = phone_key_map.get(old_key) or mask_identifier(old_key)
        return doc

    return _mask


def build_collection_plan(phone_key_map: dict):
    """Ordered (name, masker) pairs. Order matters: members must be cloned
    before member_message_stats so phone_key_map is populated in time."""
    return [
        ("users", mask_users_doc),
        ("restaurants", mask_restaurant_doc),
        ("members", mask_member_doc),
        ("member_message_stats", make_member_message_stats_masker(phone_key_map)),
        ("reservego_uploads", mask_reservego_doc),
        ("reservego_bill_data", mask_reservego_doc),
        ("inbound_messages", mask_inbound_message_doc),
        ("outbound_messages", mask_outbound_message_doc),
        ("message_logs", mask_message_log_doc),
        ("wa_identities", mask_wa_identity_doc),
        ("suppression_list", mask_suppression_doc),
        ("email_logs", mask_email_log_doc),
        ("email_suppression_list", mask_email_suppression_doc),
        # Not customer PII — business/operational metadata, copied as-is.
        ("campaign_jobs", None),
        ("email_campaign_jobs", None),
        ("email_alert_logs", None),
        ("email_templates", None),
        ("templates", None),
        ("resend_webhook_events", None),
        ("meta_billing_events", None),
        ("sync_metadata", None),
        ("user_restaurant_roles", None),
        ("contact_files", None),
        ("audit_logs", None),
    ]


def redact_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.password:
        return uri.replace(parsed.password, "***")
    return uri


async def clone_collection(source_db, dest_db, name, masker, batch_size, phone_key_map=None, max_retries=3):
    """Clone one collection, retrying from scratch on transient read errors.

    Atlas cursors can be dropped mid-scan on long-running collections (e.g. a
    network hiccup between getMores) — that raises CursorNotFound partway
    through, not on the first batch. On retry we clear whatever this attempt
    already wrote to the destination collection, then re-read the source from
    the top, so a retry never leaves duplicate docs behind.
    """
    for attempt in range(1, max_retries + 1):
        try:
            return await _clone_collection_once(source_db, dest_db, name, masker, batch_size, phone_key_map)
        except PyMongoError as e:
            if attempt == max_retries:
                raise
            print(f"    ! {name}: {e.__class__.__name__} on attempt {attempt}/{max_retries} — clearing and retrying...")
            await dest_db[name].delete_many({})
            await asyncio.sleep(3 * attempt)


async def _clone_collection_once(source_db, dest_db, name, masker, batch_size, phone_key_map=None):
    buffer = []
    total = 0
    cursor = source_db[name].find({}, batch_size=batch_size)
    async for doc in cursor:
        if name == "members" and phone_key_map is not None:
            original_phone = doc.get("phone")
            original_key = normalize_phone_for_match(original_phone)
        if masker:
            doc = masker(doc)
        if name == "members" and phone_key_map is not None and original_key:
            phone_key_map[original_key] = normalize_phone_for_match(doc.get("phone"))
        buffer.append(doc)
        if len(buffer) >= batch_size:
            await _insert(dest_db[name], buffer)
            total += len(buffer)
            buffer = []
    if buffer:
        await _insert(dest_db[name], buffer)
        total += len(buffer)
    return total


async def _insert(collection, docs):
    if not docs:
        return
    try:
        await collection.insert_many(docs, ordered=False)
    except BulkWriteError as e:
        print(f"    ! bulk write errors in {collection.name}: {e.details.get('writeErrors', [])[:2]}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--dest-uri", default=None)
    parser.add_argument("--dest-db", default=None)
    parser.add_argument("--source-uri", default=None)
    parser.add_argument("--source-db", default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--only", default=None, help="comma-separated collection names")
    parser.add_argument("--dev-password", default="Preprod123!")
    parser.add_argument("--yes", action="store_true", help="skip interactive confirmation")
    return parser.parse_args()


def resolve_db_name_from_uri(uri: str) -> str:
    return urlparse(uri).path.lstrip("/").strip()


async def main():
    global DEV_PASSWORD_HASH
    args = parse_args()

    env_values = dotenv_values(args.env_file) if Path(args.env_file).exists() else {}

    dest_uri = args.dest_uri or env_values.get("PREPROD_MONGO_URI")
    dest_db_name = args.dest_db or env_values.get("PREPROD_DB_NAME") or "dishpatch-uat"

    if not dest_uri:
        print(
            f"No destination URI given. Set PREPROD_MONGO_URI in {args.env_file} "
            "or pass --dest-uri."
        )
        sys.exit(1)

    source_uri = args.source_uri or settings.mongodb_url
    source_db_name = args.source_db or settings.mongodb_db_name or resolve_db_name_from_uri(source_uri)

    source_host = urlparse(source_uri).hostname
    dest_host = urlparse(dest_uri).hostname
    if source_host == dest_host and source_db_name == dest_db_name:
        print("Refusing to run: destination resolves to the exact same host+database as the source.")
        sys.exit(1)

    DEV_PASSWORD_HASH = hash_password(args.dev_password)

    print("Source (read-only):")
    print(f"  {redact_uri(source_uri)}  db={source_db_name}")
    print("Destination (will be DROPPED and recreated):")
    print(f"  {redact_uri(dest_uri)}  db={dest_db_name}")
    print(f"Preprod login password for all cloned `users` accounts: {args.dev_password}")
    print()

    if not args.yes:
        typed = input(f"Type the destination database name ({dest_db_name}) to proceed: ")
        if typed.strip() != dest_db_name:
            print("Confirmation did not match. Aborting.")
            sys.exit(1)

    source_client = AsyncIOMotorClient(source_uri)
    dest_client = AsyncIOMotorClient(dest_uri)
    source_db = source_client[source_db_name]
    dest_db = dest_client[dest_db_name]

    only = {c.strip() for c in args.only.split(",")} if args.only else None

    if only:
        # Resuming/retrying a subset — clear just those collections, leaving
        # everything else already cloned to the destination untouched.
        for name in only:
            await dest_db[name].drop()
        print(f"Cleared destination collections: {', '.join(sorted(only))}")
    else:
        print(f"\nDropping destination database '{dest_db_name}'...")
        await dest_client.drop_database(dest_db_name)

    phone_key_map: dict = {}
    plan = build_collection_plan(phone_key_map)
    planned_names = {name for name, _ in plan}

    failed = []
    print("\nCloning collections:")
    for name, masker in plan:
        if only and name not in only:
            continue
        try:
            count = await clone_collection(
                source_db, dest_db, name, masker, args.batch_size, phone_key_map
            )
        except PyMongoError as e:
            print(f"  {name:<28} {'FAILED':>8}  ({e.__class__.__name__}: {e})")
            failed.append(name)
            continue
        tag = "masked" if masker else "as-is"
        print(f"  {name:<28} {count:>8} docs  ({tag})")

    if not only:
        source_collection_names = set(await source_db.list_collection_names())
        extra = source_collection_names - planned_names - EXCLUDED_COLLECTIONS
        for name in sorted(extra):
            try:
                count = await clone_collection(source_db, dest_db, name, None, args.batch_size)
            except PyMongoError as e:
                print(f"  {name:<28} {'FAILED':>8}  ({e.__class__.__name__}: {e})")
                failed.append(name)
                continue
            print(f"  {name:<28} {count:>8} docs  (UNRECOGNIZED collection — copied as-is, please review)")

        skipped = source_collection_names & EXCLUDED_COLLECTIONS
        for name in sorted(skipped):
            print(f"  {name:<28} {'skipped':>8}  (raw payload / dead-letter log — not cloned)")

    source_client.close()
    dest_client.close()

    if failed:
        print(f"\n{len(failed)} collection(s) failed after retries: {', '.join(failed)}")
        print(f"Resume with: python scripts/clone_to_preprod.py --yes --only {','.join(failed)}")
    else:
        print("\nDone.")
    print(f"Point the app at {dest_db_name} to use it (MONGODB_URL / MONGODB_DB_NAME), then run")
    print("scripts/ensure_indexes.py (or let app startup's init_indexes() build them) against it.")


if __name__ == "__main__":
    asyncio.run(main())
