/**
 * Baileys inbound helpers (ETAPA 4).
 * Pure extraction + Mongo-backed dedup/persist/notify — no auto replies here; backend may AI-draft (ETAPA 6). No financial trust.
 */

const TEXT_LIMIT = 4000;
const CAPTION_LIMIT = 1000;
const PUSH_NAME_LIMIT = 120;
const DEDUP_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
const DEFAULT_BACKEND_URL = () => `http://127.0.0.1:${process.env.PORT || '10000'}`;

const inFlight = new Map();

export function truncate(value, max) {
  if (typeof value !== 'string') return null;
  if (value.length <= max) return value;
  return value.slice(0, max);
}

export function shouldProcessUpsert(type) {
  // Live messages only — skip history sync flood on reconnect.
  return type === 'notify';
}

export function messageKeyMeta(message) {
  const key = message?.key || {};
  const messageId = typeof key.id === 'string' && key.id.trim() ? key.id.trim() : null;
  const remoteJid = typeof key.remoteJid === 'string' ? key.remoteJid : null;
  const participant = typeof key.participant === 'string' ? key.participant : null;
  const fromMe = Boolean(key.fromMe);
  return { messageId, remoteJid, participant, fromMe };
}

function detectMessageType(content) {
  if (!content || typeof content !== 'object') return 'unknown';
  if (content.conversation || content.extendedTextMessage) return 'text';
  if (content.imageMessage) return 'image';
  if (content.audioMessage) return 'audio';
  if (content.videoMessage) return 'video';
  if (content.documentMessage) return 'document';
  if (content.stickerMessage) return 'sticker';
  if (content.buttonsResponseMessage || content.listResponseMessage || content.templateButtonReplyMessage) {
    return 'interactive';
  }
  return 'other';
}

function extractText(content) {
  if (!content) return null;
  if (typeof content.conversation === 'string') return content.conversation;
  if (typeof content.extendedTextMessage?.text === 'string') return content.extendedTextMessage.text;
  if (typeof content.imageMessage?.caption === 'string') return content.imageMessage.caption;
  if (typeof content.videoMessage?.caption === 'string') return content.videoMessage.caption;
  if (typeof content.documentMessage?.caption === 'string') return content.documentMessage.caption;
  if (typeof content.buttonsResponseMessage?.selectedDisplayText === 'string') {
    return content.buttonsResponseMessage.selectedDisplayText;
  }
  if (typeof content.listResponseMessage?.title === 'string') return content.listResponseMessage.title;
  return null;
}

function mediaMeta(content, messageType) {
  const mediaTypes = new Set(['image', 'audio', 'video', 'document', 'sticker']);
  if (!mediaTypes.has(messageType)) {
    return { hasMedia: false, mediaMime: null, mediaCaption: null, mediaFileName: null };
  }
  const node =
    content.imageMessage ||
    content.audioMessage ||
    content.videoMessage ||
    content.documentMessage ||
    content.stickerMessage ||
    {};
  return {
    hasMedia: true,
    mediaMime: typeof node.mimetype === 'string' ? node.mimetype.slice(0, 120) : null,
    mediaCaption: truncate(typeof node.caption === 'string' ? node.caption : null, CAPTION_LIMIT),
    mediaFileName: typeof node.fileName === 'string' ? truncate(node.fileName, 200) : null
  };
}

/**
 * Normalize a Baileys WAMessage into a safe inbound record (no binary media, no secrets).
 * Returns null when the message must be ignored (fromMe, missing id, etc.).
 */
export function normalizeInbound(message, { receivedAt = new Date() } = {}) {
  const { messageId, remoteJid, participant, fromMe } = messageKeyMeta(message);
  if (fromMe || !messageId || !remoteJid) return null;
  if (remoteJid === 'status@broadcast') return null;

  const content = message.message || null;
  const messageType = detectMessageType(content);
  const text = truncate(extractText(content), TEXT_LIMIT);
  const media = mediaMeta(content, messageType);
  const isGroup = remoteJid.endsWith('@g.us');
  const ts = Number(message.messageTimestamp);
  const messageTimestamp = Number.isFinite(ts) ? new Date(ts * 1000) : receivedAt;

  return {
    messageId,
    remoteJid,
    participant: isGroup ? participant : null,
    isGroup,
    fromMe: false,
    pushName: truncate(typeof message.pushName === 'string' ? message.pushName : null, PUSH_NAME_LIMIT),
    messageType,
    text,
    hasMedia: media.hasMedia,
    mediaMime: media.mediaMime,
    mediaCaption: media.mediaCaption,
    mediaFileName: media.mediaFileName,
    // Stub for ETAPA 8 comprovante flow — metadata only, never trust content.
    comprovanteStub: media.hasMedia && (messageType === 'image' || messageType === 'document')
      ? { awaitingDownload: true, purpose: 'comprovante_candidate' }
      : null,
    messageTimestamp: messageTimestamp.toISOString(),
    receivedAt: receivedAt.toISOString(),
    provider: 'baileys'
  };
}

