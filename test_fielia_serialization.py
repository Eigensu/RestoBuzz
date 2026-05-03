import asyncio
import json
import sys
import os
from datetime import datetime

# Add apps/backend to path
sys.path.append(os.path.abspath("apps/backend"))

async def test_serialization():
    try:
        print("Importing Fielia service...")
        from app.services.fielia_members_service import fielia_service
        
        print("Fetching members...")
        res = await fielia_service.list_members(limit=3)
        
        print("Attempting to JSON serialize result...")
        # This will fail if there are non-serializable objects like datetime or ObjectId
        json_data = json.dumps(res, default=str) # Using default=str is a common fix, let's see if it's needed
        print("Serialization successful with default=str!")
        
        print("\nAttempting to JSON serialize WITHOUT default=str (what FastAPI might do by default)...")
        try:
            json_data = json.dumps(res)
            print("Serialization successful WITHOUT default=str!")
        except TypeError as e:
            print(f"Serialization FAILED without default=str: {e}")
            
        print("\nChecking summary serialization...")
        summary = await fielia_service.get_summary(datetime(2024,1,1), datetime.now())
        try:
            json.dumps(summary)
            print("Summary serialization successful!")
        except TypeError as e:
            print(f"Summary serialization FAILED: {e}")

    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_serialization())
