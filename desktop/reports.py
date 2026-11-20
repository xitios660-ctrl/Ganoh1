"""Local ledger export, explicitly provisional and separate from central reports."""
import csv
import io
import json
from contextlib import closing
from desktop.offline_store import OfflineError


def ledger_csv(journal):
    with closing(journal._connect()) as db:
        rows=db.execute('''SELECT l.operation_id,l.line,l.account,l.amount_cents,e.kind,
          COALESCE(s.state,b.state) state,COALESCE(s.created_at,b.created_at) created_at,
          COALESCE(s.payload_json,b.payload_json) payload,o.username
          FROM ledger l JOIN event_order e ON e.operation_id=l.operation_id
          LEFT JOIN operations s ON s.operation_id=l.operation_id
          LEFT JOIN business_operations b ON b.operation_id=l.operation_id
          LEFT JOIN event_actors a ON a.operation_id=l.operation_id
          LEFT JOIN operators o ON o.actor_id=a.actor_id ORDER BY e.position,l.line LIMIT 100001''').fetchall()
    if len(rows)>100000:raise OfflineError('Relatório excede o limite desta versão; exportação não foi truncada')
    output=io.StringIO(newline='');writer=csv.writer(output)
    writer.writerow(['unit','scope','operation_id','line','account','amount_cents','kind','sync_state','created_at_utc','operator','description'])
    def safe(value):
        if value is None:return ''
        if isinstance(value,int):return value
        text=str(value)
        return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
    for row in rows:
        payload=json.loads(row['payload']) if row['payload'] else {}
        writer.writerow([safe(v) for v in [journal.unit,'LOCAL_PROVISIONAL',row['operation_id'],row['line'],row['account'],
            row['amount_cents'],row['kind'],row['state'],row['created_at'],row['username'],payload.get('description',payload.get('customer_name',''))]])
    return '\ufeff'+output.getvalue()
