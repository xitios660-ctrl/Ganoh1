import {
  getPendingSettlement, prepareSettlement, confirmSettlement,
  discardUnstartedSettlement, blockUnconfirmedSettlement
} from './prazoSettlement';

beforeEach(() => {
  sessionStorage.clear();
  let sequence = 0;
  Object.defineProperty(window, 'crypto', { configurable: true,
    value: { randomUUID: () => `10000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}` } });
});

test('reload reuses the same debt settlement operation', () => {
  const first = prepareSettlement('runner', 'Cliente Teste', 100, 'cash');
  jest.resetModules();
  const reloaded = require('./prazoSettlement');
  expect(reloaded.getPendingSettlement('runner', 'Cliente Teste')).toEqual(first);
  expect(reloaded.prepareSettlement('runner', 'Cliente Teste', 100, 'cash')).toEqual(first);
});

test('pending settlement rejects a changed amount or payment method', () => {
  prepareSettlement('runner', 'Cliente Teste', 100, 'cash');
  expect(() => prepareSettlement('runner', 'Cliente Teste', 101, 'cash')).toThrow(/sem confirmação/);
  expect(() => prepareSettlement('runner', 'Cliente Teste', 100, 'pix')).toThrow(/sem confirmação/);
});

test('confirmation only clears the matching operation', () => {
  const pending = prepareSettlement('runner', 'Cliente Teste', 100, 'cash');
  confirmSettlement('runner', 'Cliente Teste', 'different');
  expect(getPendingSettlement('runner', 'Cliente Teste')).toEqual(pending);
  confirmSettlement('runner', 'Cliente Teste', pending.operation_id);
  expect(getPendingSettlement('runner', 'Cliente Teste')).toBeNull();
});

test('stores and customers have independent operations', () => {
  const runner = prepareSettlement('runner', 'Cliente Teste', 100, 'cash');
  const gym = prepareSettlement('gym-londres', 'Cliente Teste', 100, 'cash');
  const other = prepareSettlement('runner', 'Outra Pessoa', 100, 'cash');
  expect(new Set([runner.operation_id, gym.operation_id, other.operation_id]).size).toBe(3);
});

test('unsafe server response blocks retries while safe pre-write rejection can be discarded', () => {
  const pending = prepareSettlement('runner', 'Cliente Teste', 100, 'cash');
  blockUnconfirmedSettlement('runner', 'Cliente Teste');
  expect(() => prepareSettlement('runner', 'Cliente Teste', 100, 'cash')).toThrow(/servidor/);
  discardUnstartedSettlement('runner', 'Cliente Teste', pending.operation_id);
  expect(getPendingSettlement('runner', 'Cliente Teste')).toBeNull();
});

test('storage failure stops the operation before a financial request', () => {
  const spy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota exceeded'); });
  expect(() => prepareSettlement('runner', 'Cliente Teste', 100, 'cash')).toThrow('Quota exceeded');
  spy.mockRestore();
});
