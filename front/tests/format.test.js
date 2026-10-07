import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  addDays,
  amountToInput,
  currentMonth,
  formatCurrency,
  formatDate,
  formatMonthLabel,
  formatPercent,
  isValidMonth,
  parseAmount,
  shiftMonth,
} from '../public/js/format.js';

// Intl uses a non-breaking space between "R$" and the number.
const normalize = (text) => text.replace(/\s/g, ' ');

test('formatCurrency usa BRL pt-BR e aceita string decimal da API', () => {
  assert.equal(normalize(formatCurrency('1520.50')), 'R$ 1.520,50');
  assert.equal(normalize(formatCurrency('-30.00')), '-R$ 30,00');
  assert.equal(normalize(formatCurrency('0.00')), 'R$ 0,00');
});

test('formatPercent usa o valor da API e mostra "< 0,01%" para fatias minúsculas', () => {
  assert.equal(formatPercent(52.63, '800.00'), '52,63%');
  assert.equal(formatPercent(100, '5000.00'), '100,00%');
  assert.equal(formatPercent(0, '0.01'), '< 0,01%');
  assert.equal(formatPercent(0, '0.00'), '0,00%');
});

test('parseAmount converte formato pt-BR para string decimal com ponto', () => {
  const cases = {
    '12,5': '12.50',
    '1.234,56': '1234.56',
    1234.56: '1234.56',
    '1.500': '1500.00',
    '1.234.567': '1234567.00',
    'R$ 30': '30.00',
    '0,01': '0.01',
    '007,10': '7.10',
    '9999999999,99': '9999999999.99',
  };
  for (const [input, expected] of Object.entries(cases)) {
    assert.deepEqual(parseAmount(input), { value: expected }, input);
  }
});

test('parseAmount rejeita valores inválidos com mensagem em português', () => {
  for (const input of ['', '   ', 'abc', '1,2,3', '-5', '1,234', '12.345,6.7', '1e3']) {
    assert.ok(parseAmount(input).error, `"${input}" deveria ser inválido`);
  }
  assert.equal(parseAmount('0,00').error, 'O valor deve ser maior que zero.');
  assert.equal(parseAmount('12345678901').error, 'Valor muito alto.');
});

test('amountToInput mostra vírgula decimal', () => {
  assert.equal(amountToInput('1234.50'), '1234,50');
});

test('helpers de mês e data', () => {
  assert.equal(currentMonth(new Date(2026, 9, 7)), '2026-10');
  assert.equal(shiftMonth('2026-01', -1), '2025-12');
  assert.equal(shiftMonth('2026-12', 1), '2027-01');
  assert.ok(isValidMonth('2026-10'));
  assert.ok(!isValidMonth('2026-13'));
  assert.ok(!isValidMonth('<script>'));
  assert.equal(formatMonthLabel('2026-10'), 'outubro de 2026');
  assert.equal(formatDate('2026-10-07'), '07/10/2026');
  assert.equal(addDays('2026-10-07', 365), '2027-10-07');
});
