"""
Configuration File
"""

import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Channels
CHANNELS = ["SPX", "GHN"]

# Firebase
FIREBASE_SERVICE_ACCOUNT = os.path.join(BASE_DIR, "handover-4.json")
FIREBASE_DATABASE_URL = "https://handover-4-default-rtdb.asia-southeast1.firebasedatabase.app"

# Server
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "9090"))
FLASK_THREADS = int(os.getenv("FLASK_THREADS", "8"))

# Authentication
# Đổi password tại đây (plain text - hệ thống sẽ tự động hash)
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "PHH@2025")

# Tự động tính hash (không cần sửa phần này)
import hashlib
AUTH_PASSWORD_HASH = hashlib.sha256(AUTH_PASSWORD.encode()).hexdigest()

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "your-secret-key-change-this-in-production")

