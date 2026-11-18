// Parse human-entered money exactly; no floating point multiplication of decimals.
export function parseDesktopCents(value, {allowZero = false} = {}) {
  const match = /^(0|[1-9]\d{0,9})(?:[.,](\d{1,2}))?$/.exec(String(value).trim());
  if (!match) throw new Error('Informe um valor como 10,50, sem separador de milhar.');
  const cents = Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0'));
  if (!Number.isSafeInteger(cents) || (allowZero ? cents < 0 : cents < 1)) throw new Error('O valor deve ser positivo.');
  return cents;
}
