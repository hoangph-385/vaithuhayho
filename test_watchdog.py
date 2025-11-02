"""
Test watchdog file monitoring - để debug tại sao auto-reload không hoạt động
"""

import os
import sys
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class TestEventHandler(FileSystemEventHandler):
    """Một event handler đơn giản để debug watchdog"""

    def on_modified(self, event):
        if not event.is_directory:
            print(f"[WATCHDOG] FILE MODIFIED: {event.src_path}")

    def on_created(self, event):
        if not event.is_directory:
            print(f"[WATCHDOG] FILE CREATED: {event.src_path}")

    def on_deleted(self, event):
        if not event.is_directory:
            print(f"[WATCHDOG] FILE DELETED: {event.src_path}")


def test_watchdog():
    """Test watchdog observer trên thư mục hiện tại"""
    print("[TEST WATCHDOG] Starting watchdog test...")
    print(f"[TEST WATCHDOG] Watching directory: {os.getcwd()}")
    print("[TEST WATCHDOG] Try editing/creating/deleting files to see if watchdog detects changes")
    print("[TEST WATCHDOG] Press Ctrl+C to stop\n")

    # Exclude folders
    exclude_patterns = {"__pycache__", ".git", "logs", ".pytest_cache", "node_modules", ".venv", "venv"}

    event_handler = TestEventHandler()
    observer = Observer()

    # Watch thư mục gốc
    observer.schedule(event_handler, ".", recursive=True)

    # Watch subdirectories
    for root, dirs, files in os.walk("."):
        # Exclude certain directories
        dirs[:] = [d for d in dirs if d not in exclude_patterns]

        if root not in ["."]:
            try:
                observer.schedule(event_handler, root, recursive=False)
                print(f"[WATCHDOG] Watching: {root}")
            except Exception as e:
                print(f"[WATCHDOG] Error watching {root}: {e}")

    observer.start()
    print("\n[TEST WATCHDOG] Watchdog started! Modify a file to test...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[TEST WATCHDOG] Stopping watchdog...")

    observer.join()
    print("[TEST WATCHDOG] Done!")


if __name__ == "__main__":
    test_watchdog()
