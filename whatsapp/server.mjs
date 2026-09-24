import express from 'express';
import multer from 'multer';
import { MongoClient } from 'mongodb';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import makeWASocket, { DisconnectReason, makeCacheableSignalKeyStore, Browsers, downloadMediaMessage } from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';
import { mongoAuth, codec } from './auth.mjs';
import { normalizeIncomingMessage } from './messages.mjs';

const token = process.env.WHATSAPP_INTERNAL_TOKEN;
if (!token || token.length < 32) throw new Error('WHATSAPP_INTERNAL_TOKEN must contain at least 32 characters');
const mongo = new MongoClient(process.env.MONGO_URL, { serverSelectionTimeoutMS: 10000 });
await mongo.connect();
const db = mongo.db(process.env.DB_NAME);
const authCollection = db.collection('baileys_auth');
const locks = db.collection('baileys_locks');
const inbox = db.collection('whatsapp_inbox');
const mediaPending = db.collection('whatsapp_media_pending');
await inbox.createIndex({ processed: 1, receivedAt: 1 });
await mediaPending.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 });
const mediaCrypto = codec(process.env.WHATSAPP_SESSION_KEY);
const backendPort = process.env.PORT || '10000';
const owner = randomUUID();
const logger = pino({ level: 'silent' }); // Never log QR codes, session keys or customer messages.
let socket, reconnectTimer, leaseTimer, inboxRetryTimer, connecting = false, stopping = false;
let status = 'disconnected', qrCode = null, attempts = 0;
let groupsCache = { until: 0, value: [] };
let writeQueue = Promise.resolve();
const app = express();
const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 10 * 1024 * 1024, files: 1 } });

app.use((req, res, next) => {
  const received = Buffer.from(req.get('x-whatsapp-token') || '');
  const expected = Buffer.from(token);
  if (received.length !== expected.length || !timingSafeEqual(received, expected)) return res.sendStatus(401);
  res.set('Cache-Control', 'no-store');
  next();
});
app.use(express.json({ limit: '1mb' }));

async function backendPayload(record) {
  const payload = {
    messageId: record.messageId || record._id,
    chatId: record.chatId,
    sender: record.sender,
    fromGroup: Boolean(record.fromGroup),
    kind: record.kind || 'unsupported',
    text: record.text || '',
    mimeType: record.mimeType || '',
    fileName: record.fileName || '',
    receivedAt: record.receivedAt instanceof Date ? record.receivedAt.toISOString() : record.receivedAt
  };
  if (record.kind === 'image' || record.kind === 'document') {
    const media = await mediaPending.findOne({ _id: payload.messageId });
    if (media?.payload) {
      const opened = mediaCrypto.open(media.payload);
      payload.mediaBase64 = opened.base64 || '';
      payload.mimeType = opened.mimeType || payload.mimeType;
      payload.fileName = opened.fileName || payload.fileName;
    }
  }
  return payload;
}

async function persistIncomingMedia(raw, normalized, currentSocket) {
  const allowed = new Set(['image/jpeg', 'image/png', 'image/webp', 'application/pdf']);
  if (!allowed.has(normalized.mimeType)) return false;
  const buffer = await downloadMediaMessage(
    raw,
    'buffer',
    {},
    { logger, reuploadRequest: currentSocket.updateMediaMessage }
  );
  if (!Buffer.isBuffer(buffer) || buffer.length === 0 || buffer.length > 8 * 1024 * 1024) return false;
  const encrypted = mediaCrypto.seal({
    mimeType: normalized.mimeType,
    fileName: normalized.fileName,
    base64: buffer.toString('base64')
  });
  await mediaPending.updateOne(
    { _id: normalized.messageId },
    {
      $set: {
        payload: encrypted,
        mimeType: normalized.mimeType,
        fileName: normalized.fileName,
        size: buffer.length,
        createdAt: new Date(),
        expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
      }
    },
    { upsert: true }
  );
  return true;
}

async function deliverIncoming(record) {
  const payload = await backendPayload(record);
  const response = await fetch(`http://127.0.0.1:${backendPort}/api/whatsapp/internal/incoming`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-whatsapp-token': token
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(15000)
  });
  if (!response.ok) throw new Error(`backend_${response.status}`);
  await inbox.updateOne(
    { _id: payload.messageId },
    { $set: { processed: true, processedAt: new Date(), lastError: null } }
  );
}

