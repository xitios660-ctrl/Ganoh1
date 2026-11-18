import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import DesktopCommercePanel from './DesktopCommercePanel';
global.IS_REACT_ACT_ENVIRONMENT = true;
let root, container, request;
async function input(selector, value) {
  const node = container.querySelector(selector);
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(node), 'value').set;
  await act(async () => {setter.call(node, value); node.dispatchEvent(new Event(node.tagName === 'SELECT' ? 'change' : 'input', {bubbles: true}));});
}
beforeEach(() => {
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  let n = 0;
  Object.defineProperty(global, 'crypto', {configurable: true, value: {randomUUID: () => `fixture-${++n}`}});
  request = jest.fn(async () => ({cash_cents: 1000, revenue_cents: 1500, expense_cents: 500, customers: [], events: []}));
});
afterEach(async () => {await act(async () => root.unmount()); container.remove();});
test('renders provisional cash separately from revenue and expenses', async () => {
  await act(async () => root.render(<DesktopCommercePanel request={request} onChange={jest.fn()} />));
  expect(container.textContent).toContain('Valores provisórios locais');
  expect(container.textContent).toContain('Suprimentos e retiradas não contam como faturamento');
});
test('retains the exact withdrawal request after response loss', async () => {
  await act(async () => root.render(<DesktopCommercePanel request={request} onChange={jest.fn()} />));
  await input('select', 'cash.withdraw');
  const inputs = container.querySelectorAll('input');
  await input('input', '2,50');
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(inputs[1], 'Retirada teste');
    inputs[1].dispatchEvent(new Event('input', {bubbles: true}));
  });
  const sent = [];
  request.mockImplementation(async (_path, options) => {
    if (options?.method === 'POST') {sent.push(options.body); throw new Error('ACK lost');}
    return {cash_cents: 1000, customers: [], events: []};
  });
  for (let i = 0; i < 2; i++) await act(async () => container.querySelector('form').dispatchEvent(new Event('submit', {bubbles: true, cancelable: true})));
  expect(sent).toHaveLength(2); expect(sent[0]).toEqual(sent[1]);
  expect(JSON.parse(sent[0]).data.amount_cents).toBe(250);
});
