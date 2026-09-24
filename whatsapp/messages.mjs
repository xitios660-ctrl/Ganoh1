export function unwrapMessage(message) {
  let current = message || {};
  for (let i = 0; i < 4; i += 1) {
    const nested =
      current.ephemeralMessage?.message ||
      current.viewOnceMessage?.message ||
      current.viewOnceMessageV2?.message ||
      current.viewOnceMessageV2Extension?.message;
    if (!nested) break;
    current = nested;
  }
  return current;
}

function asEpochSeconds(value) {
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim()) return Number(value);
  if (value && typeof value === 'object') {
    if (typeof value.toNumber === 'function') return value.toNumber();
    if (Number.isFinite(value.low)) return value.low;
  }
  return NaN;
}

export function normalizeIncomingMessage(raw) {
  const key = raw?.key || {};
  const chatId = key.remoteJid;
  if (!raw?.message || !key.id || !chatId || key.fromMe || chatId === 'status@broadcast') return null;

  const message = unwrapMessage(raw.message);
  let kind = 'unsupported';
  let text = '';

  let mimeType = '';
  let fileName = '';

  if (typeof message.conversation === 'string') {
    kind = 'text';
    text = message.conversation;
  } else if (typeof message.extendedTextMessage?.text === 'string') {
    kind = 'text';
    text = message.extendedTextMessage.text;
  } else if (message.imageMessage) {
    kind = 'image';
    text = message.imageMessage.caption || '';
    mimeType = message.imageMessage.mimetype || 'image/jpeg';
    fileName = 'comprovante.jpg';
  } else if (message.documentMessage) {
    kind = 'document';
    text = message.documentMessage.caption || message.documentMessage.fileName || '';
    mimeType = message.documentMessage.mimetype || '';
    fileName = message.documentMessage.fileName || 'documento';
  }

  const epoch = asEpochSeconds(raw.messageTimestamp);
  const receivedAt = Number.isFinite(epoch)
    ? new Date(epoch * 1000).toISOString()
    : new Date().toISOString();

  return {
    messageId: key.id,
    chatId,
    sender: key.participant || chatId,
    fromGroup: chatId.endsWith('@g.us'),
    kind,
    text: String(text || '').trim().slice(0, 4000),
    mimeType: String(mimeType || '').slice(0, 120),
    fileName: String(fileName || '').slice(0, 180),
    receivedAt
  };
}
