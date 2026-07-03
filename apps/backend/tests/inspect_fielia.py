import asyncio
import os
import sys
import json
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient

# Rely on environment variable for security
URI = os.getenv("FIELIA_MONGO_URI")
DB_NAME = "test"
COLLECTION_NAME = "cards"


async def analyze_record_volume(collection):
    """Analyze and print record volume."""
    total_count = await collection.count_documents({})
    print("\n--- RECORD VOLUME ---")
    print(f"Total Documents in test.cards: {total_count}")
    return total_count


async def sample_documents(collection, limit=5):
    """Sample and print documents."""
    print(f"\n--- SAMPLE DOCUMENTS (First {limit}) ---")
    cursor = collection.find().limit(limit)
    samples = await cursor.to_list(length=limit)

    for i, doc in enumerate(samples):
        clean_doc = {
            k: (v.isoformat() if isinstance(v, datetime) else str(v))
            for k, v in doc.items()
        }
        print(f"\nDocument {i+1}:")
        print(json.dumps(clean_doc, indent=2))
    return samples


async def field_analysis(collection, limit=1000):
    """Perform field presence and type analysis."""
    print("\n--- FIELD ANALYSIS ---")
    cursor = collection.find().limit(limit)
    docs = await cursor.to_list(length=limit)

    field_counts = {}
    total_sampled = len(docs)
    tenant_fields = set()

    for doc in docs:
        _analyze_doc_fields(doc, field_counts, tenant_fields)

    _print_field_stats(field_counts, total_sampled)
    return tenant_fields


def _analyze_doc_fields(doc: dict, field_counts: dict, tenant_fields: set):
    """Helper to update field stats for a single document."""
    for key, value in doc.items():
        if key not in field_counts:
            field_counts[key] = {"present": 0, "null": 0, "types": set()}
        
        stats = field_counts[key]
        stats["present"] += 1
        
        if value is None or value == "":
            stats["null"] += 1
        else:
            stats["types"].add(type(value).__name__)
        
        if any(hint in key.lower() for hint in ["restaurant", "tenant", "store", "branch"]):
            tenant_fields.add(key)


def _print_field_stats(field_counts: dict, total_sampled: int):
    """Helper to print the field statistics table."""
    print(f"Sampled {total_sampled} documents for analysis.\n")
    print(f"{'Field':<25} | {'Present %':<10} | {'Null/Empty %':<12} | {'Data Types'}")
    print("-" * 75)
    for key, stats in sorted(field_counts.items()):
        present_pct = (stats["present"] / total_sampled) * 100
        null_pct = (stats["null"] / stats["present"]) * 100
        types_str = ", ".join(stats["types"])
        print(f"{key:<25} | {present_pct:>8.1f}% | {null_pct:>10.1f}% | {types_str}")


async def multi_tenancy_check(collection, tenant_fields):
    """Check for distinct values in potential tenant fields."""
    print("\n--- MULTI-TENANCY CHECK ---")
    if not tenant_fields:
        print("No obvious restaurant_id or tenant fields found.")
        return

    print(f"Found potential tenant fields: {tenant_fields}")
    for field in tenant_fields:
        distinct_vals = await collection.distinct(field)
        print(f"Distinct values for '{field}': {distinct_vals[:10]} (showing up to 10)")


async def inspect():
    """Main inspection workflow."""
    if not URI:
        print("Error: FIELIA_MONGO_URI environment variable is not set.")
        sys.exit(1)

    print(f"Connecting to MongoDB...")
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    total_count = await analyze_record_volume(collection)
    if total_count > 0:
        await sample_documents(collection)
        tenant_fields = await field_analysis(collection)
        await multi_tenancy_check(collection, tenant_fields)

    client.close()


if __name__ == "__main__":
    asyncio.run(inspect())
