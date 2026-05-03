import asyncio
import sys
import os
from datetime import datetime
from pydantic import ValidationError
from pprint import pprint

# Add apps/backend to path
sys.path.append(os.path.abspath("apps/backend"))

async def validate_fielia_data():
    try:
        from app.services.fielia_members_service import fielia_service
        from app.models.member import MemberResponse
        
        print("Fetching Fielia members for validation...")
        res = await fielia_service.list_members(limit=5)
        items = res.get("items", [])
        
        print(f"Retrieved {len(items)} items. Starting validation against MemberResponse schema...\n")
        
        all_valid = True
        for i, item in enumerate(items):
            print(f"Checking Item #{i} (ID: {item.get('id')})")
            try:
                # Pydantic validation
                validated = MemberResponse(**item)
                print("  STATUS: VALID")
            except ValidationError as e:
                print("  STATUS: INVALID")
                all_valid = False
                pprint(e.errors())
                print("  Data that failed:")
                pprint(item)
            print("-" * 40)
            
        if all_valid:
            print("\nSUCCESS: All Fielia data samples passed schema validation!")
        else:
            print("\nFAILURE: Some items failed validation. Check the errors above.")

    except Exception as e:
        print(f"Script failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(validate_fielia_data())
