import sys
import os

# Add apps/backend to path
sys.path.append(os.path.abspath("apps/backend"))

try:
    print("Attempting to import settings...")
    from app.config import settings
    print(f"Settings imported. FIELIA_MONGO_URI present: {bool(settings.fielia_mongo_uri)}")
    
    print("\nAttempting to import app.main...")
    from app.main import app
    print("app.main imported successfully!")
    
    print("\nAttempting to import Fielia service...")
    from app.services.fielia_members_service import fielia_service
    print("Fielia service imported successfully!")
    
    print("\nBackend boot test PASSED")
except Exception as e:
    print(f"\nBackend boot test FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
