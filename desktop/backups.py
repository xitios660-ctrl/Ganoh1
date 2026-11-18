"""Consistent encrypted backups with an independently recoverable wrapped DB key.

Restoration always creates a NEW isolated directory. Never replaces the live DB.
"""
import hashlib
import hmac
import io
import json
import secrets
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from desktop.offline_store import OfflineJournal, OfflineError, _canonical
from desktop.windows_secrets import save_secret

MAX_BYTES=64*1024*1024


def recovery_key(password,salt):
    if not isinstance(password,str) or not 16<=len(password)<=256:
        raise OfflineError('Use uma frase de recuperação de 16 a 256 caracteres')
    return hashlib.scrypt(password.encode(),salt=salt,n=32768,r=8,p=1,dklen=32,maxmem=64*1024*1024)


def export(journal,password):
    if journal._key is None:
        raise OfflineError('Backup exige banco SQLCipher; fallback sem criptografia proibido')
    salt=secrets.token_bytes(16); wrapping=recovery_key(password,salt)
    with tempfile.TemporaryDirectory() as directory:
        file=Path(directory)/'journal.sqlite3'
        with closing(journal._connect()) as source:
            target=journal._driver.connect(str(file),isolation_level=None)
            try:
                target.execute("PRAGMA key = \"x'"+journal._key.hex()+"'\"")
                source.backup(target)
                if target.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise OfflineError('Backup falhou na verificação de integridade')
                version=target.execute('PRAGMA user_version').fetchone()[0]
            finally:target.close()
        if file.stat().st_size>MAX_BYTES:raise OfflineError('Backup excede o limite desta versão (64 MiB)')
        data=file.read_bytes()
    manifest={'format':1,'unit':journal.unit,'schema':version,'created_at':datetime.now(timezone.utc).isoformat(),
              'sha256':hashlib.sha256(data).hexdigest(),'salt':salt.hex(),'nonce':secrets.token_bytes(12).hex()}
    manifest['wrapped_key']=AESGCM(wrapping).encrypt(bytes.fromhex(manifest['nonce']),journal._key,_canonical(manifest).encode()).hex()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('manifest.json',_canonical(manifest)); archive.writestr('journal.sqlite3',data)
    return output.getvalue()


def restore_isolated(data,password,directory,unit,*,protect_key=save_secret):
    if not isinstance(data,bytes) or len(data)>MAX_BYTES+16384:raise OfflineError('Arquivo de backup inválido ou muito grande')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sorted(archive.namelist())!=['journal.sqlite3','manifest.json']:raise ValueError()
            for info in archive.infolist():
                if info.compress_type!=zipfile.ZIP_STORED or info.file_size>MAX_BYTES:raise ValueError()
            if archive.getinfo('manifest.json').file_size>8192:raise ValueError()
            manifest=json.loads(archive.read('manifest.json')); database=archive.read('journal.sqlite3')
        if type(manifest.get('format')) is not int or manifest['format']!=1 or manifest.get('unit')!=unit:raise ValueError()
        wrapped=bytes.fromhex(manifest.pop('wrapped_key'))
        if not hmac.compare_digest(hashlib.sha256(database).hexdigest(),manifest['sha256']):raise ValueError()
        key=AESGCM(recovery_key(password,bytes.fromhex(manifest['salt']))).decrypt(bytes.fromhex(manifest['nonce']),wrapped,_canonical(manifest).encode())
        if len(key)!=32:raise ValueError()
    except Exception as exc:
        raise OfflineError('Senha de recuperação inválida, unidade incorreta ou backup adulterado') from exc
    target=Path(directory)
    target.mkdir(parents=False,exist_ok=False,mode=0o700)
    try:
        (target/'journal.sqlite3').write_bytes(database)
        restored=OfflineJournal(target/'journal.sqlite3',unit,encryption_key=key)
        with closing(restored._connect()) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise OfflineError('Restauração falhou na integridade')
            db.execute('DELETE FROM operator_sessions')
        protect_key(target/'database-key.dpapi',key)
        return restored
    except Exception:
        # Keep the isolated encrypted copy for diagnosis; never alter the original.
        raise
