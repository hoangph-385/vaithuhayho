"""
Firebase utilities wrapper
"""

from firebase_admin import db
from .firebase_config import ensure_firebase

# Ensure Firebase is initialized
ensure_firebase()

# Export db as rtdb for backward compatibility
rtdb = db
