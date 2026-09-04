"""Backfill inbound_messages.contact_key for rows written before BSUID support.

contact_key is the conversation grouping key: the sender's phone number when we
have one, otherwise their business-scoped user ID. Rows created before that
field existed carry only from_phone, so the conversation pipeline falls back to
`$ifNull: [contact_key, from_phone]` — correct, but a computed field cannot be
served by an index.

Running this makes contact_key universally present, which is the precondition
for dropping that fallback and letting the
(restaurant_id, contact_key, received_at) index serve the sort directly.

Safe to run repeatedly and while the app is serving: it only touches documents
that have no contact_key, and never overwrites one that is already set.

    python scripts/backfill_contact_key.py --dry-run
    python scripts/backfill_contact_key.py
"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from app.database import get_fresh_db  # noqa: E402


async def backfill(dry_run: bool) -> None:
    db = get_fresh_db()
    try:
        missing = {"contact_key": {"$exists": False}, "from_phone": {"$ne": None}}
        total = await db.inbound_messages.count_documents(missing)
        print(f"inbound_messages without contact_key: {total}")

        if dry_run:
            print("dry run — no writes")
            return
        if total == 0:
            print("nothing to backfill")
            return

        result = await db.inbound_messages.update_many(
            missing, [{"$set": {"contact_key": "$from_phone"}}]
        )
        print(f"updated {result.modified_count}")

        # Rows with neither identifier cannot be grouped and are left alone
        # rather than given a null key that would merge them into one thread.
        orphans = await db.inbound_messages.count_documents(
            {"contact_key": {"$exists": False}}
        )
        if orphans:
            print(f"note: {orphans} row(s) have no from_phone and were skipped")
    finally:
        db.client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report, don't write")
    asyncio.run(backfill(parser.parse_args().dry_run))
