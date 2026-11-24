"""Authenticated, encrypted and streamable BSON archives. Never extract ZIP paths."""
import hashlib
import json
import os
import secrets
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

from bson import BSON, decode_all
from bson.codec_options import CodecOptions
from bson.raw_bson import RawBSONDocument
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from desktop.backups import recovery_key

RAW = CodecOptions(document_class=RawBSONDocument)
FORMAT = 'ganoh-mongo-snapshot-v1'
MAX_CHUNK = 20 * 1024 * 1024


class ArchiveError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    result=hashlib.sha256()
    with open(path,'rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):
            result.update(chunk)
    return result.hexdigest()


class Writer:
    def __init__(self, file, phrase, *, kind=FORMAT):
        self.archive = zipfile.ZipFile(file, 'w', compression=zipfile.ZIP_STORED)
        self.id = str(uuid.uuid4())
        self.kind = kind
        salt = secrets.token_bytes(16)
        self.cipher = AESGCM(recovery_key(phrase, salt))
        self.archive.writestr('envelope.json', json.dumps({'format': kind, 'id': self.id, 'salt': salt.hex()}))
        self.count = 0

    def put(self, name, payload):
        if len(payload) > MAX_CHUNK:
            raise ArchiveError('Arquivo excede o limite por página')
        nonce = secrets.token_bytes(12)
        self.archive.writestr(name, nonce + self.cipher.encrypt(nonce, payload, (self.kind + ':' + self.id + ':' + name).encode()))
        return {'entry': name, 'sha256': digest(payload), 'bytes': len(payload)}

    def page(self, payload):
        name = 'pages/%08d.bin' % self.count
        self.count += 1
        return self.put(name, payload)

    def finish(self, manifest):
        self.put('manifest.bin', BSON.encode(manifest))
        self.archive.close()

    def close(self):
        self.archive.close()


@contextmanager
def new_file(destination):
    """Only publish a complete archive; existing backups are never replaced."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('O destino já existe; nada foi sobrescrito')
    handle, name = tempfile.mkstemp(prefix='.ganoh-encrypted-', dir=destination.parent)
    os.chmod(name, 0o600)
    try:
        with os.fdopen(handle, 'wb') as file:
            yield file
            file.flush()
            os.fsync(file.fileno())
        os.link(name, destination)  # atomic create-if-absent, including concurrent writers
    finally:
        Path(name).unlink(missing_ok=True)


class Reader:
    def __init__(self, path, phrase, *, kind=FORMAT):
        self.archive = zipfile.ZipFile(path)
        try:
            infos = self.archive.infolist()
            names = [item.filename for item in infos]
            if len(names) > 200_002 or len(names) != len(set(names)):
                raise ArchiveError('Diretório de backup inválido')
            if any(i.compress_type != zipfile.ZIP_STORED or i.file_size > MAX_CHUNK + 28 for i in infos):
                raise ArchiveError('Página comprimida ou excessiva recusada')
            if self.archive.getinfo('envelope.json').file_size > 2048:
                raise ArchiveError('Envelope inválido')
            envelope = json.loads(self.archive.read('envelope.json'))
            if envelope.get('format') != kind or str(uuid.UUID(envelope['id'])) != envelope['id']:
                raise ArchiveError('Formato de backup inválido')
            self.id = envelope['id']
            self.kind = kind
            self.cipher = AESGCM(recovery_key(phrase, bytes.fromhex(envelope['salt'])))
            self.manifest = BSON(self.read('manifest.bin')).decode()
            if self.manifest.get('archive_id') != self.id:
                raise ArchiveError('Identidade do backup divergente')
            expected = {'envelope.json', 'manifest.bin'}
            collections = self.manifest['collections']
            if not isinstance(collections, list) or len({c['name'] for c in collections}) != len(collections):
                raise ArchiveError('Coleções inválidas')
            for collection in collections:
                for page in collection['pages']:
                    name = page['entry']
                    if name in expected or not name.startswith('pages/') or not name.endswith('.bin'):
                        raise ArchiveError('Página duplicada ou inválida')
                    expected.add(name)
            if set(names) != expected:
                raise ArchiveError('Backup incompleto ou com conteúdo extra')
        except Exception:
            self.archive.close()
            raise ArchiveError('Backup ou frase de recuperação inválidos') from None

    def read(self, name):
        data = self.archive.read(name)
        return self.cipher.decrypt(data[:12], data[12:], (self.kind + ':' + self.id + ':' + name).encode())

    def documents(self, collection):
        count = 0
        fingerprint = hashlib.sha256()
        for page in collection['pages']:
            try:
                data = self.read(page['entry'])
                if digest(data) != page['sha256'] or len(data) != page['bytes']:
                    raise ArchiveError('Hash de página divergente')
                records = decode_all(data, codec_options=RAW)
            except Exception:
                raise ArchiveError('Página adulterada ou BSON inválido') from None
            for record in records:
                count += 1
                fingerprint.update(record.raw)
                yield record
        if count != collection['count'] or fingerprint.hexdigest() != collection['sha256']:
            raise ArchiveError('Contagem/hash da coleção divergentes')

    def validate(self):
        for collection in self.manifest['collections']:
            for _ in self.documents(collection):
                pass
        return {'archive_id': self.id, 'collections': len(self.manifest['collections']),
                'documents': sum(c['count'] for c in self.manifest['collections']), 'integrity': 'ok'}

    def close(self):
        self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
