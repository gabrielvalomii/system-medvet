import { initEntriesPage } from './entries.js';

initEntriesPage({
  endpoint: '/incomes/',
  categoriesKey: 'incomes',
  noun: 'rendimento',
  emptyText: 'Nenhum rendimento neste mês. Use o formulário para adicionar o primeiro.',
});
