import { initEntriesPage } from './entries.js';

initEntriesPage({
  endpoint: '/expenses/',
  categoriesKey: 'expenses',
  noun: 'gasto',
  emptyText: 'Nenhum gasto neste mês. Use o formulário para adicionar o primeiro.',
});
