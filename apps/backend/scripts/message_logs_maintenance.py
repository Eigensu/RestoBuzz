"""One-off storage maintenance for message_logs: TTL index + compaction.

Two independent actions (run either or both):

  --apply-ttl   Create/adjust the created_at TTL index so message_logs older
                than --ttl-days are auto-deleted by MongoDB's background TTL
                monitor (runs ~every 60s). This is the same index database.py
                creates on deploy — this script just lets you apply it NOW,
                without waiting for a redeploy. Idempotent.

  --compact     Run `compact` on message_logs. Deletes/$unsets free space
                *logically*, but WiredTiger keeps the freed blocks until a
                compaction rewrites the data files and returns them to the OS
                (and thus drops the Atlas storage-quota number). Compact takes
                a brief lock on the collection — prefer low-traffic windows.

Dry run (default) prints what it WOULD do and the current index state.

Usage:
    python scripts/message_logs_maintenance.py                       # dry run: show state
    python scripts/message_logs_maintenance.py --apply-ttl           # create/adjust TTL (90d)
    python scripts/message_logs_maintenance.py --apply-ttl --ttl-days 60
    python scripts/message_logs_maintenance.py --compact             # reclaim disk
    python scripts/message_logs_maintenance.py --apply-ttl --compact # both
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymongo import ASCENDING
from pymongo.errors import OperationFailure

from app.config import settings

DEFAULT_TTL_DAYS = 90
TTL_INDEX_NAME = "created_at_1"  # PyMongo's auto-name for [("created_at", ASCENDING)]


def _resolve_db_name(mongo_url: str, default: str = "restobuzz") -> str:
    """Same resolution the app uses: MONGODB_DB_NAME, else the URL path."""
    name = (settings.mongodb_db_name or "").strip()
    if name:
        return name
    try:
        path = urlparse(mongo_url).path.strip("/").split("?")[0].split("/")[0]
        return path or default
    except Exception:
        return default


async def _show_ttl_state(coll) -> dict | None:
    """Print the current created_at index (if any) and return its info."""
    info = await coll.index_information()
    existing = info.get(TTL_INDEX_NAME)
    if not existing:
        print(f"  TTL index '{TTL_INDEX_NAME}': not present")
        return None
    ttl = existing.get("expireAfterSeconds")
    if ttl is None:
        print(f"  '{TTL_INDEX_NAME}' exists but is NOT a TTL index (no expiry)")
    else:
        print(f"  '{TTL_INDEX_NAME}' TTL = {ttl}s ({ttl / 86400:.0f} days)")
    return existing


async def _apply_ttl(db, coll, ttl_seconds: int, existing: dict | None) -> None:
    """Create the TTL index, or adjust expiry in place via collMod if it exists."""
    if existing is None:
        await coll.create_index(
            [("created_at", ASCENDING)], expireAfterSeconds=ttl_seconds
        )
        print(f"  created TTL index '{TTL_INDEX_NAME}' @ {ttl_seconds}s")
        return
    if existing.get("expireAfterSeconds") == ttl_seconds:
        print(f"  TTL already {ttl_seconds}s — nothing to change")
        return
    # Index exists with a different (or no) expiry — change it without a rebuild.
    try:
        await db.command(
            {
                "collMod": coll.name,
                "index": {"keyPattern": {"created_at": 1}, "expireAfterSeconds": ttl_seconds},
            }
        )
        print(f"  adjusted TTL of '{TTL_INDEX_NAME}' -> {ttl_seconds}s (collMod)")
    except OperationFailure as e:
        print(f"  collMod failed ({e}); dropping and recreating index...")
        await coll.drop_index(TTL_INDEX_NAME)
        await coll.create_index(
            [("created_at", ASCENDING)], expireAfterSeconds=ttl_seconds
        )
        print(f"  recreated TTL index '{TTL_INDEX_NAME}' @ {ttl_seconds}s")


def _human(num_bytes: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TiB"


async def _db_stats(db) -> None:
    """Print whole-DB logical vs on-disk size — tells us which the quota counts."""
    try:
        s = await db.command("dbStats")
    except Exception as e:
        print(f"  (dbStats unavailable: {e})")
        return
    print(f"database '{db.name}' totals:")
    print(f"  logical data size : {_human(s.get('dataSize', 0))}   (uncompressed)")
    print(f"  on-disk storage   : {_human(s.get('storageSize', 0))}   (compressed)")
    print(f"  indexes           : {_human(s.get('indexSize', 0))}")
    print(f"  disk + indexes    : {_human(s.get('storageSize', 0) + s.get('indexSize', 0))}")
    print("  --> the total closest to 512 MiB is the one Atlas is enforcing.")
    print()


async def _list_indexes(db, coll) -> None:
    """Print each index with its on-disk size (from collStats.indexSizes)."""
    try:
        stats = await db.command("collStats", coll.name)
        sizes = stats.get("indexSizes", {})
    except Exception as e:
        sizes = {}
        print(f"  (index sizes unavailable: {e})")
    info = await coll.index_information()
    print("message_logs indexes:")
    for name, spec in info.items():
        keys = ", ".join(f"{k}:{v}" for k, v in spec["key"])
        size = _human(sizes.get(name, 0))
        print(f"  {size:>10}  {name}  ({keys})")
    print()


async def _drop_index(coll, name: str) -> None:
    """Drop one index by name — a catalog op that frees quota even when writes
    are blocked, so it can unwedge an over-quota cluster."""
    if name in ("_id_", "_id"):
        print("  refusing to drop the _id index.")
        return
    print(f"  dropping index '{name}'...")
    try:
        await coll.drop_index(name)
        print(f"  dropped '{name}' — space freed; retry your write now.")
    except OperationFailure as e:
        print(f"  drop failed: {e}")


async def _compact(db, coll) -> None:
    print(f"  running compact on '{coll.name}' (may briefly lock the collection)...")
    try:
        res = await db.command({"compact": coll.name, "force": True})
        print(f"  compact ok: {res}")
    except OperationFailure as e:
        print(f"  compact failed: {e}")
        print("  (On some Atlas tiers use the Atlas UI/support to compact instead.)")


async def main(
    apply_ttl: bool, compact: bool, ttl_days: int, drop_index: str | None
) -> None:
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = settings.mongodb_url
    db = AsyncIOMotorClient(mongo_url).get_database(_resolve_db_name(mongo_url))
    coll = db.message_logs
    ttl_seconds = ttl_days * 86400
    dry = not (apply_ttl or compact or drop_index)

    host = urlparse(mongo_url).hostname or "?"
    if host in ("localhost", "127.0.0.1"):
        print("⚠️  Connected to LOCALHOST — set MONGODB_URL_PROD or use "
              "`railway run` to hit production.\n")
    print(f"[{'DRY RUN' if dry else 'APPLY'}] db={db.name}  host={host}  "
          f"ttl_days={ttl_days}\n")

    await _db_stats(db)
    await _list_indexes(db, coll)

    print("Current TTL state:")
    existing = await _show_ttl_state(coll)
    print()

    if dry:
        print("DRY RUN — no changes. Re-run with:")
        print("  --drop-index <name>    free space now (unblocks an over-quota cluster)")
        print(f"  --apply-ttl            create/adjust the {ttl_days}-day TTL index")
        print("  --compact              reclaim freed disk space")
        return

    if drop_index:
        print(f"Dropping index '{drop_index}':")
        await _drop_index(coll, drop_index)
        print()

    if apply_ttl:
        print(f"Applying {ttl_days}-day TTL:")
        # A --drop-index above can invalidate the `existing` snapshot taken
        # before it (e.g. dropping the TTL index itself), so re-read the current
        # state — otherwise _apply_ttl would collMod a now-missing index instead
        # of recreating it.
        current = (await coll.index_information()).get(TTL_INDEX_NAME)
        await _apply_ttl(db, coll, ttl_seconds, current)
        print()

    if compact:
        print("Compacting:")
        await _compact(db, coll)
        print()


if __name__ == "__main__":
    args = sys.argv[1:]
    days = (
        int(args[args.index("--ttl-days") + 1])
        if "--ttl-days" in args
        else DEFAULT_TTL_DAYS
    )
    drop = args[args.index("--drop-index") + 1] if "--drop-index" in args else None
    asyncio.run(
        main(
            apply_ttl="--apply-ttl" in args,
            compact="--compact" in args,
            ttl_days=days,
            drop_index=drop,
        )
    )
