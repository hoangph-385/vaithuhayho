"""
Vaithuhayho Web Application
Backend Server - Flask Application
"""

import os
import sys
import logging
import hashlib
import socket
from flask import Flask, request, jsonify, render_template, url_for
from waitress import serve

# Import các module con
from utils.firebase_config import ensure_firebase
from routes.wms import bp as wms_bp
from routes.report import bp as report_bp
from routes.sdd import bp as sdd_bp

# ───── Setup Flask ─────
app = Flask(__name__, static_folder="static")

# Tắt Werkzeug logging để tránh trùng lặp
import logging
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.WARNING)  # Chỉ show WARNING trở lên

# Register Blueprints
app.register_blueprint(wms_bp, url_prefix='/wms')
app.register_blueprint(report_bp, url_prefix='/api/report')
app.register_blueprint(sdd_bp, url_prefix='/api/report')

# ───── Constants ─────
PUBLIC_PATHS = {"/", "/scan", "/handover", "/sdd"}

# ───── Setup Flask & Logging ─────
import logging, logging.config
from logging.handlers import RotatingFileHandler

# Get computer name for logging
COMPUTER_NAME = socket.gethostname()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = os.getenv("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "compact": {"format": "[%(asctime)s] [%(levelname)s] %(message)s", "datefmt": "%H:%M:%S"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "formatter": "compact",
            "stream": "ext://sys.stdout",
        },
        "rotating_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": LOG_LEVEL,
            "formatter": "compact",
            "filename": os.path.join(LOG_DIR, "app.log"),
            "maxBytes": 5 * 1024 * 1024,  # 5MB
            "backupCount": 3,
            "encoding": "utf-8",
        },
    },
    "root": {
        "level": LOG_LEVEL,
        "handlers": ["console", "rotating_file"],
    },
})

# Bật log cho Flask & Waitress
app.logger.propagate = True                      # đẩy log của app lên root
logging.getLogger("waitress").setLevel(LOG_LEVEL)

# (Tuỳ chọn) log mỗi request đơn giản
@app.after_request
def _log_response(response):
    # Log với status code và client info (IP, User-Agent)
    method = request.method
    path = request.path
    status = response.status_code
    client_ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Unknown')

    # Extract browser/device info from User-Agent
    if 'Chrome' in user_agent:
        browser = 'Chrome'
    elif 'Firefox' in user_agent:
        browser = 'Firefox'
    elif 'Safari' in user_agent:
        browser = 'Safari'
    elif 'Edge' in user_agent:
        browser = 'Edge'
    else:
        browser = 'Other'

    # Log với client IP và browser info
    app.logger.info("[CLIENT: %s | %s] %s %s - %d", client_ip, browser, method, path, status)
    sys.stdout.flush()
    return response

# Signal handler for server restart
import atexit
@atexit.register
def _on_exit():
    app.logger.warning("[SERVER] Process exiting (auto-reload may have triggered restart)")

# ───── Routes ─────
@app.route("/")
def home():
    """Home page"""
    return render_template("home.html")

@app.route("/scan")
def scan():
    """Scan Tool page"""
    return render_template("tool_scan.html")

@app.route("/handover")
def handover():
    """Handover Tool page"""
    return render_template("tool_handover.html")

@app.route("/sdd")
def sdd():
    """SDD Tool page"""
    return render_template("tool_sdd.html")

# ───── Server ─────
def run_flask():
    """Run Flask app with Waitress server (production) or Flask dev server (development)"""
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "9090"))
    threads = int(os.getenv("FLASK_THREADS", "8"))

    # Check if running in development mode
    dev_mode = os.getenv("FLASK_ENV", "development") == "development" or "--dev" in sys.argv

    if dev_mode:
        # Enable watchdog debug logging (if watchdog is used)
        os.environ["WATCHDOG_LOG_LEVEL"] = "DEBUG"
        logging.getLogger("watchdog").setLevel(logging.DEBUG)

        # Use Flask's built-in development server with auto-reload
        print(f"[DEV MODE] [{COMPUTER_NAME}] Flask dev server on http://{host}:{port}")
        print("[DEV MODE] Auto-reload ENABLED - server will restart on file changes")
        print("[DEV MODE] Monitoring Python, template, CSS, JS files")
        print("[DEV MODE] Excludes: __pycache__, .git, logs, node_modules, .venv")
        print("[DEV MODE] Tip: Try editing any .py, .html, .css, .js file to trigger restart")

        # Configure Flask logging to show reloader info
        app.logger.info("[SERVER: %s] Starting Flask dev server with auto-reload", COMPUTER_NAME)

        # Use stat reloader (more stable on Windows than watchdog)
        app.run(
            host=host,
            port=port,
            debug=True,
            use_reloader=True,
            reloader_type='stat'  # stat is more stable on Windows
        )
    else:
        # Production: use Waitress
        print(f"[PRODUCTION] [{COMPUTER_NAME}] Serving on http://{host}:{port} (waitress, threads={threads})")
        serve(app, host=host, port=port, threads=threads)

# ───── Entry Point ─────
if __name__ == "__main__":
    # Initialize Firebase on startup
    ensure_firebase()
    app.logger.info("[SERVER: %s] Starting application...", COMPUTER_NAME)

    # Check if running as child process (for watchdog)
    if "--child" in sys.argv:
        try:
            run_flask()
        except KeyboardInterrupt:
            pass
        sys.exit(0)

    # Otherwise, run directly
    run_flask()
