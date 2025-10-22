"""
Vaithuhayho Web Application
Backend Server - Flask Application
"""

import os
import sys
import logging
import hashlib
from flask import Flask, request, jsonify, render_template, url_for
from waitress import serve

# Import các module con
from utils.firebase_config import ensure_firebase
from routes.wms import bp as wms_bp
from routes.report import bp as report_bp

# ───── Setup Flask ─────
app = Flask(__name__, static_folder="static")
app.logger.setLevel(logging.DEBUG)

_handler = logging.StreamHandler()
_handler.setLevel(logging.DEBUG)
_handler.setFormatter(logging.Formatter("\n[%(levelname)s]: %(asctime)s\n%(message)s"))
app.logger.addHandler(_handler)

# Register Blueprints
app.register_blueprint(wms_bp, url_prefix='/wms')
app.register_blueprint(report_bp, url_prefix='/api/report')

# ───── Constants ─────
PUBLIC_PATHS = {"/", "/scan", "/handover"}

# (Removed) Background Task handler and threads

# ───── Routes ─────
@app.route("/")
def home():
    """Home page"""
    return render_template("home.html")

@app.route("/scan")
def scan():
    """Scan Tool page"""
    return render_template("scan.html")

@app.route("/handover")
def handover():
    """Handover Tool page"""
    return render_template("handover.html")

# ───── Server ─────
def run_flask():
    """Run Flask app with Waitress server (production) or Flask dev server (development)"""
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "9090"))
    threads = int(os.getenv("FLASK_THREADS", "8"))

    # Check if running in development mode
    dev_mode = os.getenv("FLASK_ENV", "development") == "development" or "--dev" in sys.argv

    if dev_mode:
        # Use Flask's built-in development server with auto-reload
        print(f"[DEV MODE] Flask dev server on http://{host}:{port}")
        print("[DEV MODE] Auto-reload ENABLED - server will restart on file changes")
        app.run(
            host=host,
            port=port,
            debug=True,
            use_reloader=True,
            reloader_type='stat'  # Use stat reloader instead of watchdog
        )
    else:
        # Production: use Waitress
        print(f"[PRODUCTION] Serving on http://{host}:{port} (waitress, threads={threads})")
        serve(app, host=host, port=port, threads=threads)

# ───── Entry Point ─────
if __name__ == "__main__":
    # Initialize Firebase on startup
    ensure_firebase()

    # Check if running as child process (for watchdog)
    if "--child" in sys.argv:
        try:
            run_flask()
        except KeyboardInterrupt:
            pass
        sys.exit(0)

    # Otherwise, run directly
    run_flask()
