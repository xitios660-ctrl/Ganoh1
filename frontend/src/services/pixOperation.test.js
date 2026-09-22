import { getPendingPix, preparePix, confirmPix, blockUnconfirmedPix } from './pixOperation';

beforeEach(() => {
  sessionStorage.clear();
  let sequence = 0;
  Object.defineProperty(window, 'crypto', { configurable: true,
    value: { randomUUID: () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}` } });
});

test('lost response and module reload reuse the persisted operation', () => {
  const first = preparePix('runner', 100, 'PIX');
  jest.resetModules();
  const reloaded = require('./pixOperation');
  expect(reloaded.getPendingPix('runner')).toEqual(first);
  expect(reloaded.preparePix('runner', 100, 'PIX')).toEqual(first);
  expect(() => reloaded.preparePix('runner', 101, 'PIX')).toThrow();
});

test('only an acknowledged operation is cleared; a new payment gets a new key', () => {
  const first = preparePix('runner', 100, 'PIX');
  confirmPix('runner', 'different');
  expect(getPendingPix('runner')).toEqual(first);
  confirmPix('runner', first.operation_id);
  expect(getPendingPix('runner')).toBeNull();
  expect(preparePix('runner', 100, 'PIX').operation_id).not.toBe(first.operation_id);
});

test('units have independent pending operations', () => {
  const runner = preparePix('runner', 100, 'PIX');
  const gym = preparePix('gym-londres', 100, 'PIX');
  confirmPix('runner', runner.operation_id);
  expect(getPendingPix('gym-londres')).toEqual(gym);
});

test('an old server cannot be retried after acknowledging without an operation id', () => {
  preparePix('runner', 100, 'PIX');
  blockUnconfirmedPix('runner');
  expect(() => preparePix('runner', 100, 'PIX')).toThrow(/servidor/);
});

test('storage failure stops preparation before a financial request can be sent', () => {
  const spy = jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Quota exceeded'); });
  expect(() => preparePix('runner', 100, 'PIX')).toThrow('Quota exceeded');
  spy.mockRestore();
});
