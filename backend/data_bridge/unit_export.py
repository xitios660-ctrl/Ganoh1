"""Derive a credential-free, strictly single-unit business bundle from a backup."""
import hashlib
from bson.timestamp import Timestamp
from desktop.offline_store import UNITS
from backend.data_bridge.archive import Writer, Reader, ArchiveError, new_file, file_digest

UNIT_FORMAT = 'ganoh-unit-bootstrap-v1'
UNIT_COLLECTIONS = frozenset({
    'stock','orders','order_history','cash_credit_topups','cash_drawer_config','cash_withdrawals',
    'daily_sales','monthly_sales','expenses','low_stock_list','pix_adjustments','prazo_customers',
    'prazo_history','prazo_partial_payments','prazo_payments','stock_movements','whatsapp_inbound',
})
SHARED_COLLECTIONS = frozenset({'menu','adicionais'})
# These remain intact in the full backup, NEVER in an employee/device bundle.
PRIVATE_COLLECTIONS = frozenset({'tenants','settings','deploy_markers','chart_cache'})
BUSINESS_COLLECTIONS = UNIT_COLLECTIONS | SHARED_COLLECTIONS


def belongs(name, document, unit):
    if name not in BUSINESS_COLLECTIONS:
        raise ArchiveError('Coleção não autorizada no pacote da unidade')
    store = document.get('store')
    if name in SHARED_COLLECTIONS and store in (None, 'all'):
        return True
    if store not in UNITS:
        raise ArchiveError('Registros sem unidade inequívoca exigem revisão: ' + name)
    return store == unit


def export_unit(backup, backup_phrase, destination, unit_phrase, unit, *, validated_backup=None, page_bytes=4*1024*1024):
    if unit not in UNITS:
        raise ArchiveError('Unidade inválida')
    if type(page_bytes) is not int or not 1024 <= page_bytes <= 16*1024*1024:
        raise ArchiveError('Tamanho de página inválido')
    if not isinstance(validated_backup,dict) or validated_backup.get('integrity')!='restored_and_verified':
        raise ArchiveError('É obrigatório validar a restauração isolada deste backup antes da carga')
    if file_digest(backup)!=validated_backup.get('archive_sha256'):
        raise ArchiveError('O comprovante de restauração pertence a outro arquivo')
    with Reader(backup, backup_phrase) as reader:
        reader.validate()
        manifest = reader.manifest
        if reader.id!=validated_backup.get('archive_id') or manifest['source_database']!=validated_backup.get('source_database'):
            raise ArchiveError('Comprovante de restauração e origem divergentes')
        stamp = manifest.get('read_timestamp')
        if manifest.get('consistency') != 'mongodb_snapshot_session' or not isinstance(stamp, Timestamp):
            raise ArchiveError('Origem sem timestamp consistente; pacote recusado')
        # Unmapped collections cannot be silently discarded from "complete history".
        unknown = {c['name'] for c in manifest['collections']} - BUSINESS_COLLECTIONS - PRIVATE_COLLECTIONS
        if unknown:
            raise ArchiveError('Existem coleções ainda não mapeadas; revise antes de distribuir')
        with new_file(destination) as file:
            writer = Writer(file, unit_phrase, kind=UNIT_FORMAT)
            try:
                collections=[]
                for source in manifest['collections']:
                    name=source['name']
                    if name in PRIVATE_COLLECTIONS:
                        continue
                    if source['type']!='collection':
                        raise ArchiveError('View exige mapeamento explícito; não foi descartada')
                    count=0; fingerprint=hashlib.sha256(); payload=bytearray(); pages=[]
                    for document in reader.documents(source):
                        if not belongs(name, document, unit):
                            continue
                        data=document.raw
                        if payload and len(payload)+len(data)>page_bytes:
                            pages.append(writer.page(bytes(payload)));payload.clear()
                        payload.extend(data);fingerprint.update(data);count+=1
                    if payload:
                        pages.append(writer.page(bytes(payload)))
                    collections.append({'name':name,'count':count,'sha256':fingerprint.hexdigest(),'pages':pages})
                writer.finish({'archive_id':writer.id,'unit':unit,'source_archive_id':reader.id,
                    'source_database':manifest['source_database'],'read_timestamp':stamp,
                    'consistency':manifest['consistency'],'started_at':manifest['started_at'],
                    'finished_at':manifest['finished_at'],'collections':collections})
                return {'unit':unit,'archive_id':writer.id,'documents':sum(c['count'] for c in collections)}
            finally:
                writer.close()
