"""Offline operator accounts in the encrypted journal. No default credentials."""
import hashlib
import hmac
import re
import secrets
import time
from contextlib import closing

ROLES = frozenset({'owner', 'cashier', 'kitchen'})


class AuthError(ValueError):
    pass


def initialize(db):
    db.execute('''CREATE TABLE IF NOT EXISTS operators (
        actor_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, salt BLOB NOT NULL,
        password_hash BLOB NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
        failures INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0)''')
    db.execute('''CREATE TABLE IF NOT EXISTS operator_sessions (
        token_hash TEXT PRIMARY KEY, actor_id TEXT NOT NULL REFERENCES operators(actor_id), expires_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS event_actors (
        operation_id TEXT PRIMARY KEY REFERENCES event_order(operation_id), actor_id TEXT NOT NULL, role TEXT NOT NULL)''')


def _hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=32768, r=8, p=1, maxmem=64*1024*1024)


def create(journal, username, password, role='owner', *, first=False):
    import uuid
    if not isinstance(username, str) or not re.fullmatch(r'[a-z0-9._-]{3,64}', username):
        raise AuthError('Usuário deve ter 3–64 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado')
    if not isinstance(password, str) or not 12 <= len(password) <= 256 or not isinstance(role,str) or role not in ROLES:
        raise AuthError('Senha deve ter pelo menos 12 caracteres e papel válido')
    salt=secrets.token_bytes(16); digest=_hash(password,salt); actor_id=str(uuid.uuid4())
    with closing(journal._connect()) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if first and db.execute('SELECT 1 FROM operators LIMIT 1').fetchone():
                raise AuthError('Proprietário inicial já configurado')
            db.execute('INSERT INTO operators(actor_id,username,salt,password_hash,role) VALUES(?,?,?,?,?)',
                       (actor_id,username,salt,digest,role))
            db.execute('COMMIT')
        except journal._driver.IntegrityError as exc:
            db.execute('ROLLBACK'); raise AuthError('Usuário já cadastrado') from exc
        except Exception:
            db.execute('ROLLBACK'); raise
    return actor_id


def login(journal, username, password):
    if not isinstance(username,str) or not isinstance(password,str) or len(username)>64 or len(password)>256:
        raise AuthError('Credenciais inválidas')
    now=int(time.time())
    with closing(journal._connect()) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            user=db.execute('SELECT * FROM operators WHERE username=?',(username,)).fetchone()
            if not user or not user['active'] or user['locked_until']>now:
                # Still pay the password KDF cost for an unknown/locked account.
                _hash(password,b'ganoh-dummy-salt-')
                db.execute('COMMIT'); raise AuthError('Credenciais inválidas ou acesso temporariamente bloqueado')
            if not hmac.compare_digest(_hash(password,user['salt']),user['password_hash']):
                failures=user['failures']+1
                db.execute('UPDATE operators SET failures=?,locked_until=? WHERE actor_id=?',
                           (failures,now+900 if failures>=5 else 0,user['actor_id']))
                db.execute('COMMIT'); raise AuthError('Credenciais inválidas ou acesso temporariamente bloqueado')
            token=secrets.token_urlsafe(32)
            db.execute('UPDATE operators SET failures=0,locked_until=0 WHERE actor_id=?',(user['actor_id'],))
            db.execute('DELETE FROM operator_sessions WHERE expires_at<=?',(now,))
            db.execute('INSERT INTO operator_sessions VALUES(?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(),user['actor_id'],now+8*3600))
            db.execute('COMMIT')
            return token
        except AuthError:
            raise
        except Exception:
            if db.in_transaction: db.execute('ROLLBACK')
            raise


def actor(journal, token):
    if not isinstance(token,str) or len(token)>256: return None
    with closing(journal._connect()) as db:
        row=db.execute('''SELECT o.actor_id,o.username,o.role FROM operator_sessions s JOIN operators o ON o.actor_id=s.actor_id
            WHERE s.token_hash=? AND s.expires_at>? AND o.active=1''',
            (hashlib.sha256(token.encode()).hexdigest(),int(time.time()))).fetchone()
        return dict(row) if row else None


def logout(journal, token):
    if not isinstance(token,str): return
    with closing(journal._connect()) as db:
        db.execute('DELETE FROM operator_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))


def allowed(role, kind):
    if not isinstance(kind,str): return False
    if role=='owner': return True
    if role=='cashier': return kind in {'sale.create','cash.open','cash.close','expense.create','customer.create','prazo.receive','order.status'}
    return role=='kitchen' and kind=='order.status'
