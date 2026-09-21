import test from 'node:test';
import assert from 'node:assert/strict';
import { codec, mongoAuth } from './auth.mjs';

test('encrypted credentials preserve buffers and reject a wrong key or tampering', () => {
  const crypto = codec('a'.repeat(32));
  const payload = { secret: 'private-session', key: Buffer.from([0, 1, 254, 255]) };
  const encrypted = crypto.seal(payload);
  assert.ok(!encrypted.includes(payload.secret));
  assert.deepEqual(crypto.open(encrypted), payload);
  assert.throws(() => codec('b'.repeat(32)).open(encrypted));
  const corrupt = Buffer.from(encrypted, 'base64');
  corrupt[30] ^= 1;
  assert.throws(() => crypto.open(corrupt.toString('base64')));
});

test('Mongo auth survives a process reload and removes obsolete signal keys', async () => {
  const records = new Map();
  const collection = {
    async findOne({ _id }) { return records.get(_id); },
    async updateOne({ _id }, { $set }) { records.set(_id, { _id, ...$set }); },
    async deleteOne({ _id }) { records.delete(_id); }
  };
  const first = await mongoAuth(collection, 'a'.repeat(32));
  assert.equal(first.registered, false);
  first.state.creds.registered = true;
  await first.saveCreds();
  await first.state.keys.set({ session: { peer: { key: Buffer.from([42]) } } });
  const second = await mongoAuth(collection, 'a'.repeat(32));
  assert.equal(second.registered, true);
  assert.deepEqual(await second.state.keys.get('session', ['peer']), { peer: { key: Buffer.from([42]) } });
  await second.state.keys.set({ session: { peer: null } });
  assert.deepEqual(await second.state.keys.get('session', ['peer']), { peer: null });
});