/**
 * Atomically claim a message id for processing. Duplicate key => already handled.
 */
export async function claimProcessed(processedCollection, messageId, meta = {}) {
  const now = new Date();
  const expiresAt = new Date(now.getTime() + DEDUP_TTL_MS);
  try {
    await processedCollection.insertOne({
      _id: messageId,
      remoteJid: meta.remoteJid || null,
      claimedAt: now,
      expiresAt
    });
    return true;
  } catch (error) {
    if (error && (error.code === 11000 || error.codeName === 'DuplicateKey')) return false;
    throw error;
  }
}

export async function ensureInboundIndexes(processedCollection, inboundCollection) {
  await processedCollection.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 });
  await inboundCollection.createIndex({ messageId: 1 }, { unique: true });
  await inboundCollection.createIndex({ receivedAt: -1 });
  await inboundCollection.createIndex({ backendNotified: 1, receivedAt: -1 });
}

export async function persistInbound(inboundCollection, event) {
  const doc = {
    ...event,
    backendNotified: false,
    backendStatus: 'pending',
    backendError: null,
    createdAt: new Date()
  };
  try {
    await inboundCollection.insertOne(doc);
    return doc;
  } catch (error) {
    if (error && (error.code === 11000 || error.codeName === 'DuplicateKey')) {
      return inboundCollection.findOne({ messageId: event.messageId });
    }
    throw error;
  }
}

export async function notifyBackend(event, {
  fetchImpl = fetch,
  backendUrl = process.env.BACKEND_INTERNAL_URL || DEFAULT_BACKEND_URL(),
  token = process.env.WHATSAPP_INTERNAL_TOKEN
} = {}) {
  if (!token || token.length < 32) {
    return { ok: false, status: 0, error: 'token_missing' };
  }
  const url = `${String(backendUrl).replace(/\/$/, '')}/api/whatsapp/inbound`;
  try {
    const response = await fetchImpl(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-whatsapp-token': token
      },
      body: JSON.stringify(event)
    });
    if (!response.ok) {
      return { ok: false, status: response.status, error: `http_${response.status}` };
    }
    return { ok: true, status: response.status, error: null };
  } catch (error) {
    return { ok: false, status: 0, error: error?.code || error?.name || 'notify_failed' };
  }
}

/**
 * Full inbound pipeline for one WAMessage. Serializes per messageId to avoid double-replies/loops.
 * No auto-send here — AI replies handled by backend webhook (ETAPA 6+).
 */
export function handleInboundMessage(message, {
  processedCollection,
  inboundCollection,
  fetchImpl,
  backendUrl,
  token,
  upsertType = 'notify'
} = {}) {
  // Non-async so concurrent callers share the same Promise reference (loop/dedup safety).
  if (!shouldProcessUpsert(upsertType)) return Promise.resolve({ skipped: true, reason: 'upsert_type' });

  const event = normalizeInbound(message);
  if (!event) return Promise.resolve({ skipped: true, reason: 'ignored' });

  const existing = inFlight.get(event.messageId);
  if (existing) return existing;

  const work = (async () => {
    try {
      const claimed = await claimProcessed(processedCollection, event.messageId, {
        remoteJid: event.remoteJid
      });
      if (!claimed) return { skipped: true, reason: 'duplicate' };

      const stored = await persistInbound(inboundCollection, event);
      const notify = await notifyBackend(event, { fetchImpl, backendUrl, token });
      const patch = {
        backendNotified: notify.ok,
        backendStatus: notify.ok ? 'ok' : 'error',
        backendError: notify.ok ? null : notify.error,
        backendHttpStatus: notify.status,
        notifiedAt: notify.ok ? new Date() : null
      };
      await inboundCollection.updateOne({ messageId: event.messageId }, { $set: patch });
      return { skipped: false, messageId: event.messageId, notified: notify.ok, stored: Boolean(stored) };
    } finally {
      inFlight.delete(event.messageId);
    }
  })();

  inFlight.set(event.messageId, work);
  return work;
}

/** Test helper — clear in-flight map between unit tests. */
export function _resetInFlightForTests() {
  inFlight.clear();
}

export const INBOUND_LIMITS = { TEXT_LIMIT, CAPTION_LIMIT, PUSH_NAME_LIMIT, DEDUP_TTL_MS };
