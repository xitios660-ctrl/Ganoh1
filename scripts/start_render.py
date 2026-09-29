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
    recovery = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() == 'true' and \
       os.environ.get('GANOH_RECOVERY_CUSTOMERS'):
        # Keep the maintenance page healthy during a slow Atlas import.
        recovery = subprocess.Popen([sys.executable, 'scripts/recover_pdf.py'], cwd=ROOT)
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and os.environ.get('WHATSAPP_PROVIDER') == 'baileys':
        children.append(subprocess.Popen(['node', 'server.mjs'], cwd=ROOT / 'whatsapp'))
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'render_app:app',
                                     '--host', '0.0.0.0', '--port', os.environ.get('PORT', '10000'),
                                     '--no-access-log'], cwd=ROOT / 'backend'))
    smoke = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_RECOVERY_SOURCE') == 'pdf':
        smoke = subprocess.Popen([sys.executable, 'scripts/smoke_render.py'], cwd=ROOT)
    while not stopping and all(child.poll() is None for child in children):
        if recovery and recovery.poll() is not None:
            print('GANOH recovery process finished' if recovery.returncode == 0 else
                  'GANOH recovery process failed; maintenance remains active', flush=True)
            recovery = None
        if smoke and smoke.poll() is not None:
            print('GANOH read-only smoke finished' if smoke.returncode == 0 else
                  'GANOH read-only smoke failed', flush=True)
            smoke = None
        time.sleep(0.5)
    failed = any(child.poll() not in (None, 0) for child in children)
finally:
    if 'recovery' in locals() and recovery and recovery.poll() is None:
        recovery.terminate()
    if 'smoke' in locals() and smoke and smoke.poll() is None:
        smoke.terminate()
    stop()
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
sys.exit(1 if failed else 0)