async function markIncomingFailure(messageId, error) {
  await inbox.updateOne(
    { _id: messageId },
    {
      $inc: { attempts: 1 },
      $set: {
        lastAttemptAt: new Date(),
        lastError: String(error?.message || error?.name || 'delivery_failed').slice(0, 120)
      }
    }
  );
}

async function retryInbox() {
  if (stopping) return;
  const pending = await inbox.find({ processed: { $ne: true } }).sort({ receivedAt: 1 }).limit(20).toArray();
  for (const record of pending) {
    try {
      await deliverIncoming(record);
    } catch (error) {
      await markIncomingFailure(record._id, error);
    }
  }
}

function ensureInboxRetry() {
  if (inboxRetryTimer) return;
  inboxRetryTimer = setInterval(() => {
    retryInbox().catch(() => {});
  }, 10000);
}

async function acquireLease() {
  const now = new Date();
  try {
    const result = await locks.findOneAndUpdate(
      { _id: 'ganoh', $or: [{ owner }, { expiresAt: { $lte: now } }] },
      { $set: { owner, expiresAt: new Date(Date.now() + 60000) } },
      { upsert: true, returnDocument: 'after' }
    );
    return result?.owner === owner;
  } catch (error) {
    if (error.code === 11000) return false;
    throw error;
  }
}

function scheduleReconnect() {
  if (stopping || reconnectTimer) return;
  status = 'reconnecting';
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect().catch(() => scheduleReconnect());
  }, Math.min(60000, 2000 * 2 ** Math.min(attempts++, 5)) + Math.random() * 1000);
}

async function connect() {
  if (stopping || connecting || socket) return;
  connecting = true;
  try {
    if (!await acquireLease()) { scheduleReconnect(); return; }
    if (!leaseTimer) leaseTimer = setInterval(async () => {
      try {
        if (!await acquireLease()) throw new Error('Lease lost');
      } catch {
        // Fail closed: two deploys must not connect the same WhatsApp session.
        await stop(1);
      }
    }, 15000);
    await writeQueue;
    const auth = await mongoAuth(authCollection, process.env.WHATSAPP_SESSION_KEY);
    status = 'connecting';
    const current = makeWASocket({
      auth: { creds: auth.state.creds, keys: makeCacheableSignalKeyStore(auth.state.keys, logger) },
      logger, browser: Browsers.ubuntu('Chrome'), markOnlineOnConnect: false,
      syncFullHistory: false, connectTimeoutMs: 30000, keepAliveIntervalMs: 25000,
      getMessage: async () => undefined
    });
    socket = current;
    current.ev.on('creds.update', () => {
      writeQueue = writeQueue.then(() => auth.saveCreds()).catch(() => { stop(1); });
    });
    current.ev.on('messages.upsert', async event => {
      try {
        for (const raw of event.messages || []) {
          const message = normalizeIncomingMessage(raw);
          if (!message) continue;
          const record = {
            _id: message.messageId,
            ...message,
            receivedAt: new Date(message.receivedAt),
            processed: false,
            attempts: 0,
            mediaPresent: false
          };
          const result = await inbox.updateOne(
            { _id: message.messageId },
            { $setOnInsert: record },
            { upsert: true }
          );
          if (result.upsertedCount === 1) {
            if (message.kind === 'image' || message.kind === 'document') {
              try {
                record.mediaPresent = await persistIncomingMedia(raw, message, current);
                await inbox.updateOne(
                  { _id: message.messageId },
                  { $set: { mediaPresent: record.mediaPresent } }
                );
              } catch (error) {
                await inbox.updateOne(
                  { _id: message.messageId },
                  { $set: { mediaPresent: false, mediaError: String(error?.name || 'download_failed').slice(0, 80) } }
                );
              }
            }
            deliverIncoming(record).catch(error => markIncomingFailure(message.messageId, error));
          }
        }
      } catch (error) {
        console.error('WhatsApp inbound processing failed:', error.code || error.name || 'unknown');
      }
    });
    current.ev.on('connection.update', async update => {
      if (socket !== current || stopping) return;
      if (update.qr) {
        const encoded = (await QRCode.toDataURL(update.qr)).split(',')[1];
        if (socket === current && status !== 'connected') { qrCode = encoded; status = 'waiting_qr'; }
      }
      if (update.connection === 'open') {
        status = 'connected'; qrCode = null; attempts = 0; groupsCache.until = 0; ensureInboxRetry();
      }
      if (update.connection === 'close') {
        socket = null; qrCode = null;
        const code = update.lastDisconnect?.error?.output?.statusCode;
        if (code === DisconnectReason.loggedOut || code === DisconnectReason.badSession) {
          status = 'logged_out';
          await writeQueue;
          await authCollection.deleteMany({}); // Only expired WhatsApp credentials, never business data.
        } else if (code === DisconnectReason.connectionReplaced || code === DisconnectReason.forbidden) {
          status = 'connection_conflict';
        } else {
          scheduleReconnect();
        }
      }
    });
  } finally { connecting = false; }
}

