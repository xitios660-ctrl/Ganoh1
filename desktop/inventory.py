"""Project local stock over a central snapshot without double-applying known effects."""
import json
from contextlib import closing


def outstanding(db):
    rows = db.execute('''SELECT o.operation_id,o.payload_json,o.state,e.position
        FROM operations o JOIN local_sales s ON s.operation_id=o.operation_id
        JOIN event_order e ON e.operation_id=o.operation_id
        LEFT JOIN inventory_coverage c ON c.operation_id=o.operation_id
        WHERE s.payment_method IN ('cash','prazo') AND c.operation_id IS NULL
        UNION ALL
        SELECT o.operation_id,o.payload_json,o.state,e.position
        FROM business_operations o JOIN event_order e ON e.operation_id=o.operation_id
        LEFT JOIN inventory_coverage c ON c.operation_id=o.operation_id
        WHERE o.kind IN ('stock.adjust','catalog.upsert') AND c.operation_id IS NULL ORDER BY position''').fetchall()
    return [(row['operation_id'], json.loads(row['payload_json']), row['state']) for row in rows]


def project(db):
    has_catalog=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog'").fetchone() is not None
    entries = {r['sku']: json.loads(r['data']) for r in db.execute('SELECT * FROM catalog')} if has_catalog else {}
    for entry in entries.values():
        entry.update(central_quantity=entry['quantity'], central_version=entry['version'], blocked=False)
    for _, payload, state in outstanding(db):
        if payload['kind']=='catalog.upsert':
            sku=payload['sku']
            if sku not in entries:entries[sku]={'sku':sku,'quantity':0,'version':0,'central_quantity':0,'central_version':0,'blocked':False}
            entry=entries[sku]
            entry.update({key:payload[key] for key in ('name','description','category','price_cents','prep_time','available')})
            entry['version']+=1;entry['blocked']|=state=='conflict'
            continue
        if payload['kind'] == 'stock.adjust':
            movements = [(payload['sku'], payload['delta'])]
        else:
            movements = [(line.get('sku'), -line.get('quantity', 0)) for line in payload['items']
                         if isinstance(line.get('sku'), str) and type(line.get('quantity')) is int]
        for sku, delta in movements:
            if sku in entries:
                entries[sku]['quantity'] += delta
                entries[sku]['version'] += 1
                entries[sku]['blocked'] |= state == 'conflict'
    for entry in entries.values():
        entry['quantity'] = max(0, entry['quantity'])
    return sorted(entries.values(), key=lambda item: item['sku'])


def pending_ids(journal):
    with closing(journal._connect()) as db:
        return [operation for operation, _, _ in outstanding(db)][:100]
