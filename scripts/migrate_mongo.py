"""Copy an entire MongoDB database into a NEW empty database and verify raw BSON.

Requires a read-only SOURCE_MONGO_URL and a writable TARGET_MONGO_URL.
Source writers must be paused during the final copy. Never modifies the source.
No credentials or customer data are printed or written to the repository.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from bson import BSON
from pymongo import MongoClient


def fingerprint(collection):
    digest = hashlib.sha256()
    count = 0
    # Stable _id order; raw BSON retains dates, decimals, binary and numeric types.
    for document in collection.find({}).sort('_id', 1):
        digest.update(BSON.encode(document))
        count += 1
    return {'count': count, 'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Copy only into an empty target')
    parser.add_argument('--source-paused', action='store_true', help='Confirm all source writers are paused')
    args = parser.parse_args()
    required = ('SOURCE_MONGO_URL', 'SOURCE_DB_NAME', 'TARGET_MONGO_URL', 'TARGET_DB_NAME')
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError('Configure all SOURCE_/TARGET_ MongoDB settings in the environment')
    if args.apply and not args.source_paused:
        raise RuntimeError('Final copy requires --source-paused and writers actually paused at the source')
    with MongoClient(os.environ['SOURCE_MONGO_URL'], serverSelectionTimeoutMS=10000) as src_client, \
         MongoClient(os.environ['TARGET_MONGO_URL'], serverSelectionTimeoutMS=10000) as dst_client:
        source = src_client[os.environ['SOURCE_DB_NAME']]
        target = dst_client[os.environ['TARGET_DB_NAME']]
        source.command('ping')
        target.command('ping')
        # Equal database names are refused even across clusters to prevent accidental reuse.
        if source.name == target.name:
            raise RuntimeError('Use a distinct, new target database name')
        info = list(source.list_collections())
        if not info:
            raise RuntimeError('Source has no collections; refusing to report an empty migration as success')
        if any(item.get('type') != 'collection' or item['name'].startswith('system.') for item in info):
            raise RuntimeError('Source has views or special collections; use MongoDB native backup/restore')
        names = sorted(item['name'] for item in info)
        if args.apply and target.list_collection_names():
            raise RuntimeError('Target is not empty. No data was overwritten; use a new database')
        before = {name: fingerprint(source[name]) for name in names}
        if not args.apply:
            print(json.dumps({'mode': 'dry-run', 'collections': before}, indent=2))
            return
        for item in sorted(info, key=lambda item: item['name']):
            name = item['name']
            options = dict(item.get('options', {}))
            # Capped/time-series storage needs a native backup; never silently flatten it.
            if options.get('capped') or options.get('timeseries'):
                raise RuntimeError('Special storage requires MongoDB native backup/restore')
            target.create_collection(name, **options)
            batch = []
            for document in source[name].find({}).sort('_id', 1):
                batch.append(document)
                if len(batch) >= 250:
                    target[name].insert_many(batch, ordered=True)
                    batch = []
            if batch:
                target[name].insert_many(batch, ordered=True)
            # Preserve indexes, including uniqueness and expiry settings.
            for index in source[name].list_indexes():
                if index['name'] == '_id_':
                    continue
                kwargs = {key: value for key, value in index.items() if key not in ('key', 'v', 'ns')}
                target[name].create_index(list(index['key'].items()), **kwargs)
        after_source = {name: fingerprint(source[name]) for name in names}
        after_target = {name: fingerprint(target[name]) for name in names}
        current_names = sorted(source.list_collection_names())
        if before != after_source or before != after_target or current_names != names:
            raise RuntimeError('Verification failed or source changed. Keep destination in maintenance; do not switch traffic')
        print(json.dumps({'mode': 'copied-and-verified', 'verified_at': datetime.now(timezone.utc).isoformat(),
                          'collections': after_target}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Database exceptions may contain connection strings; omit their details.
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        else:
            print(f'Migration stopped ({type(error).__name__}). Destination remains unverified.', file=sys.stderr)
        sys.exit(1)
