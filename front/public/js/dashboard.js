// Dashboard: summary cards + doughnut charts + category lists.
import { api } from './api.js';
import { formatCurrency, formatMonthLabel, formatPercent } from './format.js';
import { initLayout, initMonthPicker } from './layout.js';
import { colorFor, cssVar, el, emptyState, errorState, loadingState } from './ui.js';

const PANELS = {
  expenses: {
    summaryKey: 'expenses_by_category',
    totalKey: 'total_expenses',
    title: 'Gastos',
    emptyText: 'Nenhum gasto registrado neste mês.',
  },
  incomes: {
    summaryKey: 'incomes_by_category',
    totalKey: 'total_incomes',
    title: 'Ganhos',
    emptyText: 'Nenhum rendimento registrado neste mês.',
  },
};

const charts = {};
let categoryOrder = { expenses: [], incomes: [] };
let latestRequest = 0;

function byId(id) {
  return document.getElementById(id);
}

/* ---------- Summary cards ---------- */

function setCardsLoading() {
  for (const id of ['total-expenses', 'total-incomes', 'balance']) {
    const node = byId(id);
    node.textContent = '—';
    node.classList.remove('is-negative', 'is-positive');
  }
  byId('summary').setAttribute('aria-busy', 'true');
}

function renderCards(summary) {
  byId('total-expenses').textContent = formatCurrency(summary.total_expenses);
  byId('total-incomes').textContent = formatCurrency(summary.total_incomes);
  const balance = byId('balance');
  const value = Number(summary.balance);
  balance.textContent = formatCurrency(summary.balance);
  balance.classList.toggle('is-negative', value < 0);
  balance.classList.toggle('is-positive', value > 0);
  byId('summary').removeAttribute('aria-busy');
}

/* ---------- Category panels ---------- */

function colorOf(kind, category, fallbackIndex) {
  const index = categoryOrder[kind].indexOf(category);
  return colorFor(kind, index >= 0 ? index : fallbackIndex);
}

function showPanelState(kind, stateNode) {
  byId(`${kind}-content`).hidden = true;
  byId(`${kind}-state`).replaceChildren(stateNode);
}

function renderList(kind, items, colors) {
  const rows = items.map((item, index) => {
    const swatch = el('span', { className: 'swatch', attrs: { 'aria-hidden': 'true' } });
    swatch.style.backgroundColor = colors[index];
    return el('li', { className: 'category-item' }, [
      swatch,
      el('span', { className: 'category-name', text: item.label }),
      el('span', { className: 'category-amount', text: formatCurrency(item.total) }),
      el('span', { className: 'category-percent', text: formatPercent(item.percent, item.total) }),
    ]);
  });
  byId(`${kind}-list`).replaceChildren(...rows);
}

function chartDescription(kind, items) {
  const parts = items.map(
    (item) =>
      `${item.label}: ${formatCurrency(item.total)} (${formatPercent(item.percent, item.total)})`,
  );
  return `${PANELS[kind].title} por categoria. ${parts.join('; ')}.`;
}

function renderChart(kind, items, colors) {
  const canvas = byId(`${kind}-chart`);
  canvas.setAttribute('aria-label', chartDescription(kind, items));
  const data = {
    labels: items.map((item) => item.label),
    datasets: [
      {
        data: items.map((item) => Number(item.total)),
        backgroundColor: colors,
        borderColor: cssVar('--surface'),
        borderWidth: 2,
        hoverOffset: 6,
      },
    ],
  };

  if (charts[kind]) {
    charts[kind].$items = items;
    charts[kind].data = data;
    charts[kind].update();
    return;
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const chart = new window.Chart(canvas, {
    type: 'doughnut',
    data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      animation: reduceMotion ? false : { duration: 400 },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => {
              const item = chart.$items[context.dataIndex];
              return ` ${formatCurrency(item.total)} (${formatPercent(item.percent, item.total)})`;
            },
          },
        },
      },
    },
  });
  chart.$items = items;
  charts[kind] = chart;
}

function renderPanel(kind, summary) {
  const items = summary[PANELS[kind].summaryKey] ?? [];
  if (items.length === 0) {
    showPanelState(kind, emptyState(PANELS[kind].emptyText));
    return;
  }
  const colors = items.map((item, index) => colorOf(kind, item.category, index));
  byId(`${kind}-state`).replaceChildren();
  byId(`${kind}-content`).hidden = false;
  byId(`${kind}-chart-total`).textContent = formatCurrency(summary[PANELS[kind].totalKey]);
  renderList(kind, items, colors);
  renderChart(kind, items, colors);
}

/* ---------- Data loading ---------- */

async function loadCategoryOrder() {
  try {
    const categories = await api.get('/categories/');
    categoryOrder = {
      expenses: categories.expenses.map((item) => item.value),
      incomes: categories.incomes.map((item) => item.value),
    };
  } catch {
    // Colors fall back to the list position; the dashboard still works.
  }
}

async function loadSummary(month) {
  const requestId = ++latestRequest;
  byId('period-label').textContent = formatMonthLabel(month);
  setCardsLoading();
  for (const kind of Object.keys(PANELS)) showPanelState(kind, loadingState());

  try {
    const summary = await api.get('/dashboard/summary/', { month });
    if (requestId !== latestRequest) return; // a newer month was selected
    renderCards(summary);
    for (const kind of Object.keys(PANELS)) renderPanel(kind, summary);
    byId('dashboard-status').textContent = `Resumo de ${formatMonthLabel(month)} carregado.`;
  } catch (error) {
    if (requestId !== latestRequest) return;
    byId('summary').removeAttribute('aria-busy');
    const retry = () => loadSummary(month);
    for (const kind of Object.keys(PANELS)) showPanelState(kind, errorState(error.message, retry));
  }
}

async function init() {
  window.Chart.defaults.color = cssVar('--text-muted');
  window.Chart.defaults.font.family = cssVar('--font');
  await initLayout();
  const picker = initMonthPicker(loadSummary);
  await loadCategoryOrder();
  loadSummary(picker.get());
}

init();
