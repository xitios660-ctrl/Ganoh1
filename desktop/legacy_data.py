"""Lossless encrypted history cache. Imports NEVER create sales/ledger/outbox events.

Operational balance/customer reconciliation is deliberately separate from raw
history: historical receipts must never be resent or counted as new revenue.
"""
import hashlib
from contextlib import closing
from bson import BSON, decode_all, json_util
from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument
from bson.timestamp import Timestamp
from backend.data_bridge.archive import ArchiveError, Reader
from backend.data_bridge.unit_export import UNIT_FORMAT, BUSINESS_COLLECTIONS, belongs
from desktop.offline_store import OfflineError

RAW=CodecOptions(document_class=RawBSONDocument)


def initialize(journal):
    with closing(journal._connect()) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS legacy_generations(
          generation TEXT PRIMARY KEY, manifest_hash TEXT NOT NULL, source_database TEXT NOT NULL,
          clock_seconds INTEGER NOT NULL,clock_increment INTEGER NOT NULL,
          manifest BLOB NOT NULL, next_page INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS legacy_versions(
          collection TEXT NOT NULL,source_key TEXT NOT NULL,fingerprint TEXT NOT NULL,document BLOB NOT NULL,
          PRIMARY KEY(collection,source_key,fingerprint));
        CREATE TABLE IF NOT EXISTS legacy_members(
          generation TEXT NOT NULL REFERENCES legacy_generations(generation),collection TEXT NOT NULL,
          source_key TEXT NOT NULL,fingerprint TEXT NOT NULL,
          PRIMARY KEY(generation,collection,source_key),
          FOREIGN KEY(collection,source_key,fingerprint) REFERENCES legacy_versions(collection,source_key,fingerprint));
        ''')


def active(journal):
    initialize(journal)
    with closing(journal._connect()) as db:
        pointer=db.execute("SELECT value FROM metadata WHERE key='legacy_active'").fetchone()
        if not pointer:return None
        value=dict(db.execute('SELECT generation,source_database,clock_seconds,clock_increment,complete FROM legacy_generations WHERE generation=?',(pointer[0],)).fetchone())
        value['history_complete']=bool(value.pop('complete'))
        baseline=db.execute("SELECT value FROM metadata WHERE key='legacy_operational_baseline'").fetchone()
        value['operational_baseline_ready']=bool(baseline and baseline[0])
        return value


def _guard(previous, manifest):
    stamp=manifest['read_timestamp']; incoming=(stamp.time,stamp.inc)
    clock=(previous['clock_seconds'],previous['clock_increment'])
    if previous['source_database']!=manifest['source_database'] or incoming<clock:
        raise ArchiveError('Mudança de origem ou regressão de versão exige revisão')
    if incoming==clock:
        old=BSON(bytes(previous['manifest'])).decode()
        def content(value):
            return sorted((c['name'],c['count'],c['sha256']) for c in value['collections'])
        if content(old)!=content(manifest):
            raise ArchiveError('Mesma versão com conteúdo divergente exige revisão')


def import_bundle(journal, path, phrase, *, after_page=None):
    if journal._key is None:
        raise OfflineError('Dados históricos exigem SQLCipher; importação sem criptografia recusada')
    initialize(journal)
    try:
        with Reader(path,phrase,kind=UNIT_FORMAT) as reader:
            manifest=reader.manifest
            stamp=manifest.get('read_timestamp')
            if manifest.get('unit')!=journal.unit or not isinstance(stamp,Timestamp):
                raise ArchiveError('Unidade ou timestamp da origem divergente')
            if any(c['name'] not in BUSINESS_COLLECTIONS for c in manifest['collections']):
                raise ArchiveError('Coleção privada ou não suportada recusada')
            reader.validate()  # all pages authenticated before staging any data
            raw_manifest=BSON.encode(manifest); manifest_hash=hashlib.sha256(raw_manifest).hexdigest()
            with closing(journal._connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    pointer=db.execute("SELECT value FROM metadata WHERE key='legacy_active'").fetchone()
                    if pointer:
                        previous=db.execute('SELECT * FROM legacy_generations WHERE generation=?',(pointer[0],)).fetchone()
                        _guard(previous,manifest)
                    old=db.execute('SELECT * FROM legacy_generations WHERE generation=?',(reader.id,)).fetchone()
                    if old and old['manifest_hash']!=manifest_hash:
                        raise ArchiveError('Identidade reutilizada com conteúdo diferente')
                    if old and old['complete']:
                        db.execute('COMMIT');return {'generation':reader.id,'already_imported':True}
                    db.execute('INSERT OR IGNORE INTO legacy_generations(generation,manifest_hash,source_database,clock_seconds,clock_increment,manifest) VALUES(?,?,?,?,?,?)',
                               (reader.id,manifest_hash,manifest['source_database'],stamp.time,stamp.inc,raw_manifest))
                    db.execute("INSERT OR REPLACE INTO metadata VALUES('legacy_staging',?)",(reader.id,))
                    db.execute('PRAGMA user_version = 4')
                    db.execute('COMMIT')
                except Exception:db.execute('ROLLBACK');raise
            page_number=0
            for collection in manifest['collections']:
                for page in collection['pages']:
                    with closing(journal._connect()) as db:
                        db.execute('BEGIN IMMEDIATE')
                        try:
                            state=db.execute('SELECT next_page FROM legacy_generations WHERE generation=?',(reader.id,)).fetchone()[0]
                            if state>page_number:
                                db.execute('COMMIT');page_number+=1;continue
                            if state!=page_number:raise ArchiveError('Checkpoint divergente')
                            records=decode_all(reader.read(page['entry']),codec_options=RAW)
                            for record in records:
                                if not belongs(collection['name'],record,journal.unit):raise ArchiveError('Registro de outra unidade recusado')
                                source_key=hashlib.sha256(BSON.encode({'_id':record['_id']})).hexdigest()
                                fingerprint=hashlib.sha256(record.raw).hexdigest()
                                db.execute('INSERT OR IGNORE INTO legacy_versions VALUES(?,?,?,?)',(collection['name'],source_key,fingerprint,record.raw))
                                db.execute('INSERT INTO legacy_members VALUES(?,?,?,?)',(reader.id,collection['name'],source_key,fingerprint))
                            db.execute('UPDATE legacy_generations SET next_page=? WHERE generation=?',(page_number+1,reader.id))
                            db.execute('COMMIT')
                        except Exception:db.execute('ROLLBACK');raise
                    page_number+=1
                    if after_page:after_page(page_number)
            with closing(journal._connect()) as db:
                db.execute('BEGIN')  # WAL read verification does not block new sales
                try:
                    for collection in manifest['collections']:
                        fingerprint=hashlib.sha256();count=0
                        # BSON _id order need not match its SHA key. Validate membership
                        # through stored raw content hashes, in original archive order.
                        for record in reader.documents(collection):
                            source_key=hashlib.sha256(BSON.encode({'_id':record['_id']})).hexdigest()
                            row=db.execute('SELECT v.document FROM legacy_members m JOIN legacy_versions v USING(collection,source_key,fingerprint) WHERE generation=? AND collection=? AND source_key=?',(reader.id,collection['name'],source_key)).fetchone()
                            if not row or bytes(row[0])!=record.raw:raise ArchiveError('Histórico local divergente')
                            fingerprint.update(bytes(row[0]));count+=1
                        actual=db.execute('SELECT COUNT(*) FROM legacy_members WHERE generation=? AND collection=?',(reader.id,collection['name'])).fetchone()[0]
                        if actual!=count or fingerprint.hexdigest()!=collection['sha256']:raise ArchiveError('Contagem/hash local divergentes')
                    db.execute('COMMIT')
                except Exception:db.execute('ROLLBACK');raise
            with closing(journal._connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    pointer=db.execute("SELECT value FROM metadata WHERE key='legacy_active'").fetchone()
                    if pointer:
                        prior=db.execute('SELECT * FROM legacy_generations WHERE generation=?',(pointer[0],)).fetchone()
                        _guard(prior,manifest)
                    db.execute('UPDATE legacy_generations SET complete=1 WHERE generation=?',(reader.id,))
                    db.execute("INSERT OR REPLACE INTO metadata VALUES('legacy_active',?)",(reader.id,))
                    db.execute('PRAGMA user_version = 4')
                    db.execute("DELETE FROM metadata WHERE key='legacy_staging' AND value=?",(reader.id,))
                    db.execute('COMMIT')
                except Exception:db.execute('ROLLBACK');raise
            return {'generation':reader.id,'already_imported':False,'collections':len(manifest['collections']),
                    'documents':sum(c['count'] for c in manifest['collections'])}
    except ArchiveError as exc:
        raise OfflineError(str(exc)) from None


def records(journal, collection, *, after='', limit=100):
    if collection not in BUSINESS_COLLECTIONS or type(limit) is not int or not 1<=limit<=100:
        raise OfflineError('Coleção ou paginação inválida')
    initialize(journal)
    with closing(journal._connect()) as db:
        db.execute('BEGIN')
        pointer=db.execute("SELECT value FROM metadata WHERE key='legacy_active'").fetchone()
        if not pointer:return {'items':[],'generation':None,'next_cursor':None}
        generation=pointer[0]
        last=''
        if after:
            try:
                cursor_generation,last=after.split(':',1)
                if cursor_generation!=generation or len(last)!=64 or any(c not in '0123456789abcdef' for c in last):raise ValueError()
            except ValueError:raise OfflineError('Cursor pertence a outra geração ou é inválido') from None
        rows=db.execute('SELECT m.source_key,v.document FROM legacy_members m JOIN legacy_versions v USING(collection,source_key,fingerprint) WHERE generation=? AND collection=? AND m.source_key>? ORDER BY m.source_key LIMIT ?',
                        (generation,collection,last,limit+1)).fetchall()
        chosen=rows[:limit]
        # Extended JSON preserves Decimal128/ObjectId/Binary without lossy coercion.
        import json
        items=[json.loads(json_util.dumps(BSON(bytes(r['document'])).decode(),json_options=json_util.CANONICAL_JSON_OPTIONS)) for r in chosen]
        return {'items':items,'generation':generation,'next_cursor':generation+':'+chosen[-1]['source_key'] if len(rows)>limit else None}
