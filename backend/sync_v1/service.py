"""Isolated staging sync service. Never imports the production application."""
import hashlib
import hmac
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Header, HTTPException
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from desktop.offline_store import _canonical


def create_app(db):
    # Explicit allowlist: accidental production configuration fails before writes.
    if not db.name.startswith('ganoh_sync_test_'):
        raise ValueError('Only isolated ganoh_sync_test_* databases are permitted')
    db.inbox.create_index([('unit', 1), ('operation_id', 1)], unique=True)
    db.sales.create_index([('unit', 1), ('sale_id', 1)], unique=True)
    db.devices.create_index('token_hash', unique=True)
    db.stock.create_index([('unit', 1), ('sku', 1)], unique=True)
    db.review_events.create_index([('unit', 1), ('review_id', 1)], unique=True)
    db.reviewers.create_index('token_hash', unique=True)
    db.snapshots.create_index('expires_at', expireAfterSeconds=0)
    app = FastAPI(title='GANOH isolated sync validation')

    def apply(device, item):
        payload = item.get('payload', {})
        if not isinstance(payload, dict):
            raise HTTPException(422, 'Invalid payload')
        identity = {key: item.get(key) for key in ('unit', 'operation_id', 'fingerprint')}
        if item.get('unit') != device['unit'] or payload.get('unit') != device['unit']:
            raise HTTPException(403, 'Unit mismatch')
        try:
            operation = str(uuid.UUID(item['operation_id']))
            digest = hashlib.sha256(_canonical(payload).encode('utf-8')).hexdigest()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(422, 'Invalid operation')
        if operation != payload.get('operation_id') or operation != item['operation_id'] or not hmac.compare_digest(digest, str(item.get('fingerprint', ''))):
            raise HTTPException(422, 'Invalid identity or fingerprint')
        if payload.get('kind') != 'sale.create' or item.get('kind') != 'sale.create':
            raise HTTPException(422, 'Unsupported operation')
        key = {'unit': device['unit'], 'operation_id': operation}

        def transaction(session):
            # Writing the device document serializes revocation with commits.
            active = db.devices.update_one(
                {'_id': device['_id'], 'revoked': False, 'unit': device['unit']},
                {'$inc': {'sync_attempts': 1}}, session=session)
            if active.matched_count != 1:
                raise HTTPException(401, 'Device revoked')
            previous = db.inbox.find_one(key, session=session)
            if previous:
                if previous['fingerprint'] != digest:
                    raise HTTPException(409, 'Operation ID reused with different content')
                reply = previous['reply'].copy()
                if reply['status'] == 'applied':
                    reply['status'] = 'already_applied'
                return reply
            reason = None
            items = payload.get('items')
            if payload.get('payment_method') != 'cash':
                reason = 'Payment requires financial review; settlement is not implemented'
            if not isinstance(payload.get('sale_id'), str) or not payload['sale_id'].strip():
                raise HTTPException(422, 'Invalid sale ID')
            if type(payload.get('total_cents')) is not int or payload['total_cents'] < 0:
                raise HTTPException(422, 'Invalid money')
            if not isinstance(items, list) or not items or len(items) > 200:
                raise HTTPException(422, 'Invalid items')
            total, stocks, seen = 0, [], set()
            for line in items:
                if not isinstance(line, dict) or not isinstance(line.get('sku'), str) or type(line.get('quantity')) is not int or line['quantity'] <= 0:
                    raise HTTPException(422, 'Invalid item')
                if line['sku'] in seen:
                    raise HTTPException(422, 'Duplicate SKU')
                seen.add(line['sku'])
                stock = db.stock.find_one({'unit': device['unit'], 'sku': line['sku']}, session=session)
                if not stock or type(line.get('base_version')) is not int or stock['version'] != line['base_version'] or stock['quantity'] < line['quantity']:
                    reason = 'Stock missing, insufficient or version changed; manual review required'
                else:
                    total += stock['price_cents'] * line['quantity']
                    stocks.append((stock, line['quantity']))
            if total != payload['total_cents']:
                reason = reason or 'Catalog total differs; manual review required'
            if db.sales.find_one({'unit': device['unit'], 'sale_id': payload['sale_id']}, session=session):
                reason = 'Sale ID already recorded by another operation'
            reply = {**identity, 'status': 'conflict' if reason else 'applied', 'receipt_id': str(uuid.uuid4())}
            if reason:
                reply['reason'] = reason
            else:
                for stock, quantity in stocks:
                    updated = db.stock.update_one({'_id': stock['_id'], 'version': stock['version']}, {'$inc': {'quantity': -quantity, 'version': 1}}, session=session)
                    if updated.modified_count != 1:
                        raise RuntimeError('Concurrent stock change')
                db.sales.insert_one({**key, 'sale_id': payload['sale_id'], 'payload': payload, 'receipt_id': reply['receipt_id'], 'total_cents': total}, session=session)
            db.inbox.insert_one({**key, 'device_id': device['_id'], 'fingerprint': digest, 'payload': payload, 'reply': reply, 'created_at': datetime.now(timezone.utc)}, session=session)
            return reply

        # Unique-index races abort their transaction; replay reads the winner.
        for attempt in range(3):
            try:
                with db.client.start_session() as session:
                    return session.with_transaction(
                        transaction, read_concern=ReadConcern('snapshot'),
                        write_concern=WriteConcern('majority'))
            except DuplicateKeyError:
                if attempt == 2:
                    raise HTTPException(503, 'Retry same operation ID')

    def authenticate(authorization):
        if not authorization.startswith('Bearer ') or len(authorization) > 1024:
            raise HTTPException(401, 'Device authentication required')
        token_hash = hashlib.sha256(authorization[7:].encode()).hexdigest()
        device = db.devices.find_one({'token_hash': token_hash, 'revoked': False})
        if not device:
            raise HTTPException(401, 'Invalid device')
        return device

    @app.get('/api/sync/v1/snapshot')
    def snapshot(cursor: str = '', authorization: str = Header(default='')):
        device = authenticate(authorization)
        if cursor:
            try:
                generation, offset_text = cursor.split(':')
                offset = int(offset_text)
                if str(uuid.UUID(generation)) != generation or offset < 0 or offset % 100:
                    raise ValueError()
            except (ValueError, AttributeError):
                raise HTTPException(422, 'Invalid cursor')
            saved = db.snapshots.find_one({'_id': generation, 'unit': device['unit'],
                                          'device_id': device['_id']})
            if not saved or saved['expires_at'].replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
                raise HTTPException(410, 'Snapshot expired; restart explicitly')
            if offset >= len(saved['items']):
                raise HTTPException(422, 'Cursor outside snapshot')
        else:
            generation, offset = str(uuid.uuid4()), 0
            def capture(session):
                items = list(db.stock.find({'unit': device['unit']}, {'_id': 0, 'sku': 1, 'name': 1, 'quantity': 1, 'price_cents': 1, 'version': 1}, session=session).sort('sku', 1).limit(1001))
                if len(items) > 1000:
                    raise HTTPException(413, 'Demo snapshot limit exceeded')
                now = datetime.now(timezone.utc)
                saved = {'_id': generation, 'unit': device['unit'], 'device_id': device['_id'],
                         'items': items, 'created_at': now.isoformat(), 'expires_at': now + timedelta(days=1)}
                db.snapshots.insert_one(saved, session=session)
                return saved
            with db.client.start_session() as session:
                saved = session.with_transaction(capture, read_concern=ReadConcern('snapshot'),
                                                 write_concern=WriteConcern('majority'))
        end = offset + 100
        done = end >= len(saved['items'])
        return {'unit': device['unit'], 'generation': generation, 'items': saved['items'][offset:end],
                'next_cursor': None if done else generation + ':' + str(end),
                'done': done, 'created_at': saved['created_at']}

    @app.post('/api/sync/v1/conflicts/review')
    def review(body: dict, authorization: str = Header(default='')):
        # Owner/support credentials are separate from store device credentials.
        if not authorization.startswith('Bearer '):
            raise HTTPException(401, 'Reviewer authentication required')
        reviewer = db.reviewers.find_one({'token_hash': hashlib.sha256(authorization[7:].encode()).hexdigest(), 'revoked': False})
        if not reviewer:
            raise HTTPException(401, 'Reviewer authentication required')
        unit = body.get('unit')
        if unit not in reviewer.get('units', []):
            raise HTTPException(403, 'Reviewer unit mismatch')
        try:
            review_id = str(uuid.UUID(body['review_id']))
            operation_id = str(uuid.UUID(body['operation_id']))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(422, 'Invalid review identity')
        if body.get('decision') not in ('reject', 'retain') or not isinstance(body.get('reason'), str) or not 5 <= len(body['reason'].strip()) <= 500 or type(body.get('expected_revision')) is not int:
            raise HTTPException(422, 'Explicit decision, reason and revision required')
        digest = hashlib.sha256(_canonical(body).encode()).hexdigest()
        def commit(session):
            active = db.reviewers.update_one({'_id': reviewer['_id'], 'revoked': False}, {'$inc': {'review_attempts': 1}}, session=session)
            if not active.matched_count:
                raise HTTPException(401, 'Reviewer revoked')
            prior = db.review_events.find_one({'unit': unit, 'review_id': review_id}, session=session)
            if prior:
                if prior['fingerprint'] != digest:
                    raise HTTPException(409, 'Review ID reused')
                return prior['result']
            conflict = db.inbox.find_one({'unit': unit, 'operation_id': operation_id}, session=session)
            if not conflict or conflict['reply']['status'] != 'conflict':
                raise HTTPException(404, 'Conflict not found')
            revision = conflict.get('review_revision', 0)
            if revision != body['expected_revision'] or conflict.get('review_state') == 'rejected':
                raise HTTPException(409, 'Conflict already reviewed or revision changed')
            result = {'unit': unit, 'operation_id': operation_id, 'review_id': review_id,
                      'revision': revision + 1, 'state': 'rejected' if body['decision'] == 'reject' else 'needs_review'}
            db.inbox.update_one({'_id': conflict['_id']}, {'$set': {'review_revision': revision + 1, 'review_state': result['state']}}, session=session)
            db.review_events.insert_one({'unit': unit, 'review_id': review_id, 'operation_id': operation_id,
                'reviewer_id': reviewer['_id'], 'fingerprint': digest, 'decision': body['decision'],
                'reason': body['reason'].strip(), 'created_at': datetime.now(timezone.utc), 'result': result}, session=session)
            return result
        for attempt in range(3):
            try:
                with db.client.start_session() as session:
                    return session.with_transaction(commit, read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'))
            except DuplicateKeyError:
                if attempt == 2:
                    raise HTTPException(503, 'Retry same review ID')

    @app.post('/api/sync/v1/batch')
    def batch(body: dict, authorization: str = Header(default='')):
        device = authenticate(authorization)
        items = body.get('operations')
        if not isinstance(items, list) or not 1 <= len(items) <= 100 or not all(isinstance(i, dict) for i in items):
            raise HTTPException(422, 'Invalid batch')
        return {'results': [apply(device, item) for item in items]}

    return app
