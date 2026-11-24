"""Dedicated read-only TV identities. Never accepted by owner/device authorizers."""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from desktop.auth import _hash
from desktop.offline_store import UNITS


def initialize(db):
    if not db.name.startswith('ganoh_sync_test_'):
        raise ValueError('Isolated database required')
    db.tv_accounts.create_index('username', unique=True)
    db.tv_sessions.create_index('token_hash', unique=True)
    db.tv_sessions.create_index('expires_at', expireAfterSeconds=0)


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create(db, owner, body):
    username, password, units = body.get('username'), body.get('password'), body.get('units')
    if (not isinstance(username, str) or not re.fullmatch(r'[a-z0-9._-]{3,64}', username)
        or not isinstance(password, str) or not 12 <= len(password) <= 256
        or not isinstance(units, list) or not units or not all(isinstance(u, str) and u in UNITS for u in units)):
        raise HTTPException(422, 'TV username, strong dedicated password and units required')
    units = sorted(set(units))
    if not set(units) <= set(owner.get('units', [])):
        raise HTTPException(403, 'Owner unit mismatch')
    if owner.get('password_hash') and hmac.compare_digest(_hash(password, owner['salt']), owner['password_hash']):
        raise HTTPException(422, 'TV password must differ from owner password')
    account_id, salt = str(uuid.uuid4()), secrets.token_bytes(16)
    encoded = _hash(password, salt)
    now = datetime.now(timezone.utc)
    def transaction(session):
        active = db.reviewers.update_one({'_id': owner['_id'], 'revoked': False, 'units': {'$all': units}},
                                        {'$inc': {'tv_revision': 1}}, session=session)
        if active.matched_count != 1:
            raise HTTPException(403, 'Owner no longer authorized')
        if db.tv_accounts.count_documents({'owner_id': owner['_id'], 'revoked': False}, session=session) >= 20:
            raise HTTPException(409, 'Maximum active TV accounts reached')
        db.tv_accounts.insert_one({'_id': account_id, 'owner_id': owner['_id'], 'username': username,
            'salt': salt, 'password_hash': encoded, 'units': units, 'revoked': False,
            'failures': 0, 'locked_until': 0, 'created_at': now}, session=session)
        db.tv_audit.insert_one({'_id': str(uuid.uuid4()), 'kind': 'create', 'account_id': account_id,
                               'owner_id': owner['_id'], 'units': units, 'created_at': now}, session=session)
        return {'account_id': account_id, 'username': username, 'units': units, 'scope': 'tv:read'}
    try:
        with db.client.start_session() as session:
            return session.with_transaction(transaction, read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'))
    except DuplicateKeyError:
        raise HTTPException(409, 'TV username unavailable')


def accounts(db, owner):
    return [{'account_id': r['_id'], 'username': r['username'], 'units': r['units'],
             'revoked': r['revoked'], 'created_at': r['created_at'].isoformat()}
            for r in db.tv_accounts.find({'owner_id': owner['_id']}).sort([('revoked', 1), ('created_at', -1)]).limit(100)]


def revoke(db, owner, account_id):
    def transaction(session):
        active = db.reviewers.update_one({'_id': owner['_id'], 'revoked': False},
                                        {'$inc': {'tv_revision': 1}}, session=session)
        if active.matched_count != 1:
            raise HTTPException(401, 'Owner revoked')
        row = db.tv_accounts.find_one({'_id': account_id, 'owner_id': owner['_id']}, session=session)
        if not row:
            raise HTTPException(404, 'TV account not found')
        if not row['revoked']:
            db.tv_accounts.update_one({'_id': account_id}, {'$set': {'revoked': True}}, session=session)
            db.tv_sessions.delete_many({'account_id': account_id}, session=session)
            db.tv_audit.insert_one({'_id': str(uuid.uuid4()), 'kind': 'revoke', 'account_id': account_id,
                'owner_id': owner['_id'], 'created_at': datetime.now(timezone.utc)}, session=session)
        return {'account_id': account_id, 'revoked': True}
    with db.client.start_session() as session:
        return session.with_transaction(transaction, read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'))


def login(db, username, password):
    if not isinstance(username, str) or len(username) > 64 or not isinstance(password, str) or len(password) > 256:
        return None
    def transaction(session):
        now = int(time.time())
        row = db.tv_accounts.find_one({'username': username, 'revoked': False}, session=session)
        if not row or row.get('locked_until', 0) > now:
            _hash(password, b'ganoh-tv-dummy---')
            return None
        if not hmac.compare_digest(_hash(password, row['salt']), row['password_hash']):
            failures = row.get('failures', 0) + 1
            db.tv_accounts.update_one({'_id': row['_id']}, {'$set': {'failures': failures,
                'locked_until': now + 900 if failures >= 5 else 0}}, session=session)
            return None
        owner = db.reviewers.find_one({'_id': row['owner_id'], 'revoked': False}, session=session)
        if not owner or not set(row['units']) & set(owner.get('units', [])):
            return None
        token = secrets.token_urlsafe(32)
        db.tv_accounts.update_one({'_id': row['_id']}, {'$set': {'failures': 0, 'locked_until': 0}}, session=session)
        db.tv_sessions.insert_one({'token_hash': _digest(token), 'account_id': row['_id'],
                                  'expires_at': datetime.now(timezone.utc) + timedelta(hours=8)}, session=session)
        return token
    with db.client.start_session() as session:
        return session.with_transaction(transaction, read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'))


def resolve(db, authorization):
    if not isinstance(authorization, str) or not authorization.startswith('Bearer ') or len(authorization) > 1024:
        return None
    session = db.tv_sessions.find_one({'token_hash': _digest(authorization[7:]),
                                      'expires_at': {'$gt': datetime.now(timezone.utc)}})
    if not session:
        return None
    account = db.tv_accounts.find_one({'_id': session['account_id'], 'revoked': False})
    if not account:
        return None
    owner = db.reviewers.find_one({'_id': account['owner_id'], 'revoked': False})
    units = sorted(set(account['units']) & set(owner.get('units', [])) & UNITS) if owner else []
    return {'_id': 'tv:' + account['_id'], 'units': units} if units else None


def logout(db, authorization):
    if isinstance(authorization, str) and authorization.startswith('Bearer '):
        db.tv_sessions.delete_one({'token_hash': _digest(authorization[7:])})


class PrivateResponses:
    """Prevent shared/browser caches from retaining authenticated financial views."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith(('/api/sync/v1/tv/', '/api/sync/v1/owner/')):
            return await self.app(scope, receive, send)
        async def private_send(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                headers = [(key, value) for key, value in message.get('headers', []) if key.lower() != b'cache-control']
                message['headers'] = headers + [(b'cache-control', b'no-store')]
            await send(message)
        await self.app(scope, receive, private_send)
