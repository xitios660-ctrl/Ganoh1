import {parseDesktopCents} from './desktopMoney';
test('money input is exact for centavos and decimal separators', () => {
  expect(parseDesktopCents('10,50')).toBe(1050);
  expect(parseDesktopCents('0.29')).toBe(29);
  expect(parseDesktopCents('1')).toBe(100);
  expect(parseDesktopCents('12,3')).toBe(1230);
});
test('ambiguous negative zero and overly precise money is rejected', () => {
  for (const value of ['1.000,00', '-1', '0', '0,001', 'NaN', '1e3', '', '0.00']) expect(() => parseDesktopCents(value)).toThrow();
});
