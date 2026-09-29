"""One-time import of verified PDF records from temporary Render env vars.

Private customer rows are never stored in the public repository. Import runs
under maintenance and resumes safely after a restart using source IDs.
"""
import base64
import hashlib
import json
import os
import sys
import uuid
import zlib
from datetime import datetime, timezone
from decimal import Decimal

from pymongo import MongoClient

PARTS = ('CUSTOMERS', 'ORDERS', 'EXPENSES', 'MENU')
EXPECTED = {'customers': 93, 'orders': 470, 'expenses': 301, 'menu': 320}


def money(cents):
    return float(Decimal(cents) / 100)


def decode():
    encoded = {key: os.environ.get('GANOH_RECOVERY_' + key) for key in PARTS}
    if not any(encoded.values()):
        return None
    if not all(encoded.values()) or not os.environ.get('GANOH_RECOVERY_SHA256'):
        raise ValueError('Incomplete recovery payload')
    # Each part is individually compressed; digest uses uncompressed canonical JSON.
    arrays = {key.lower(): json.loads(zlib.decompress(base64.b64decode(encoded[key], validate=True))) for key in PARTS}
    canonical = json.dumps(arrays, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != os.environ['GANOH_RECOVERY_SHA256']:
        raise ValueError('Recovery checksum mismatch')
    if {key: len(value) for key, value in arrays.items()} != EXPECTED:
        raise ValueError('Recovery row counts mismatch')
    if sum(x['credit'] for x in arrays['customers']) != 8400 or \
       sum(x['due'] for x in arrays['orders']) != 694315 or \
       sum(x['amount'] for x in arrays['expenses']) != 5600818 or \
       sum(len(x['items']) for x in arrays['orders']) != 697:
        raise ValueError('Recovery financial checks mismatch')
    for order in arrays['orders']:
        if order['total'] - order['partial_paid'] != order['due'] or \
           sum(x['subtotal'] for x in order['items']) != order['total'] or \
           len(order['items']) != order['item_count']:
            raise ValueError('Recovery order/items mismatch')
    return arrays


def docs(data):
    customers = [{**c, 'credit': money(c['credit']), 'source': 'pdf_recovery'} for c in data['customers']]
    orders = []
    for item in data['orders']:
        orders.append({
            'id': item['id'], 'store': item['store'], 'customer_name': item['customer_name'],
            'created_at': item['created_at'], 'updated_at': item['created_at'],
            'total': money(item['total']), 'partial_paid': money(item['partial_paid']),
            'payment_method': 'prazo', 'prazo_paid': False, 'status': 'delivered',
            'items': [dict(menu_item_id=p['menu_item_id'], name=p['name'],
                           price=money(p['price']), quantity=p['quantity']) for p in item['items']],
            'source': 'pdf_recovery',
        })
    expenses = []
    for item in data['expenses']:
        day = datetime.strptime(item['date'], '%d/%m/%Y')
        # Date is provided by the PDF; clock time is not. Midday UTC stays on
        # the same Brazilian date and is explicitly marked as approximate.
        date = day.replace(hour=15, tzinfo=timezone.utc).isoformat()
        expenses.append({
            'id': item['id'], 'store': item['store'], 'description': item['description'],
            'category': item['category'], 'notes': item['notes'],
            'amount': money(item['amount']), 'created_at': date,
            'time_estimated_from_date': True, 'image_url': '', 'source': 'pdf_recovery',
        })
    menu = []
    for index, item in enumerate(data['menu']):
        key = f"ganoh-pdf-2026:{index}:{item['store']}:{item['name']}"
        menu.append({
            'id': str(uuid.uuid5(uuid.NAMESPACE_URL, key)), 'store': item['store'],
            'name': item['name'], 'category': item['category'],
            'price': money(item['price']), 'available': True,
            'description': '', 'image_url': '', 'source': 'pdf_recovery',
        })
    return {'prazo_customers': customers, 'orders': orders, 'expenses': expenses, 'menu': menu}


def main():
    data = decode()
    if data is None:
        return
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true':
        raise ValueError('Recovery requires maintenance mode')
    with MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=10000) as client:
        db = client[os.environ['DB_NAME']]
        db.command('ping')
        already = db.recovery_runs.find_one({'id': 'pdf-2026-09-28'})
        if already and already.get('status') == 'verified':
            print('GANOH recovery already verified')
            return
        rows = docs(data)
        for collection, records in rows.items():
            # Refuse to mix PDF rows with unrelated production records on first run.
            if db[collection].count_documents({'source': {'$ne': 'pdf_recovery'}}):
                raise ValueError(f'Recovery stopped: existing {collection} records')
            for record in records:
                db[collection].update_one({'id': record['id']}, {'$setOnInsert': record}, upsert=True)
            if db[collection].count_documents({'source': 'pdf_recovery'}) != len(records):
                raise ValueError(f'Recovery verification failed: {collection}')
        total_due = round(sum(o['total'] - o['partial_paid'] for o in db.orders.find({'source': 'pdf_recovery'})), 2)
        if total_due != 6943.15:
            raise ValueError('Recovered debt total mismatch')
        db.recovery_runs.update_one({'id': 'pdf-2026-09-28'}, {'$set': {
            'id': 'pdf-2026-09-28', 'status': 'verified', 'counts': EXPECTED,
            'debt_total': total_due, 'verified_at': datetime.now(timezone.utc).isoformat(),
        }}, upsert=True)
        print('GANOH PDF recovery verified: 93 customers, 470 debts, 697 items, 301 expenses, 320 menu entries; R$ 6943.15 due')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never print DB connection details or private customer data in logs.
        print(f'GANOH recovery stopped ({type(exc).__name__})', file=sys.stderr)
        sys.exit(1)
