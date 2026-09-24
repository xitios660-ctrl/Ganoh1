import test from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeInbound,
  shouldProcessUpsert,
  claimProcessed,
  handleInboundMessage,
  truncate,
  _resetInFlightForTests,
  INBOUND_LIMITS,
  notifyBackendMedia,
  isAllowedComprovanteMime
} from './inbound.mjs';

function mockProcessed() {
  const records = new Map();
  return {
    records,
    async insertOne(doc) {
      if (records.has(doc._id)) {
        const err = new Error('duplicate');
        err.code = 11000;
        throw err;
      }
      records.set(doc._id, doc);
    }
  };
}

function mockInbound() {
  const records = new Map();
  return {
    records,
    async insertOne(doc) {
      if (records.has(doc.messageId)) {
        const err = new Error('duplicate');
        err.code = 11000;
        throw err;
      }
      records.set(doc.messageId, { ...doc });
    },
    async findOne({ messageId }) {
      return records.get(messageId) || null;
    },
    async updateOne({ messageId }, { $set }) {
      const current = records.get(messageId);
      if (!current) return;
      records.set(messageId, { ...current, ...$set });
    }
  };
}

test('truncate respects max length', () => {
  assert.equal(truncate('abc', 10), 'abc');
  assert.equal(truncate('abcdefghij', 5), 'abcde');
  assert.equal(truncate(null, 5), null);
});

test('shouldProcessUpsert accepts only live notify', () => {
  assert.equal(shouldProcessUpsert('notify'), true);
  assert.equal(shouldProcessUpsert('append'), false);
  assert.equal(shouldProcessUpsert(undefined), false);
});

test('normalizeInbound ignores fromMe, missing id, and status broadcast', () => {
  assert.equal(normalizeInbound({ key: { id: '1', remoteJid: '5511@s.whatsapp.net', fromMe: true }, message: { conversation: 'oi' } }), null);
  assert.equal(normalizeInbound({ key: { remoteJid: '5511@s.whatsapp.net', fromMe: false }, message: { conversation: 'oi' } }), null);
  assert.equal(normalizeInbound({ key: { id: '1', remoteJid: 'status@broadcast', fromMe: false }, message: { conversation: 'x' } }), null);
});

test('normalizeInbound extracts text and media metadata without binary', () => {
  const textEvent = normalizeInbound({
    key: { id: 'abc', remoteJid: '5511999999999@s.whatsapp.net', fromMe: false },
    pushName: 'Cliente',
    messageTimestamp: 1700000000,
    message: { conversation: 'pedido pronto?' }
  });
  assert.equal(textEvent.messageType, 'text');
  assert.equal(textEvent.text, 'pedido pronto?');
  assert.equal(textEvent.hasMedia, false);
  assert.equal(textEvent.isGroup, false);
  assert.equal(textEvent.comprovanteStub, null);

  const long = 'x'.repeat(INBOUND_LIMITS.TEXT_LIMIT + 50);
  const longEvent = normalizeInbound({
    key: { id: 'long', remoteJid: '120363@g.us', participant: '5511@s.whatsapp.net', fromMe: false },
    message: { extendedTextMessage: { text: long } }
  });
  assert.equal(longEvent.text.length, INBOUND_LIMITS.TEXT_LIMIT);
  assert.equal(longEvent.isGroup, true);
  assert.equal(longEvent.participant, '5511@s.whatsapp.net');

  const imageEvent = normalizeInbound({
    key: { id: 'img1', remoteJid: '5511@s.whatsapp.net', fromMe: false },
    message: {
      imageMessage: { mimetype: 'image/jpeg', caption: 'comprovante pix' }
    }
  });
  assert.equal(imageEvent.messageType, 'image');
  assert.equal(imageEvent.hasMedia, true);
  assert.equal(imageEvent.mediaMime, 'image/jpeg');
  assert.equal(imageEvent.mediaCaption, 'comprovante pix');
  assert.deepEqual(imageEvent.comprovanteStub, { awaitingDownload: true, purpose: 'comprovante_candidate' });
  assert.ok(!('url' in imageEvent));
});

test('claimProcessed deduplicates by message id', async () => {
  const processed = mockProcessed();
  assert.equal(await claimProcessed(processed, 'm1', { remoteJid: 'a' }), true);
  assert.equal(await claimProcessed(processed, 'm1', { remoteJid: 'a' }), false);
  assert.equal(processed.records.size, 1);
  assert.ok(processed.records.get('m1').expiresAt instanceof Date);
});

