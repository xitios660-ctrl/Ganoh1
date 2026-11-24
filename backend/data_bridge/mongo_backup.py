"""Read-only full BSON snapshot; recovery ONLY into fresh local test databases.

Caller supplies one shared client. No URI/env lookup, source writes, cutoff dates,
API list limits, global config changes, or production server import.
"""
import hashlib
from datetime import datetime, timezone

from bson import BSON, json_util
from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument
from pymongo import IndexModel
from pymongo.errors import PyMongoError
from backend.data_bridge.archive import Writer, Reader, ArchiveError, new_file, file_digest

RAW = CodecOptions(document_class=RawBSONDocument)


def _catalog_signature(catalog):
    return BSON.encode({'collections':[{'name':c['name'],'type':c['type'],
        'options':c.get('options',{}),'uuid':c.get('info',{}).get('uuid')}
        for c in sorted(catalog,key=lambda c:c['name']) if not c['name'].startswith('system.')]})


def _index_signature(indexes):
    # Preserve compound key order, normalize only irrelevant metadata key ordering.
    result=[{'keys':list(item['key'].items()),'options':{k:v for k,v in item.items() if k not in ('key','ns','v')}}
            for item in sorted(indexes,key=lambda item:item['name'])]
    return json_util.dumps(result,sort_keys=True,json_options=json_util.CANONICAL_JSON_OPTIONS)


def capture(source, destination, phrase, *, page_bytes=4*1024*1024, on_collection=None):
    try:
        return _capture(source,destination,phrase,page_bytes=page_bytes,on_collection=on_collection)
    except PyMongoError:
        raise ArchiveError('Captura interrompida pelo MongoDB; origem intacta e pacote incompleto não publicado') from None


def _capture(source, destination, phrase, *, page_bytes, on_collection):
    if type(page_bytes) is not int or not 1024 <= page_bytes <= 16*1024*1024:
        raise ArchiveError('Tamanho de página inválido')
    started = datetime.now(timezone.utc)
    catalog = sorted(source.list_collections(), key=lambda c: c['name'])
    if any(c['type'] not in ('collection', 'view') for c in catalog):
        raise ArchiveError('Tipo de coleção exige adaptação antes do backup')
    catalog = [c for c in catalog if not c['name'].startswith('system.')]
    with new_file(destination) as file:
        writer = Writer(file, phrase)
        try:
            descriptors = []
            # MongoDB 5+ snapshot session fixes one read timestamp across all finds.
            # It is read-only and does not hold a long-running write transaction.
            with source.client.start_session(snapshot=True) as session:
                for info in catalog:
                    name = info['name']
                    if info['type'] == 'view':
                        descriptors.append({'name': name, 'type': 'view', 'options': info['options'],
                                            'indexes': [], 'pages': [], 'count': 0, 'sha256': hashlib.sha256().hexdigest()})
                        continue
                    collection = source.get_collection(name, codec_options=RAW)
                    indexes = list(source[name].list_indexes())
                    pages, payload, count = [], bytearray(), 0
                    fingerprint = hashlib.sha256()
                    # No to_list(limit), date filter, skip or implicit truncation.
                    with collection.find({}, session=session).sort('_id', 1).batch_size(100) as cursor:
                        for record in cursor:
                            data = record.raw
                            if payload and len(payload) + len(data) > page_bytes:
                                pages.append(writer.page(bytes(payload))); payload.clear()
                            payload.extend(data); fingerprint.update(data); count += 1
                    if payload:
                        pages.append(writer.page(bytes(payload)))
                    descriptors.append({'name': name, 'type': 'collection', 'options': info['options'],
                                        'indexes': indexes, 'pages': pages, 'count': count,
                                        'sha256': fingerprint.hexdigest()})
                    if on_collection:
                        on_collection(name, count)
                read_timestamp = session._snapshot_time  # pinned PyMongo 4.5; fail closed if unsupported
            # Detect catalog churn rather than silently omitting a newly created table.
            current_catalog = list(source.list_collections())
            if _catalog_signature(current_catalog) != _catalog_signature(catalog):
                raise ArchiveError('Catálogo mudou durante o backup; reinicie uma captura consistente')
            for descriptor in descriptors:
                if descriptor['type']=='collection':
                    current=sorted(source[descriptor['name']].list_indexes(),key=lambda item:item['name'])
                    original=sorted(descriptor['indexes'],key=lambda item:item['name'])
                    if BSON.encode({'indexes':current})!=BSON.encode({'indexes':original}):
                        raise ArchiveError('Índices mudaram durante o backup; captura recusada')
            writer.finish({'archive_id': writer.id, 'source_database': source.name,
                'consistency': 'mongodb_snapshot_session', 'read_timestamp': read_timestamp, 'started_at': started,
                'finished_at': datetime.now(timezone.utc), 'collections': descriptors})
            return {'archive_id': writer.id, 'collections': len(descriptors),
                    'documents': sum(c['count'] for c in descriptors), 'integrity': 'captured'}
        finally:
            writer.close()


