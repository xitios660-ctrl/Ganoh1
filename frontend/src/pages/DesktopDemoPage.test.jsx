import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import DesktopDemoPage from './DesktopDemoPage';

global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container;
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container);
  root = createRoot(container);
  Object.defineProperty(global, 'crypto', {configurable: true, value: {randomUUID: jest.fn().mockReturnValueOnce('operation-uuid').mockReturnValueOnce('sale-uuid')}});
  global.fetch = jest.fn(async url => ({ok: true, json: async () => url.endsWith('status') ? {unit: 'runner', pending: 2, conflicts: 1, connection: 'offline'} : url.endsWith('catalog') ? {items: [{sku: 'lanche', price_cents: 1000}]} : {items: []}}));
});
afterEach(async () => {await act(async () => root.unmount()); container.remove();});
it('shows unit, offline pending and conflict counts without claiming remote totals', async () => {
  await act(async () => root.render(<DesktopDemoPage />));
  expect(container.textContent).toContain('RUNNER');
  expect(container.textContent).toContain('Pendentes: 2');
  expect(container.textContent).toContain('Conflitos: 1');
  expect(container.textContent).toContain('ainda não fazem parte dos relatórios remotos');
});
it('reuses the exact sale request after a lost local response', async () => {
  await act(async () => root.render(<DesktopDemoPage />));
  const select = container.querySelector('select[aria-label="Produto da venda"]');
  await act(async () => {select.value = 'lanche'; select.dispatchEvent(new Event('change', {bubbles: true}));});
  const original = global.fetch.getMockImplementation();
  const requests = [];
  global.fetch.mockImplementation(async (url, options) => {
    if (url.endsWith('/sales') && options?.method === 'POST') {requests.push(options.body); throw new Error('ACK lost');}
    return original(url, options);
  });
  const form = Array.from(container.querySelectorAll('button')).find(b => b.textContent.includes('Salvar venda em dinheiro')).closest('form');
  await act(async () => form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
  await act(async () => form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
  expect(requests).toHaveLength(2);
  expect(requests[0]).toEqual(requests[1]);
  expect(JSON.parse(requests[0]).operation_id).toBe('operation-uuid');
});
