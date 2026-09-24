import express from 'express';
import multer from 'multer';
import { MongoClient } from 'mongodb';
import { randomUUID, timingSafeEqual } from 'node:crypto';
import makeWASocket, { DisconnectReason, makeCacheableSignalKeyStore, Browsers } from '@whiskeysockets/baileys';
import QRCode from 'qrcode';
import pino from 'pino';
import { mongoAuth } from './auth.mjs';
import { ensureInboundIndexes, handleInboundMessage } from './inbound.mjs';

const token = process.env.WHATSAPP_INTERNAL_TOKEN;
if (!token || token.length < 32) throw new Error('WHATSAPP_INTERNAL_TOKEN must contain at least 32 characters');
const mongo = new MongoClient(process.env.MONGO_URL, { serverSelectionTimeoutMS: 10000 });
await mongo.connect();
const db = mongo.db(process.env.DB_NAME);
const authCollection = db.collection('baileys_auth');
const locks = db.collection('baileys_locks');
const processedMessages = db.collection('baileys_processed_messages');
const inboundCollection = db.collection('baileys_inbound');
const owner = randomUUID();
const logger = pino({ level: 'silent' }); // Never log QR codes, session keys or customer messages.
let socket, reconnectTimer, leaseTimer, connecting = false, stopping = false;
let status = 'disconnected', qrCode = null, attempts = 0;
let groupsCache = { until: 0, value: [] };
let writeQueue = Promise.resolve();
let indexesReady = Promise.resolve();
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

function attachInboundHandler(current) {
  current.ev.on('messages.upsert', ({ type, messages }) => {
    if (socket !== current || stopping || !Array.isArray(messages)) return;
    for (const message of messages) {
      handleInboundMessage(message, {
        processedCollection: processedMessages,
        inboundCollection,
        token,
        upsertType: type
      }).catch(error => {
        // Safe codes/names only — never log QR, credentials, or message bodies.
        console.error('Inbound handling failed:', error?.code || error?.name || 'unknown');
      });
    }
  });
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
    await indexesReady;
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
    attachInboundHandler(current);
    current.ev.on('connection.update', async update => {
      if (socket !== current || stopping) return;
      if (update.qr) {
        const encoded = (await QRCode.toDataURL(update.qr)).split(',')[1];
        if (socket === current && status !== 'connected') { qrCode = encoded; status = 'waiting_qr'; }
      }
      if (update.connection === 'open') {
        status = 'connected'; qrCode = null; attempts = 0; groupsCache.until = 0;
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

// Token-protected peek for gestor tooling (ETAPA 5+). Never returns secrets.
app.get('/inbound/recent', async (req, res) => {
  const limit = Math.min(100, Math.max(1, Number(req.query.limit) || 20));
  const rows = await inboundCollection
    .find({}, {
      projection: {
        _id: 0,
        messageId: 1,
        remoteJid: 1,
        participant: 1,
        isGroup: 1,
        messageType: 1,
        hasMedia: 1,
        mediaMime: 1,
        pushName: 1,
        messageTimestamp: 1,
        receivedAt: 1,
        backendNotified: 1,
        backendStatus: 1,
        // Intentionally omit text/mediaCaption bodies from list peek.
        comprovanteStub: 1
      }
    })
    .sort({ receivedAt: -1 })
    .limit(limit)
    .toArray();
  res.json({ count: rows.length, items: rows });
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

indexesReady = ensureInboundIndexes(processedMessages, inboundCollection).catch(error => {
  console.error('Inbound index setup failed:', error?.code || error?.name || 'unknown');
});

const httpServer = app.listen(8002, '127.0.0.1');
const savedAuth = await mongoAuth(authCollection, process.env.WHATSAPP_SESSION_KEY);
if (savedAuth.registered) connect().catch(() => scheduleReconnect());
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  clearTimeout(reconnectTimer); clearInterval(leaseTimer);
  socket?.end(new Error('Service stopping'));
  httpServer.close();
  try { await writeQueue; await locks.deleteOne({ _id: 'ganoh', owner }); } finally { await mongo.close(); }
  process.exit(code);
}
process.on('SIGTERM', () => stop());
process.on('SIGINT', () => stop());
