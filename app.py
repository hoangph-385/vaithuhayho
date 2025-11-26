"""
Vaithuhayho Web Application
Backend Server - Flask Application
"""

import os
import sys
import logging
import hashlib
import socket
from flask import Flask, request, jsonify, render_template, url_for, session, redirect
from waitress import serve
from functools import wraps

# Import các module con
from utils.firebase_config import ensure_firebase
from routes.wms import bp as wms_bp
from routes.report import bp as report_bp
from routes.sdd import bp as sdd_bp
import config

# ───── Setup Flask ─────
app = Flask(__name__, static_folder="static")
app.secret_key = config.SESSION_SECRET_KEY

# Tắt Werkzeug logging để tránh trùng lặp
import logging
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.WARNING)  # Chỉ show WARNING trở lên

# Register Blueprints
app.register_blueprint(wms_bp, url_prefix='/wms')
app.register_blueprint(report_bp, url_prefix='/api/report')
app.register_blueprint(sdd_bp, url_prefix='/api/report')

# ───── Constants ─────
PUBLIC_PATHS = {"/login"}  # Only login page is public

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

# ───── Authentication ─────
SESSION_VERSION = "v3_new_update"  # Change this to invalidate all old sessions

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if session is valid and has correct version
        if not session.get('authenticated') or session.get('version') != SESSION_VERSION:
            session.clear()  # Clear invalid/old session
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page"""
    if request.method == "POST":
        password = request.form.get('password', '')
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        if password_hash == config.AUTH_PASSWORD_HASH:
            session.clear()  # Clear any old data
            session['authenticated'] = True
            session['version'] = SESSION_VERSION  # Mark session with current version
            session.permanent = True
            app.logger.info("[AUTH] User logged in from %s", request.remote_addr)
            return redirect(url_for('home'))
        else:
            app.logger.warning("[AUTH] Failed login attempt from %s", request.remote_addr)
            return redirect(url_for('login', error=1))

    # GET request - show login page
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Logout and clear session"""
    session.clear()
    app.logger.info("[AUTH] User logged out from %s", request.remote_addr)
    return redirect(url_for('login'))

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
@login_required
def home():
    """Home page"""
    return render_template("home.html")

@app.route("/scan")
@login_required
def scan():
    """Scan Tool page"""
    return render_template("tool_scan.html")

@app.route("/handover")
@login_required
def handover():
    """Handover Tool page"""
    return render_template("tool_handover.html")

@app.route("/sdd")
@login_required
def sdd():
    """SDD Tool page"""
    return render_template("tool_sdd.html")

# ───── Server ─────
def run_flask():
    """Run Flask app with Waitress server (production) or Flask dev server (development)"""
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "9090"))
    threads = int(os.getenv("FLASK_THREADS", "15"))

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
        print(f"[DEV MODE] Threading ENABLED - using {threads} threads for concurrent requests")

        # Configure Flask logging to show reloader info
        app.logger.info("[SERVER: %s] Starting Flask dev server with auto-reload and threading", COMPUTER_NAME)

        # Use stat reloader with threading enabled
        app.run(
            host=host,
            port=port,
            debug=True,
            use_reloader=True,
            reloader_type='stat',  # stat is more stable on Windows
            threaded=True,         # Enable threading for concurrent requests
            processes=1            # Use threads instead of processes
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
