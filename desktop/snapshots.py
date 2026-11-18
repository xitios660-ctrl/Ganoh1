"""Durable, page-atomic snapshots. Published catalog changes only on final page."""
import json
from contextlib import closing
from desktop.offline_store import OfflineError


def initialize(journal):
    with closing(journal._connect()) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS snapshot_state (
          id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT, cursor TEXT,
          published_at TEXT);
        INSERT OR IGNORE INTO snapshot_state(id) VALUES(1);
        CREATE TABLE IF NOT EXISTS snapshot_staging (
          sku TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS catalog (sku TEXT PRIMARY KEY, data TEXT NOT NULL);
        ''')


def cursor(journal):
    initialize(journal)
    with closing(journal._connect()) as db:
        return db.execute('SELECT cursor FROM snapshot_state WHERE id=1').fetchone()[0]


def apply_page(journal, page, expected_cursor):
    initialize(journal)
    if page.get('unit') != journal.unit or not isinstance(page.get('generation'), str):
        raise OfflineError('Snapshot unit/generation mismatch')
    if not isinstance(page.get('items'), list) or type(page.get('done')) is not bool:
        raise OfflineError('Invalid snapshot page')
    if page['done'] != (page.get('next_cursor') is None):
        raise OfflineError('Invalid snapshot continuation')
    with closing(journal._connect()) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            state = db.execute('SELECT * FROM snapshot_state WHERE id=1').fetchone()
            if state['cursor'] != expected_cursor:
                raise OfflineError('Snapshot cursor changed concurrently')
            if (state['published_at'] and page.get('created_at')
                    and page['created_at'] < state['published_at']):
                raise OfflineError('Snapshot is older than published catalog')
            if expected_cursor is None:
                db.execute('DELETE FROM snapshot_staging')
                db.execute('DELETE FROM inventory_coverage_staging')
            elif state['generation'] != page['generation']:
                raise OfflineError('Snapshot generation changed')
            coverage = page.get('covered_operations', [])
            from desktop.business_rules import identifier, BusinessError
            if not isinstance(coverage, list) or len(coverage) > 100:
                raise OfflineError('Invalid snapshot coverage')
            try:
                for receipt in coverage:
                    if not isinstance(receipt, dict):
                        raise OfflineError('Invalid coverage receipt')
                    operation = identifier(receipt.get('operation_id'))
                    table = journal._operation_table(db, operation)
                    local = db.execute(f'SELECT fingerprint FROM {table} WHERE operation_id=?', (operation,)).fetchone()
                    if local:
                        if local['fingerprint'] != receipt.get('fingerprint'):
                            raise OfflineError('Coverage fingerprint mismatch')
                        db.execute('INSERT OR IGNORE INTO inventory_coverage_staging VALUES(?)', (operation,))
            except BusinessError as exc:
                raise OfflineError(str(exc)) from exc
            for item in page['items']:
                if (not isinstance(item, dict) or not isinstance(item.get('sku'), str)
                        or any(type(item.get(k)) is not int or item[k] < 0
                               for k in ('quantity', 'price_cents', 'version'))):
                    raise OfflineError('Invalid catalog item')
                db.execute('INSERT INTO snapshot_staging VALUES(?,?)',
                           (item['sku'], json.dumps(item)))
            if page['done']:
                old = {r['sku']: json.loads(r['data']) for r in db.execute('SELECT * FROM catalog')}
                for row in db.execute('SELECT * FROM snapshot_staging'):
                    incoming = json.loads(row['data'])
                    if row['sku'] in old and incoming['version'] < old[row['sku']]['version']:
                        raise OfflineError('Catalog version downgrade rejected')
                db.execute('DELETE FROM catalog')
                db.execute('INSERT INTO catalog SELECT * FROM snapshot_staging')
                db.execute('INSERT OR IGNORE INTO inventory_coverage SELECT * FROM inventory_coverage_staging')
                db.execute('DELETE FROM inventory_coverage_staging')
                db.execute('DELETE FROM snapshot_staging')
            db.execute('DELETE FROM inventory_coverage_staging')
            db.execute('UPDATE snapshot_state SET generation=?,cursor=?,published_at=CASE WHEN ? THEN ? ELSE published_at END WHERE id=1',
                       (page['generation'], page.get('next_cursor'), page['done'], page.get('created_at')))
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise


def catalog(journal, *, projected=True):
    initialize(journal)
    with closing(journal._connect()) as db:
        if projected:
            from desktop.inventory import project
            return project(db)
        return [json.loads(r[0]) for r in db.execute('SELECT data FROM catalog ORDER BY sku')]


def pull_once(journal, fetch):
    current = cursor(journal)
    page = fetch(current)
    apply_page(journal, page, current)
    return page['done']


def restart(journal):
    """Abandon an expired generation without touching published catalog/outbox."""
    initialize(journal)
    with closing(journal._connect()) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('DELETE FROM snapshot_staging')
            db.execute('DELETE FROM inventory_coverage_staging')
            db.execute('UPDATE snapshot_state SET generation=NULL,cursor=NULL WHERE id=1')
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise
