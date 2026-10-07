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
    e2e = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_E2E_ONCE', 'false').lower() == 'true':
        e2e = subprocess.Popen([sys.executable, 'scripts/e2e_production.py'], cwd=ROOT)
    routing_test = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_STORE_ROUTING_TEST_ONCE', 'false').lower() == 'true':
        routing_test = subprocess.Popen([sys.executable, 'scripts/store_routing_e2e.py'], cwd=ROOT)
    value_audit = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_VALUE_AUDIT_ONCE', 'false').lower() == 'true':
        value_audit = subprocess.Popen([sys.executable, 'scripts/value_audit_e2e.py'], cwd=ROOT)
    cashflow_export = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_CASHFLOW_EXPORT_ONCE', 'false').lower() == 'true':
        cashflow_export = subprocess.Popen([sys.executable, 'scripts/export_cashflow_snapshot.py'], cwd=ROOT)
    gym_debug = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_GYM_DEBUG_ONCE', 'false').lower() == 'true':
        gym_debug = subprocess.Popen([sys.executable, 'scripts/debug_gym_today.py'], cwd=ROOT)
    while not stopping and all(child.poll() is None for child in children):
        if recovery and recovery.poll() is not None:
            print('GANOH recovery process finished' if recovery.returncode == 0 else
                  'GANOH recovery process failed; maintenance remains active', flush=True)
            recovery = None
        if smoke and smoke.poll() is not None:
            print('GANOH read-only smoke finished' if smoke.returncode == 0 else
                  'GANOH read-only smoke failed', flush=True)
            smoke = None
        if e2e and e2e.poll() is not None:
            print('GANOH full E2E finished' if e2e.returncode == 0 else
                  'GANOH full E2E failed', flush=True)
            e2e = None
        if routing_test and routing_test.poll() is not None:
            print('GANOH store routing test finished' if routing_test.returncode == 0 else
                  'GANOH store routing test failed', flush=True)
            routing_test = None
        if value_audit and value_audit.poll() is not None:
            print('GANOH value audit finished' if value_audit.returncode == 0 else
                  'GANOH value audit failed', flush=True)
            value_audit = None
        if cashflow_export and cashflow_export.poll() is not None:
            print('GANOH cashflow export finished' if cashflow_export.returncode == 0 else
                  'GANOH cashflow export failed', flush=True)
            cashflow_export = None
        if gym_debug and gym_debug.poll() is not None:
            print('GANOH GYM debug finished' if gym_debug.returncode == 0 else
                  'GANOH GYM debug failed', flush=True)
            gym_debug = None
        time.sleep(0.5)
    failed = any(child.poll() not in (None, 0) for child in children)
finally:
    if 'recovery' in locals() and recovery and recovery.poll() is None:
        recovery.terminate()
    if 'smoke' in locals() and smoke and smoke.poll() is None:
        smoke.terminate()
    if 'e2e' in locals() and e2e and e2e.poll() is None:
        e2e.terminate()
    if 'routing_test' in locals() and routing_test and routing_test.poll() is None:
        routing_test.terminate()
    if 'value_audit' in locals() and value_audit and value_audit.poll() is None:
        value_audit.terminate()
    if 'cashflow_export' in locals() and cashflow_export and cashflow_export.poll() is None:
        cashflow_export.terminate()
    if 'gym_debug' in locals() and gym_debug and gym_debug.poll() is None:
        gym_debug.terminate()
    stop()
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
sys.exit(1 if failed else 0)
