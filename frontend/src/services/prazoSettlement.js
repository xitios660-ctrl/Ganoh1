const key = (store, customerName) =>
  `ganoh_pending_prazo_v1:${store}:${customerName.trim().toLocaleLowerCase('pt-BR')}`;

export const getPendingSettlement = (store, customerName) => {
  const value = sessionStorage.getItem(key(store, customerName));
  return value ? JSON.parse(value) : null;
};

export const prepareSettlement = (store, customerName, amount, paymentMethod) => {
  const pending = getPendingSettlement(store, customerName);
  if (pending) {
    if (pending.unconfirmedServer) {
      throw new Error('O servidor não confirmou a proteção da quitação. Confira com o gestor antes de tentar novamente.');
    }
    if (pending.amount !== amount || pending.payment_method !== paymentMethod) {
      throw new Error('Existe uma quitação sem confirmação para este cliente. Confira com o gestor antes de alterar o valor ou a forma de pagamento.');
    }
    return pending;
  }
  const operation = {
    store,
    customer_name: customerName,
    amount,
    payment_method: paymentMethod,
    operation_id: crypto.randomUUID()
  };
  sessionStorage.setItem(key(store, customerName), JSON.stringify(operation));
  return operation;
};

export const confirmSettlement = (store, customerName, operationId) => {
  if (getPendingSettlement(store, customerName)?.operation_id === operationId) {
    sessionStorage.removeItem(key(store, customerName));
  }
};

export const discardUnstartedSettlement = (store, customerName, operationId) => {
  confirmSettlement(store, customerName, operationId);
};

export const blockUnconfirmedSettlement = (store, customerName) => {
  const pending = getPendingSettlement(store, customerName);
  if (pending) {
    sessionStorage.setItem(key(store, customerName), JSON.stringify({ ...pending, unconfirmedServer: true }));
  }
};
