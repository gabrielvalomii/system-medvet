// Shared page logic for "Adicionar gastos" and "Adicionar rendimentos".
import { api } from './api.js';
import {
  addDays,
  amountToInput,
  formatCurrency,
  formatDate,
  formatMonthLabel,
  parseAmount,
  todayISO,
} from './format.js';
import { initLayout, initMonthPicker } from './layout.js';
import {
  confirmDialog,
  el,
  emptyState,
  errorState,
  loadingState,
  setButtonLoading,
  showToast,
} from './ui.js';

const MIN_DATE = '2000-01-01';
const MAX_FUTURE_DAYS = 365;
const DESCRIPTION_MAX = 255;
const FIELDS = ['category', 'amount', 'date', 'description'];

function byId(id) {
  return document.getElementById(id);
}

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/* ---------- Field errors ---------- */

function setFieldError(field, message) {
  const input = byId(field);
  const error = byId(`${field}-error`);
  error.textContent = message ?? '';
  if (message) input.setAttribute('aria-invalid', 'true');
  else input.removeAttribute('aria-invalid');
}

function clearErrors() {
  FIELDS.forEach((field) => setFieldError(field, ''));
  byId('form-error').textContent = '';
}

function showApiErrors(error) {
  const fieldErrors = error.fieldErrors;
  const known = FIELDS.filter((field) => fieldErrors[field]);
  known.forEach((field) => setFieldError(field, fieldErrors[field]));
  const others = Object.entries(fieldErrors)
    .filter(([field]) => !FIELDS.includes(field))
    .map(([, message]) => message);
  if (known.length === 0 || others.length > 0) {
    byId('form-error').textContent = others.length ? others.join(' ') : error.message;
  }
  byId(known[0] ?? 'category').focus();
}

/* ---------- Client-side validation ---------- */

function validateDate(value) {
  const max = addDays(todayISO(), MAX_FUTURE_DAYS);
  if (!value) return 'Informe a data.';
  if (value < MIN_DATE || value > max) {
    return `Informe uma data entre ${formatDate(MIN_DATE)} e ${formatDate(max)}.`;
  }
  return '';
}

function validateDescription(value) {
  if (value.length > DESCRIPTION_MAX) return `Use no máximo ${DESCRIPTION_MAX} caracteres.`;
  if (/[<>]/.test(value)) return 'A descrição não pode conter os caracteres < ou >.';
  return '';
}

/** Returns the payload or null (and shows inline errors). */
function readForm() {
  const amount = parseAmount(byId('amount').value);
  const values = {
    category: byId('category').value,
    date: byId('date').value,
    description: byId('description').value.trim(),
  };
  const errors = {
    category: values.category ? '' : 'Selecione uma categoria.',
    amount: amount.error ?? '',
    date: validateDate(values.date),
    description: validateDescription(values.description),
  };
  FIELDS.forEach((field) => setFieldError(field, errors[field]));
  const firstInvalid = FIELDS.find((field) => errors[field]);
  if (firstInvalid) {
    byId(firstInvalid).focus();
    return null;
  }
  return { ...values, amount: amount.value };
}

/* ---------- Page controller ---------- */

/**
 * config: { endpoint, categoriesKey, noun, emptyText }
 *   endpoint: '/expenses/' | '/incomes/'
 *   categoriesKey: 'expenses' | 'incomes' (key in /api/categories/)
 *   noun: 'gasto' | 'rendimento'
 */
