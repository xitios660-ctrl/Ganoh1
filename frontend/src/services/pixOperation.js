// Persist before sending: a lost response or reload must reuse the same operation.
const key = (store) => `ganoh_pending_pix_v1:${store}`;

export const getPendingPix = (store) => {
  const value = sessionStorage.getItem(key(store));
  return value ? JSON.parse(value) : null;
};

export const preparePix = (store, amount, description) => {
  const pending = getPendingPix(store);
  if (pending) {
    if (pending.unconfirmedServer) throw new Error('O servidor não confirmou a proteção contra duplicidade. Confira o histórico com o gestor antes de continuar.');
    if (pending.amount !== amount || pending.description !== description) {
      throw new Error('Existe um PIX sem confirmação. Reabra o formulário e confirme a tentativa anterior antes de lançar outro.');
    }
    return pending;
  }
  const operation = { store, amount, description, operation_id: crypto.randomUUID() };
  // If storage is unavailable, fail before POST instead of risking a duplicate.
  sessionStorage.setItem(key(store), JSON.stringify(operation));
  return operation;
};

export const confirmPix = (store, operationId) => {
  if (getPendingPix(store)?.operation_id === operationId) sessionStorage.removeItem(key(store));
};

export const blockUnconfirmedPix = (store) => {
  const pending = getPendingPix(store);
  if (pending) sessionStorage.setItem(key(store), JSON.stringify({ ...pending, unconfirmedServer: true }));
};
