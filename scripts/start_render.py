"""Supervise one API process and one loopback-only Baileys process."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
children = []
stopping = False

def stop(*_):
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.terminate()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and os.environ.get('WHATSAPP_PROVIDER') == 'baileys':
        children.append(subprocess.Popen(['node', 'server.mjs'], cwd=ROOT / 'whatsapp'))
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'render_app:app',
                                     '--host', '0.0.0.0', '--port', os.environ.get('PORT', '10000'),
                                     '--no-access-log'], cwd=ROOT / 'backend'))
    while not stopping and all(child.poll() is None for child in children):
        time.sleep(0.5)
    failed = any(child.poll() not in (None, 0) for child in children)
finally:
    stop()
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
sys.exit(1 if failed else 0)
