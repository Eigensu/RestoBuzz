import sys
import os
from pydantic import ValidationError

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "apps", "backend"))

from app.models.member import MemberCreate

def test_payload(payload):
    print(f"Testing payload: {payload}")
    try:
        m = MemberCreate(**payload)
        print("VALID")
        print(f"  Result: {m.model_dump()}")
    except ValidationError as e:
        print("INVALID")
        for err in e.errors():
            print(f"  - {err['loc']}: {err['msg']} ({err['type']})")
    print("-" * 20)

# Case 1: All required fields present
test_payload({
    "restaurant_id": "r1",
    "type": "vip",
    "name": "John Doe",
    "phone": "1234567"
})

# Case 2: Missing phone (should be VALID now because of default)
test_payload({
    "restaurant_id": "r1",
    "type": "vip",
    "name": "John Doe"
})

# Case 3: Missing name (should be INVALID - missing)
test_payload({
    "restaurant_id": "r1",
    "type": "vip",
    "phone": "1234567"
})

# Case 4: Missing restaurant_id (should be INVALID - missing)
test_payload({
    "restaurant_id": None, # Pydantic V2 'missing' if absent, but 'type_error.none.not_allowed' if None
    "type": "vip",
    "name": "John Doe"
})

# Case 5: Empty object (should be INVALID - multiple missing)
test_payload({})
