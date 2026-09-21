import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';
import { BufferJSON, initAuthCreds, proto } from '@whiskeysockets/baileys';

export function codec(secret) {
  if (!secret || secret.length < 32) throw new Error('WHATSAPP_SESSION_KEY must contain at least 32 characters');
  const key = createHash('sha256').update(secret).digest();
  return {
    seal(value) {
      const iv = randomBytes(12);
      const cipher = createCipheriv('aes-256-gcm', key, iv);
      const body = Buffer.concat([cipher.update(JSON.stringify(value, BufferJSON.replacer)), cipher.final()]);
      return Buffer.concat([iv, cipher.getAuthTag(), body]).toString('base64');
    },
    open(value) {
      const bytes = Buffer.from(value, 'base64');
      const cipher = createDecipheriv('aes-256-gcm', key, bytes.subarray(0, 12));
      cipher.setAuthTag(bytes.subarray(12, 28));
      return JSON.parse(Buffer.concat([cipher.update(bytes.subarray(28)), cipher.final()]).toString(), BufferJSON.reviver);
    }
  };
}

export async function mongoAuth(collection, secret) {
  const crypto = codec(secret);
  const read = async id => {
    const record = await collection.findOne({ _id: id });
    return record ? crypto.open(record.payload) : null;
  };
  const write = async (id, value) => {
    if (value == null) return collection.deleteOne({ _id: id });
    await collection.updateOne({ _id: id }, { $set: { payload: crypto.seal(value) } }, { upsert: true });
  };
  const saved = await read('creds');
  const creds = saved || initAuthCreds();
  return {
    registered: Boolean(saved?.registered),
    state: {
      creds,
      keys: {
        async get(type, ids) {
          const entries = await Promise.all(ids.map(async id => {
            let value = await read(`${type}:${id}`);
            if (type === 'app-state-sync-key' && value) value = proto.Message.AppStateSyncKeyData.fromObject(value);
            return [id, value];
          }));
          return Object.fromEntries(entries);
        },
        async set(data) {
          for (const [type, entries] of Object.entries(data)) {
            for (const [id, value] of Object.entries(entries)) await write(`${type}:${id}`, value);
          }
        }
      }
    },
    saveCreds: () => write('creds', creds)
  };
}