export async function initEntriesPage(config) {
  const noun = config.noun;
  const state = { entries: [], editingId: null, month: null, latestRequest: 0 };
  let picker = null;

  /* ----- Categories ----- */

  async function loadCategories() {
    const select = byId('category');
    const status = byId('categories-status');
    select.disabled = true;
    select.replaceChildren(
      el('option', { text: 'Carregando categorias...', attrs: { value: '' } }),
    );
    status.replaceChildren();
    try {
      const categories = await api.get('/categories/');
      const options = categories[config.categoriesKey].map((item) =>
        el('option', { text: item.label, attrs: { value: item.value } }),
      );
      select.replaceChildren(
        el('option', { text: 'Selecione uma categoria', attrs: { value: '' } }),
        ...options,
      );
      select.disabled = false;
    } catch (error) {
      select.replaceChildren(
        el('option', { text: 'Categorias indisponíveis', attrs: { value: '' } }),
      );
      status.replaceChildren(errorState(error.message, loadCategories));
    }
  }

  /* ----- Form ----- */

  function setDateLimits() {
    const date = byId('date');
    date.min = MIN_DATE;
    date.max = addDays(todayISO(), MAX_FUTURE_DAYS);
  }

  function resetForm() {
    state.editingId = null;
    byId('entry-form').reset();
    byId('date').value = todayISO();
    clearErrors();
    byId('form-title').textContent = `Novo ${noun}`;
    byId('edit-badge').hidden = true;
    byId('cancel-edit').hidden = true;
    byId('submit-button').textContent = `Adicionar ${noun}`;
    byId('form-panel').classList.remove('is-editing');
    highlightEditingRow();
  }

  function startEdit(entry) {
    state.editingId = entry.id;
    clearErrors();
    byId('category').value = entry.category;
    byId('amount').value = amountToInput(entry.amount);
    byId('date').value = entry.date;
    byId('description').value = entry.description ?? '';
    byId('form-title').textContent = `Editar ${noun}`;
    byId('edit-badge').hidden = false;
    byId('cancel-edit').hidden = false;
    byId('submit-button').textContent = 'Salvar alterações';
    byId('form-panel').classList.add('is-editing');
    highlightEditingRow();
    byId('form-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    byId('amount').focus({ preventScroll: true });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    byId('form-error').textContent = '';
    const payload = readForm();
    if (!payload) return;

    const editing = state.editingId !== null;
    const button = byId('submit-button');
    const restore = setButtonLoading(button, 'Salvando...');
    try {
      const saved = editing
        ? await api.put(`${config.endpoint}${state.editingId}/`, payload)
        : await api.post(config.endpoint, payload);
      restore();
      afterSave(saved, editing);
    } catch (error) {
      restore();
      if (error.status === 400) showApiErrors(error);
      else if (error.status === 404) handleMissing();
      else showToast(error.message, 'error');
    }
  }

  function afterSave(saved, editing) {
    const savedMonth = saved.date.slice(0, 7);
    const verb = editing ? 'atualizado' : 'adicionado';
    const where = savedMonth === state.month ? '' : ` em ${formatMonthLabel(savedMonth)}`;
    showToast(`${capitalize(noun)} ${verb}${where}.`, 'success');
    resetForm();
    if (savedMonth !== state.month) picker.set(savedMonth);
    else loadEntries(state.month);
    byId('category').focus();
  }

  function handleMissing() {
    showToast(`${capitalize(noun)} não encontrado. A lista foi atualizada.`, 'error');
    resetForm();
    loadEntries(state.month);
  }

  /* ----- Delete ----- */

  async function handleDelete(entry) {
    const confirmed = await confirmDialog({
      title: `Excluir ${noun}?`,
      message: `${entry.category_label} — ${formatCurrency(entry.amount)} em ${formatDate(entry.date)}. Esta ação não pode ser desfeita.`,
      confirmText: 'Excluir',
      danger: true,
    });
    if (!confirmed) return;
    try {
      await api.delete(`${config.endpoint}${entry.id}/`);
      showToast(`${capitalize(noun)} excluído.`, 'success');
      if (state.editingId === entry.id) resetForm();
      loadEntries(state.month);
    } catch (error) {
      if (error.status === 404) handleMissing();
      else showToast(error.message, 'error');
    }
  }

  /* ----- Table ----- */

  function highlightEditingRow() {
    document.querySelectorAll('#entries-body tr').forEach((row) => {
      row.classList.toggle('is-editing', Number(row.dataset.id) === state.editingId);
    });
  }

  function actionButton(text, label, className, onClick) {
    const button = el('button', {
      className: `btn btn-sm ${className}`,
      text,
      attrs: { type: 'button', 'aria-label': label },
    });
    button.addEventListener('click', onClick);
    return button;
  }

  function renderRow(entry) {
    const summary = `${noun} de ${formatCurrency(entry.amount)} (${entry.category_label}) em ${formatDate(entry.date)}`;
    const cell = (label, text, className) =>
      el('td', { className, text, attrs: { 'data-label': label } });
    const row = el('tr', { attrs: { 'data-id': entry.id } }, [
      cell('Data', formatDate(entry.date)),
      cell('Categoria', entry.category_label),
      cell('Descrição', entry.description || '—', 'cell-description'),
      cell('Valor', formatCurrency(entry.amount), 'num'),
      el('td', { className: 'actions' }, [
        actionButton('Editar', `Editar ${summary}`, 'btn-secondary', () => startEdit(entry)),
        actionButton('Excluir', `Excluir ${summary}`, 'btn-ghost', () => handleDelete(entry)),
      ]),
    ]);
    return row;
  }

  function sumCents(entries) {
    return entries.reduce((total, entry) => total + Math.round(Number(entry.amount) * 100), 0);
  }

  function sortEntries(entries) {
    return [...entries].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);
  }

  function showListState(node) {
    byId('entries-table').hidden = true;
    byId('entries-state').replaceChildren(node);
  }

  function renderTable() {
    if (state.entries.length === 0) {
      showListState(emptyState(config.emptyText));
      byId('entries-body').replaceChildren();
      byId('entries-count').textContent = '';
      return;
    }
    byId('entries-state').replaceChildren();
    byId('entries-body').replaceChildren(...sortEntries(state.entries).map(renderRow));
    byId('entries-total').textContent = formatCurrency(sumCents(state.entries) / 100);
    const count = state.entries.length;
    byId('entries-count').textContent = `${count} ${count === 1 ? 'lançamento' : 'lançamentos'}`;
    byId('entries-table').hidden = false;
    highlightEditingRow();
  }

  async function loadEntries(month) {
    state.month = month;
    const requestId = ++state.latestRequest;
    byId('period-label').textContent = formatMonthLabel(month);
    byId('entries-count').textContent = '';
    showListState(loadingState());
    try {
      const entries = await api.get(config.endpoint, { month });
      if (requestId !== state.latestRequest) return;
      state.entries = entries;
      renderTable();
    } catch (error) {
      if (requestId !== state.latestRequest) return;
      showListState(errorState(error.message, () => loadEntries(month)));
    }
  }

  /* ----- Boot ----- */

  byId('entry-form').addEventListener('submit', handleSubmit);
  byId('cancel-edit').addEventListener('click', () => {
    resetForm();
    byId('category').focus();
  });
  setDateLimits();
  resetForm();

  await initLayout();
  picker = initMonthPicker(loadEntries);
  state.month = picker.get();
  await Promise.all([loadCategories(), loadEntries(state.month)]);
}
