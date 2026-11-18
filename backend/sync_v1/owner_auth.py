"""Owner access for isolated v1 ledger. Provision only in test/staging databases."""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime,timedelta,timezone
from desktop.auth import _hash
from desktop.offline_store import UNITS


def provision(db,username,password,units):
    if not db.name.startswith('ganoh_sync_test_'):raise ValueError('Isolated database required')
    if (not isinstance(username,str) or not re.fullmatch(r'[a-z0-9._-]{3,64}',username)
        or not isinstance(password,str) or not 12<=len(password)<=256
        or not isinstance(units,list) or not units or not all(unit in UNITS for unit in units)):
        raise ValueError('Username, strong password and authorized units required')
    db.reviewers.create_index('username',unique=True,partialFilterExpression={'username':{'$type':'string'}})
    salt=secrets.token_bytes(16);reviewer_id=str(uuid.uuid4())
    db.reviewers.insert_one({'_id':reviewer_id,'username':username,'salt':salt,'password_hash':_hash(password,salt),
        'units':sorted(set(units)),'revoked':False,'failures':0,'locked_until':0,
        'token_hash':hashlib.sha256(secrets.token_bytes(32)).hexdigest()})
    return reviewer_id


def login(db,username,password):
    if not isinstance(username,str) or len(username)>64 or not isinstance(password,str) or len(password)>256:return None
    def transaction(session):
        row=db.reviewers.find_one({'username':username,'revoked':False},session=session);now=int(time.time())
        if not row or row.get('locked_until',0)>now:
            _hash(password,b'ganoh-dummy-salt-');return None
        if not hmac.compare_digest(_hash(password,row['salt']),row['password_hash']):
            failures=row.get('failures',0)+1
            db.reviewers.update_one({'_id':row['_id']},{'$set':{'failures':failures,'locked_until':now+900 if failures>=5 else 0}},session=session)
            return None
        token=secrets.token_urlsafe(32)
        db.reviewers.update_one({'_id':row['_id']},{'$set':{'failures':0,'locked_until':0}},session=session)
        db.owner_sessions.insert_one({'token_hash':hashlib.sha256(token.encode()).hexdigest(),'reviewer_id':row['_id'],
                                     'expires_at':datetime.now(timezone.utc)+timedelta(hours=8)},session=session)
        return token
    with db.client.start_session() as session:return session.with_transaction(transaction)


def resolve(db,authorization):
    if not isinstance(authorization,str) or not authorization.startswith('Bearer ') or len(authorization)>1024:return None
    digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
    reviewer=db.reviewers.find_one({'token_hash':digest,'revoked':False})
    if reviewer:return reviewer
    token=db.owner_sessions.find_one({'token_hash':digest,'expires_at':{'$gt':datetime.now(timezone.utc)}})
    return db.reviewers.find_one({'_id':token['reviewer_id'],'revoked':False}) if token else None


def logout(db,authorization):
    if authorization.startswith('Bearer '):
        db.owner_sessions.delete_one({'token_hash':hashlib.sha256(authorization[7:].encode()).hexdigest()})
