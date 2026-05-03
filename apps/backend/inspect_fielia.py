import asyncio
import os
import sys

# We don't strictly need config.py if we just hardcode the test URI for diagnostic purposes,
# but we can use motor.
from motor.motor_asyncio import AsyncIOMotorClient
import json
from datetime import datetime

URI = "mongodb+srv://workeigensu_db_user:WlHeR6RNCgubUikl@fielia.8qgkoam.mongodb.net/?appName=Fielia"
DB_NAME = "test"
COLLECTION_NAME = "cards"

async def inspect():
    print(f"Connecting to {URI}...")
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # 1. Record Volume
    total_count = await collection.count_documents({})
    print(f"\n--- RECORD VOLUME ---")
    print(f"Total Documents in test.cards: {total_count}")

    if total_count == 0:
        print("Collection is empty!")
        return

    # 2. Sample Documents
    print(f"\n--- SAMPLE DOCUMENTS (First 5) ---")
    cursor = collection.find().limit(5)
    samples = await cursor.to_list(length=5)
    
    for i, doc in enumerate(samples):
        # Clean up types for printing
        clean_doc = {}
        for k, v in doc.items():
            if isinstance(v, datetime):
                clean_doc[k] = v.isoformat()
            else:
                clean_doc[k] = str(v)
        print(f"\nDocument {i+1}:")
        print(json.dumps(clean_doc, indent=2))

    # 3. Field Analysis
    print(f"\n--- FIELD ANALYSIS ---")
    # Sample up to 1000 docs for field frequency
    cursor = collection.find().limit(1000)
    docs = await cursor.to_list(length=1000)
    
    field_counts = {}
    total_sampled = len(docs)
    
    tenant_fields = set()
    
    for doc in docs:
        for key, value in doc.items():
            if key not in field_counts:
                field_counts[key] = {"present": 0, "null": 0, "types": set()}
            
            field_counts[key]["present"] += 1
            if value is None or value == "":
                field_counts[key]["null"] += 1
            else:
                field_counts[key]["types"].add(type(value).__name__)
                
            # Check for multi-tenancy hints
            if "restaurant" in key.lower() or "tenant" in key.lower() or "store" in key.lower() or "branch" in key.lower():
                tenant_fields.add(key)

    print(f"Sampled {total_sampled} documents for analysis.\n")
    print(f"{'Field':<25} | {'Present %':<10} | {'Null/Empty %':<12} | {'Data Types'}")
    print("-" * 75)
    for key, stats in sorted(field_counts.items()):
        present_pct = (stats["present"] / total_sampled) * 100
        null_pct = (stats["null"] / stats["present"]) * 100
        types_str = ", ".join(stats["types"])
        print(f"{key:<25} | {present_pct:>8.1f}% | {null_pct:>10.1f}% | {types_str}")

    # Multi-tenancy check
    print(f"\n--- MULTI-TENANCY CHECK ---")
    if tenant_fields:
        print(f"Found potential tenant fields: {tenant_fields}")
        for field in tenant_fields:
            distinct_vals = await collection.distinct(field)
            print(f"Distinct values for '{field}': {distinct_vals[:10]} (showing up to 10)")
    else:
        print("No obvious restaurant_id or tenant fields found. Data might be single-tenant or implicit.")

    client.close()

if __name__ == "__main__":
    asyncio.run(inspect())
