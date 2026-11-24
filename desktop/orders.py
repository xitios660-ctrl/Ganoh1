"""Local kitchen progress; immutable business events audit every transition."""
import json
from contextlib import closing
from desktop.business_rules import BusinessError
from desktop.offline_store import _utc_now

TRANSITIONS={'received':'preparing','preparing':'ready','ready':'delivered'}


def prepare(db,payload):
    row=db.execute('SELECT * FROM order_progress WHERE sale_id=?',(payload['sale_id'],)).fetchone()
    if not row or row['version']!=payload['base_version'] or TRANSITIONS.get(row['status'])!=payload['status']:
        raise BusinessError('Pedido alterado ou transição inválida; atualize a cozinha')


def apply_local(db,payload):
    db.execute('UPDATE order_progress SET status=?,version=version+1,updated_at=?,last_operation_id=? WHERE sale_id=?',
               (payload['status'],_utc_now(),payload['operation_id'],payload['sale_id']))


def list_orders(journal):
    with closing(journal._connect()) as db:
        rows=db.execute('''SELECT p.*,o.payload_json,o.state FROM order_progress p
             JOIN local_sales s ON s.sale_id=p.sale_id JOIN operations o ON o.operation_id=s.operation_id
             ORDER BY o.sequence DESC LIMIT 200''').fetchall()
        result=[]
        for row in rows:
            payload=json.loads(row['payload_json'])
            table=journal._operation_table(db,row['last_operation_id'])
            state=db.execute(f'SELECT state FROM {table} WHERE operation_id=?',(row['last_operation_id'],)).fetchone()
            result.append({'sale_id':row['sale_id'],'status':row['status'],'version':row['version'],
                           'updated_at':row['updated_at'],'customer_name':payload.get('customer_name') or 'Cliente local',
                           'items':[{'sku':i.get('sku','legacy-item'),'name':i.get('name',i.get('sku','Produto legado')),'quantity':i.get('quantity',0)} for i in payload['items']],
                           'sync_state':state['state'] if state else row['state']})
        return result