app.get('/getStateInstance', (req, res) => res.json({
  stateInstance: status === 'connected' ? 'authorized' : status,
  provider: 'baileys', sendingEnabled: process.env.WHATSAPP_SEND_ENABLED === 'true'
}));
app.get('/qr', (req, res) => res.json({ message: qrCode, state: status }));
app.post('/connect', async (req, res) => {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  await connect();
  res.json({ success: true, status });
});
app.get('/media/:messageId', async (req, res) => {
  const media = await mediaPending.findOne({ _id: req.params.messageId });
  if (!media?.payload) return res.sendStatus(404);
  const opened = mediaCrypto.open(media.payload);
  res.json({
    mimeType: opened.mimeType || media.mimeType || '',
    fileName: opened.fileName || media.fileName || '',
    data: opened.base64 || ''
  });
});

app.get('/getChats', async (req, res) => {
  if (status !== 'connected') return res.status(409).json({ error: 'WhatsApp desconectado' });
  if (Date.now() > groupsCache.until) {
    const groups = await socket.groupFetchAllParticipating();
    groupsCache = { until: Date.now() + 60000, value: Object.values(groups).map(group => ({
      id: group.id, name: group.subject, participants: group.participants.length
    })) };
  }
  res.json(groupsCache.value);
});
app.post('/getGroupDataByInviteLink', async (req, res) => {
  if (status !== 'connected') return res.status(409).json({ error: 'WhatsApp desconectado' });
  const match = /^https:\/\/chat\.whatsapp\.com\/([A-Za-z0-9_-]+)(?:\?.*)?$/.exec(req.body.inviteLink || '');
  if (!match) return res.status(400).json({ error: 'Link de grupo inválido' });
  const groupJid = await socket.groupAcceptInvite(match[1]);
  groupsCache.until = 0;
  res.json({ groupJid, groupName: 'Grupo WhatsApp' });
});

function canSend(req, res, next) {
  if (process.env.WHATSAPP_SEND_ENABLED !== 'true') return res.status(403).json({ error: 'Envio desativado até concluir a migração' });
  if (status !== 'connected') return res.status(409).json({ error: 'WhatsApp desconectado' });
  next();
}
function validTarget(target) { return typeof target === 'string' && /^\d[\d-]*@(g\.us|s\.whatsapp\.net|c\.us)$/.test(target); }
app.post('/sendMessage', canSend, async (req, res) => {
  const { chatId, message } = req.body;
  if (!validTarget(chatId) || typeof message !== 'string' || !message.trim()) return res.sendStatus(400);
  const sent = await socket.sendMessage(chatId.replace('@c.us', '@s.whatsapp.net'), { text: message });
  res.json({ idMessage: sent.key.id });
});
app.post('/sendFileByUpload', canSend, upload.single('file'), async (req, res) => {
  if (!validTarget(req.body.chatId) || !req.file || !/^image\/(jpeg|png|webp)$/.test(req.file.mimetype)) return res.sendStatus(400);
  const sent = await socket.sendMessage(req.body.chatId.replace('@c.us', '@s.whatsapp.net'), {
    image: req.file.buffer, caption: req.body.caption || '', mimetype: req.file.mimetype
  });
  res.json({ idMessage: sent.key.id });
});
app.use((error, req, res, next) => {
  console.error('WhatsApp operation failed:', error.code || error.name || 'unknown');
  res.status(502).json({ error: 'Falha na operação do WhatsApp; tente novamente após conferir a conexão.' });
});

const httpServer = app.listen(8002, '127.0.0.1');
ensureInboxRetry();
const savedAuth = await mongoAuth(authCollection, process.env.WHATSAPP_SESSION_KEY);
if (savedAuth.registered) connect().catch(() => scheduleReconnect());
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  clearTimeout(reconnectTimer); clearInterval(leaseTimer); clearInterval(inboxRetryTimer);
  socket?.end(new Error('Service stopping'));
  httpServer.close();
  try { await writeQueue; await locks.deleteOne({ _id: 'ganoh', owner }); } finally { await mongo.close(); }
  process.exit(code);
}
process.on('SIGTERM', () => stop());
process.on('SIGINT', () => stop());
