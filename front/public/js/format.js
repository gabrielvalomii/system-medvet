// Pure formatting/parsing helpers (no DOM) — unit tested in tests/format.test.js.

const currencyFormatter = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const percentFormatter = new Intl.NumberFormat('pt-BR', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const monthFormatter = new Intl.DateTimeFormat('pt-BR', {
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
});

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
const MAX_INTEGER_DIGITS = 10; // DecimalField(max_digits=12, decimal_places=2)

/** Formats an API decimal string (or number) as BRL, e.g. "1520.5" -> "R$ 1.520,50". */
export function formatCurrency(value) {
  const number = Number(value);
  return currencyFormatter.format(Number.isFinite(number) ? number : 0);
}

/**
 * Formats the percent returned by the API (never recalculated here).
 * A category with money but percent 0 (< 0.005%) is shown as "< 0,01%".
 */
export function formatPercent(percent, total) {
  const value = Number(percent) || 0;
  if (value === 0 && Number(total) > 0) return '< 0,01%';
  return `${percentFormatter.format(value)}%`;
}

function pad(number) {
  return String(number).padStart(2, '0');
}

/** Local date as YYYY-MM-DD (no UTC shift). */
export function toISODate(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function todayISO(now = new Date()) {
  return toISODate(now);
}

export function currentMonth(now = new Date()) {
  return toISODate(now).slice(0, 7);
}

export function isValidMonth(value) {
  return typeof value === 'string' && MONTH_PATTERN.test(value);
}

/** Adds `delta` months to a YYYY-MM string. */
export function shiftMonth(month, delta) {
  const [year, monthIndex] = month.split('-').map(Number);
  const date = new Date(year, monthIndex - 1 + delta, 1);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}`;
}

/** "2026-10" -> "outubro de 2026". */
export function formatMonthLabel(month) {
  const [year, monthIndex] = month.split('-').map(Number);
  return monthFormatter.format(new Date(Date.UTC(year, monthIndex - 1, 1)));
}

/** "2026-10-07" -> "07/10/2026" (string based, no timezone issues). */
export function formatDate(isoDate) {
  const [year, month, day] = String(isoDate).split('-');
  return day && month && year ? `${day}/${month}/${year}` : String(isoDate);
}

/** Adds days to a YYYY-MM-DD string. */
export function addDays(isoDate, days) {
  const [year, month, day] = isoDate.split('-').map(Number);
  return toISODate(new Date(year, month - 1, day + days));
}

// Integer part with optional pt-BR thousands groups: "1234" or "1.234.567".
const GROUPED_INTEGER = String.raw`(?:\d+|\d{1,3}(?:\.\d{3})+)`;
const PT_BR_DECIMAL = new RegExp(`^${GROUPED_INTEGER},\\d{1,2}$`);
const THOUSANDS_ONLY = /^\d{1,3}(?:\.\d{3})+$/;

/** Returns the amount with "." as decimal separator, or the raw text if ambiguous. */
function normalizeSeparators(raw) {
  // pt-BR: "." is the thousands separator and "," the decimal one ("1.234,56").
  if (PT_BR_DECIMAL.test(raw)) return raw.replace(/\./g, '').replace(',', '.');
  if (raw.includes(',')) return raw; // invalid, rejected by the caller
  // "1.500" / "1.234.567" are thousands; "12.50" is a decimal dot.
  if (THOUSANDS_ONLY.test(raw)) return raw.replace(/\./g, '');
  return raw;
}

/**
 * Parses an amount typed in pt-BR ("1.234,56", "12,5", "12.50", "R$ 30")
 * into the API format: a decimal string with a dot and 2 places ("1234.56").
 * Returns { value } on success or { error } with a message in Portuguese.
 */
export function parseAmount(input) {
  const raw = String(input ?? '')
    .replace(/R\$/gi, '')
    .replace(/\s/g, '');
  if (!raw) return { error: 'Informe o valor.' };
  if ((raw.match(/,/g) || []).length > 1)
    return { error: 'Valor inválido. Use o formato 1.234,56.' };

  const normalized = normalizeSeparators(raw);
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(normalized);
  if (!match) return { error: 'Valor inválido. Use o formato 1.234,56.' };

  const integer = match[1].replace(/^0+(?=\d)/, '');
  if (integer.length > MAX_INTEGER_DIGITS) return { error: 'Valor muito alto.' };

  const value = `${integer}.${(match[2] || '').padEnd(2, '0')}`;
  if (/^0+\.00$/.test(value)) return { error: 'O valor deve ser maior que zero.' };
  return { value };
}

/** API decimal string -> value shown in the input ("1234.50" -> "1234,50"). */
export function amountToInput(value) {
  return String(value ?? '').replace('.', ',');
}