def validate_restore(path, phrase, target):
    try:
        return _validate_restore(path,phrase,target)
    except PyMongoError:
        raise ArchiveError('Restauração de ensaio interrompida; destino em quarentena e origem intacta') from None


def _validate_restore(path, phrase, target):
    """Refuse existing/remote targets. Source is never an argument to recovery."""
    if not target.name.startswith('ganoh_restore_test_'):
        raise ArchiveError('Restauração permitida somente em banco de teste novo')
    address = target.client.address
    if not address or address[0] not in ('127.0.0.1', 'localhost', '::1'):
        raise ArchiveError('Restauração de ensaio exige MongoDB local isolado')
    if target.list_collection_names():
        raise ArchiveError('Destino existente recusado; nenhum registro foi substituído')
    # Expired TTL records must survive the drill, so exact full-data comparison is
    # possible. This check NEVER changes the server parameter or production config.
    if target.client.admin.command({'getParameter': 1, 'ttlMonitorEnabled': 1}).get('ttlMonitorEnabled') is not False:
        raise ArchiveError('Inicie o MongoDB descartável com ttlMonitorEnabled=false para o ensaio')
    physical_hash=file_digest(path)
    with Reader(path, phrase) as reader:
        result = reader.validate()  # authenticate ALL pages before the first write
        physical = [c for c in reader.manifest['collections'] if c['type'] == 'collection']
        views = [c for c in reader.manifest['collections'] if c['type'] == 'view']
        for descriptor in physical:
            name = descriptor['name']
            target.create_collection(name, **descriptor['options'])
            chunk = []; buffered = 0
            for record in reader.documents(descriptor):
                if chunk and (len(chunk)>=100 or buffered+len(record.raw)>4*1024*1024):
                    target[name].insert_many(chunk,bypass_document_validation=True)
                    chunk.clear();buffered=0
                chunk.append(record);buffered+=len(record.raw)
            if chunk:
                target[name].insert_many(chunk,bypass_document_validation=True)
            indexes = []
            for item in descriptor['indexes']:
                if item['name'] == '_id_':
                    continue
                options = {k: v for k, v in item.items() if k not in ('key', 'v', 'ns')}
                indexes.append(IndexModel(list(item['key'].items()), **options))
            if indexes:
                target[name].create_indexes(indexes)
            if _index_signature(list(target[name].list_indexes()))!=_index_signature(descriptor['indexes']):
                raise ArchiveError('Índices restaurados divergentes; ensaio não validado')
            actual = hashlib.sha256(); count = 0
            for record in target.get_collection(name, codec_options=RAW).find().sort('_id', 1):
                actual.update(record.raw); count += 1
            if count != descriptor['count'] or actual.hexdigest() != descriptor['sha256']:
                raise ArchiveError('Restauração divergente; destino de teste mantido em quarentena')
        # Create views only after their dependencies exist. Never run source scripts.
        while views:
            done = []
            for descriptor in views:
                if descriptor['options'].get('viewOn') in target.list_collection_names():
                    target.create_collection(descriptor['name'], **descriptor['options']); done.append(descriptor)
            if not done:
                raise ArchiveError('Dependência de view inválida; ensaio não validado')
            views = [c for c in views if c not in done]
        if file_digest(path)!=physical_hash:
            raise ArchiveError('Arquivo mudou durante a restauração; ensaio não validado')
        return {**result, 'archive_sha256':physical_hash, 'source_database':reader.manifest['source_database'],
                'restored_database': target.name, 'integrity': 'restored_and_verified'}
