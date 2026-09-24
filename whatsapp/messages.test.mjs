import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeIncomingMessage, unwrapMessage } from './messages.mjs';

test('normalizes a direct text message', () => {
  const result = normalizeIncomingMessage({
    key: { id: 'm1', remoteJid: '5511999999999@s.whatsapp.net', fromMe: false },
    messageTimestamp: 1_700_000_000,
    message: { conversation: 'Quanto vendeu hoje?' }
  });
  assert.equal(result.messageId, 'm1');
  assert.equal(result.kind, 'text');
  assert.equal(result.text, 'Quanto vendeu hoje?');
  assert.equal(result.fromGroup, false);
});

test('normalizes a group image caption without exposing binary media', () => {
  const result = normalizeIncomingMessage({
    key: {
      id: 'm2',
      remoteJid: '120000000000000000@g.us',
      participant: '5511888888888@s.whatsapp.net',
      fromMe: false
    },
    message: { imageMessage: { caption: 'Comprovante PIX' } }
  });
  assert.equal(result.kind, 'image');
  assert.equal(result.text, 'Comprovante PIX');
  assert.equal(result.fromGroup, true);
  assert.equal(result.sender, '5511888888888@s.whatsapp.net');
});

test('ignores own messages and status broadcasts', () => {
  assert.equal(normalizeIncomingMessage({
    key: { id: 'self', remoteJid: '5511@s.whatsapp.net', fromMe: true },
    message: { conversation: 'x' }
  }), null);
  assert.equal(normalizeIncomingMessage({
    key: { id: 'status', remoteJid: 'status@broadcast', fromMe: false },
    message: { conversation: 'x' }
  }), null);
});

test('unwraps ephemeral messages', () => {
  const message = unwrapMessage({
    ephemeralMessage: { message: { extendedTextMessage: { text: 'oi' } } }
  });
  assert.equal(message.extendedTextMessage.text, 'oi');
});
