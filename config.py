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