test('handleInboundMessage persists, notifies backend, and skips duplicates / fromMe', async () => {
  _resetInFlightForTests();
  const processed = mockProcessed();
  const inbound = mockInbound();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200 };
  };

  const msg = {
    key: { id: 'msg-42', remoteJid: '5511@s.whatsapp.net', fromMe: false },
    message: { conversation: 'ola' },
    messageTimestamp: 1700000001
  };

  const first = await handleInboundMessage(msg, {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    backendUrl: 'http://127.0.0.1:10000',
    token: 't'.repeat(32),
    upsertType: 'notify'
  });
  assert.equal(first.skipped, false);
  assert.equal(first.notified, true);
  assert.equal(inbound.records.get('msg-42').backendNotified, true);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/api\/whatsapp\/inbound$/);
  assert.equal(calls[0].options.headers['x-whatsapp-token'].length, 32);
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.messageId, 'msg-42');
  assert.equal(body.text, 'ola');
  assert.ok(!JSON.stringify(body).includes('mediaKey'));

  const dup = await handleInboundMessage(msg, {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    backendUrl: 'http://127.0.0.1:10000',
    token: 't'.repeat(32),
    upsertType: 'notify'
  });
  assert.deepEqual(dup, { skipped: true, reason: 'duplicate' });
  assert.equal(calls.length, 1);

  const history = await handleInboundMessage(msg, {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    upsertType: 'append'
  });
  assert.deepEqual(history, { skipped: true, reason: 'upsert_type' });

  const self = await handleInboundMessage({
    key: { id: 'self', remoteJid: '5511@s.whatsapp.net', fromMe: true },
    message: { conversation: 'echo' }
  }, {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    upsertType: 'notify'
  });
  assert.deepEqual(self, { skipped: true, reason: 'ignored' });
});

test('concurrent handleInboundMessage shares one in-flight promise', async () => {
  _resetInFlightForTests();
  const processed = mockProcessed();
  const inbound = mockInbound();
  let releaseNotify;
  const notifyGate = new Promise(resolve => { releaseNotify = resolve; });
  const fetchImpl = async () => {
    await notifyGate;
    return { ok: true, status: 200 };
  };
  const msg = {
    key: { id: 'race-1', remoteJid: '5511@s.whatsapp.net', fromMe: false },
    message: { conversation: 'race' }
  };
  const opts = {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    backendUrl: 'http://127.0.0.1:10000',
    token: 't'.repeat(32),
    upsertType: 'notify'
  };
  const p1 = handleInboundMessage(msg, opts);
  const p2 = handleInboundMessage(msg, opts);
  assert.equal(p1, p2);
  releaseNotify();
  const [a, b] = await Promise.all([p1, p2]);
  assert.equal(a.messageId, 'race-1');
  assert.equal(b.messageId, 'race-1');
  assert.equal(processed.records.size, 1);
});

test('isAllowedComprovanteMime accepts images only', () => {
  assert.equal(isAllowedComprovanteMime('image/jpeg'), true);
  assert.equal(isAllowedComprovanteMime('image/png'), true);
  assert.equal(isAllowedComprovanteMime('image/webp'), true);
  assert.equal(isAllowedComprovanteMime('application/pdf'), false);
});

test('notifyBackendMedia posts size-capped base64 without logging binary', async () => {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200 };
  };
  const buf = Buffer.from('fake-jpeg');
  const result = await notifyBackendMedia('mid-1', buf, 'image/jpeg', {
    fetchImpl,
    backendUrl: 'http://127.0.0.1:10000',
    token: 't'.repeat(32)
  });
  assert.equal(result.ok, true);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/api\/whatsapp\/inbound\/media$/);
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.messageId, 'mid-1');
  assert.equal(body.mediaMime, 'image/jpeg');
  assert.equal(body.mediaBase64, buf.toString('base64'));
  assert.ok(!JSON.stringify(calls[0].options.headers).includes('fake-jpeg'));
});

test('notifyBackendMedia rejects oversized and disallowed mime', async () => {
  const fetchImpl = async () => ({ ok: true, status: 200 });
  const huge = Buffer.alloc(INBOUND_LIMITS.MAX_MEDIA_BYTES + 1, 1);
  const tooBig = await notifyBackendMedia('m', huge, 'image/png', {
    fetchImpl,
    token: 't'.repeat(32)
  });
  assert.equal(tooBig.ok, false);
  assert.equal(tooBig.error, 'media_too_large');

  const bad = await notifyBackendMedia('m', Buffer.from('x'), 'application/pdf', {
    fetchImpl,
    token: 't'.repeat(32)
  });
  assert.equal(bad.ok, false);
  assert.equal(bad.error, 'mime_not_allowed');
});

test('handleInboundMessage uploads media when downloadMediaFn provided', async () => {
  _resetInFlightForTests();
  const processed = mockProcessed();
  const inbound = mockInbound();
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200 };
  };
  const msg = {
    key: { id: 'img-media', remoteJid: '5511@s.whatsapp.net', fromMe: false },
    message: { imageMessage: { mimetype: 'image/jpeg', caption: 'pix' } },
    messageTimestamp: 1700000002
  };
  const out = await handleInboundMessage(msg, {
    processedCollection: processed,
    inboundCollection: inbound,
    fetchImpl,
    backendUrl: 'http://127.0.0.1:10000',
    token: 't'.repeat(32),
    upsertType: 'notify',
    downloadMediaFn: async () => Buffer.from('img-bytes')
  });
  assert.equal(out.skipped, false);
  assert.equal(out.notified, true);
  assert.equal(out.mediaUploaded, true);
  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/api\/whatsapp\/inbound$/);
  assert.match(calls[1].url, /\/api\/whatsapp\/inbound\/media$/);
  assert.equal(inbound.records.get('img-media').mediaUploaded, true);
});
