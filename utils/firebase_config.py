"""
Firebase Configuration and Initialization
"""

import os
import firebase_admin
from firebase_admin import credentials, db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_ACCOUNT = os.path.join(BASE_DIR, "handover-4.json")
DATABASE_URL = "https://handover-4-default-rtdb.asia-southeast1.firebasedatabase.app"

def ensure_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    try:
        firebase_admin.get_app()
    except ValueError:
        if not os.path.isfile(SERVICE_ACCOUNT):
            raise FileNotFoundError(f"Không thấy service account: {SERVICE_ACCOUNT}")

        cred = credentials.Certificate(SERVICE_ACCOUNT)
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
        print(f"[Firebase] Initialized with {SERVICE_ACCOUNT}")

def get_db():
    """Get Firebase database reference"""
    ensure_firebase()
    return db
