# QA — Front-end Tarefas 4, 5 e 6 + Tarefa 7 (suíte E2E completa)
**Status:** APROVADO (após re-teste; ver seção "Re-teste" no fim)
**Data:** 2026-10-07

> Histórico: a 1ª rodada saiu REPROVADO por QA-F-01 (MÉDIA). Os itens abaixo ficaram como registro, e o resultado atual está na seção "Re-teste".

Escopo:
- **Tarefa 4:** `server.js` (Express, helmet/CSP, proxy `/api`, Chart.js local) e tela de login.
- **Tarefa 5:** layout base (sidebar/gaveta, seletor de mês) e dashboard (cards, 2 doughnuts, listas com %).
- **Tarefa 6:** telas de gastos e rendimentos (`entries.js`).
- **Tarefa 7:** suíte E2E completa: login → lançar gasto/rendimento → ver no dashboard → editar/excluir → logout.

Ambiente: Windows 11, Node 24, Playwright 1.63 (Chromium), Django em `127.0.0.1:8000` (`back/venv`, `NUM_PROXIES=1`, `LOGIN_THROTTLE_RATE=5/min`). O front sobe pelo `webServer` do Playwright na porta 3000.

## Testes executados

| Comando | Resultado |
|---|---|
| `npm run lint` | OK (0 erros, incluindo os testes novos) |
| `npm run format:check` | OK ("All matched files use Prettier code style!") |
| `npm test` (`node:test` + supertest) | **18/18 passaram** |
| `npx playwright test` (3 projetos: 1440/768/360) | **91 passaram, 1 falhou (QA-F-01), 6 pulados de propósito** |

Os 6 pulados são os testes de login pela interface fora do desktop (2 em `auth.spec.js` e 1 em `smoke.spec.js`, nos projetos 768 e 360). Eles rodam só no desktop por causa do throttle; veja a seção "Throttle de login" abaixo.

### Arquivos de teste criados ou alterados (só testes e config de teste)

| Arquivo | O que faz |
|---|---|
| `front/tests/e2e/helpers.js` (novo) | Credenciais, `apiClient` (cookies + `X-CSRFToken`), formatação esperada (`brl`/`pct`), limpeza por TAG `QA-E2E`, verificação de scroll horizontal |
| `front/tests/e2e/auth.setup.js` (novo) | **1 login por execução**, via API, salvo em `test-results/.auth/user.json` (storageState). Se receber 429, espera o `Retry-After` e tenta mais uma vez |
| `front/tests/e2e/auth.teardown.js` (novo) | Ao final, apaga os lançamentos `QA-E2E` que sobraram (mês atual, mês anterior e 2001-02), faz logout da sessão compartilhada e apaga o storageState |
| `front/tests/e2e/auth.spec.js` (novo) | Login, redirecionamentos, logout, mensagens de 429/502, sessão expirada x falha de CSRF, POST sem CSRF |
| `front/tests/e2e/entries.spec.js` (novo) | Fluxo completo de gasto e rendimento, erro 400 inline, lançamento em outro mês |
| `front/tests/e2e/dashboard.spec.js` (novo) | % exatos num mês controlado, seletor de mês, estado vazio, XSS |
| `front/tests/e2e/layout.spec.js` (novo) | Responsividade, sidebar/gaveta, teclado/foco, tema escuro, CSP, 404 |
| `front/playwright.config.js` | Projetos `setup` (dependência dos 3 viewports) e `teardown` adicionados |
| `front/tests/e2e/smoke.spec.js` | O teste "login → dashboard → logout" agora roda só no `desktop-1440` (throttle) |

### Cobertura funcional (passou nos 3 viewports, salvo indicação)

- **Login (T4)**
  - Validação inline (e-mail inválido, campos vazios) sem chamar a API, com `aria-invalid` e foco no 1º campo inválido.
  - Credenciais erradas → "E-mail ou senha inválidos.", senha limpa e foco na senha. *(só desktop)*
  - Login válido → dashboard; com sessão ativa, abrir `/index.html` volta ao dashboard. *(só desktop)*
  - Cookie `sessionid` com `HttpOnly` e `SameSite=Lax`; `localStorage` e `sessionStorage` vazios.
  - Respostas 429 e 502 simuladas (`page.route`) → mensagens amigáveis e o botão volta a ficar habilitado.
- **Páginas protegidas:** `/dashboard.html`, `/gastos.html` e `/rendimentos.html` sem sessão → `index.html`. `/api/auth/me/`, `/api/expenses/` e `/api/dashboard/summary/` → 401/403.
- **Logout:** volta ao login; depois dele, `/api/auth/me/` → 403, o dashboard redireciona e "Voltar" não reabre a área logada. *(só desktop)*
- **Sessão expirada x CSRF**
  - Um 403 de sessão ao salvar redireciona para o login.
  - Um 403 "CSRF Failed" mostra o toast "Recarregue a página" e **não** desloga.
  - Um POST real sem `X-CSRFToken` recebe 403.
- **Gastos/rendimentos (T6)**
  - Data padrão = hoje.
  - As opções do `select` são **exatamente** as de `/api/categories/`, nada fixo no código.
  - Validação client-side funciona (categoria, valor "abc", valor 0).
  - Criação com "1.234,56" → linha com "R$ 1.234,56" e descrição com `& "aspas" 'simples' Ção` exibida literalmente.
  - Edição (categoria e valor) → "Gasto atualizado." e a linha é atualizada.
  - Exclusão: "Cancelar" (foco inicial no Cancelar) e Escape mantêm a linha; "Excluir" remove na tela e no back.
  - Erro 400 do back (descrição com `<b>`) aparece inline no campo.
  - Lançamento em outro mês → toast "… adicionado em <mês>", o seletor e a `?month=` mudam para aquele mês.
- **Dashboard (T5)**
  - No mês atual, cards, listas (rótulo, valor, %) e gráficos (labels, dados, cores das fatias = cores dos marcadores) batem com `GET /api/dashboard/summary/`, e a soma dos % fica em 100 ± 0,01.
  - Mês controlado `2001-02` (300/100/100 e 100000/1):
    - Listas: `60,00% / 20,00% / 20,00%` e `100,00% / < 0,01%`.
    - Cards: R$ 500,00 / R$ 100.001,00 / R$ 99.501,00 (`is-positive`).
    - Paletas de gastos e ganhos sem cor em comum.
  - Estado vazio ("Nenhum gasto registrado neste mês.") aparece corretamente.
  - Anterior/próximo atualizam a URL, os dados e os links do menu (`?month=`). Uma `?month=2026-13` inválida cai no mês atual.
- **XSS:** um payload `<img onerror>`/`<script>`/`&amp;` no nome do usuário, nos rótulos do summary e em descrição/categoria da tabela (respostas simuladas) aparece como texto. Nenhum `img`/`script` é criado e `window.__xss` continua indefinido.
- **Responsividade**
  - Sem scroll horizontal em login, dashboard, gastos, rendimentos e 404, em 360, 768 e 1440.
  - Gráficos lado a lado em 1440 e empilhados em 768 e 360 (< 900px).
  - Sidebar fixa em ≥ 768px. Em 360 vira gaveta: botão com `aria-expanded`, Escape fecha e devolve o foco ao botão, clique no fundo fecha e a navegação pela gaveta funciona.
  - Capturas conferidas visualmente em 360, 768 e 1440.
- **Teclado/foco**
  - O skip link é o 1º Tab e leva a `#main`.
  - O foco é visível (outline) nos campos e nos links do menu.
  - Todo input tem `label`.
  - O formulário envia com Enter.
  - No login, a ordem de Tab é e-mail → senha → Entrar.
- **Tema escuro:** `--bg` é `#0f1115`, o `body` tem `rgb(15,17,21)` e texto `rgb(230,232,238)`, e há `meta color-scheme=dark` em todas as páginas.
- **CSP:** nenhum erro de CSP, `pageerror` ou erro de console em nenhuma página/fluxo (exceto os 401/403 esperados de `/api/auth/me/` sem sessão).

### Revisão de código (estática)

| Item | Resultado |
|---|---|
| `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write`/`eval` em `public/js` | Nenhum. O ESLint também bloqueia `innerHTML`/`outerHTML` |
| `localStorage`/`sessionStorage` | Nenhum uso |
| `fetch` fora de `api.js` | Nenhum (`api.js:118` é o único) |
| Cores fora de `variables.css` | Nenhuma no CSS (só `var(--…)` e `color-mix` com variáveis). A paleta das fatias fica só em `ui.js` (`PALETTE`), como pede o CLAUDE.md. Os marcadores usam `style.backgroundColor` via CSSOM, o que é permitido pela CSP |
| Categorias fixas no código | Nenhuma (`gasolina`, `salario_fixo` etc. não aparecem em `public/`) |
| Scripts/estilos inline e CDN | Nenhum (o teste do servidor já cobre) |

### Throttle de login (5/min por IP) x E2E

- **Como a suíte se organiza:** são **4 logins por execução** (setup via API + login inválido + login válido/logout + smoke, todos só no desktop). Os demais testes reaproveitam a sessão salva (storageState). O teardown faz logout dessa sessão.
- **Limitação:** rodar a suíte **duas vezes em menos de 60s** estoura o limite. O setup se recupera sozinho (espera o `Retry-After`), mas os testes de login pela interface falham com "Muitas tentativas". Isso foi reproduzido e não é bug: é o throttle funcionando.
- **Proposta, sem afrouxar a produção:** o back já lê `LOGIN_THROTTLE_RATE` do `.env`. Para quem roda E2E com frequência, use um `back/.env` **local de teste** com `LOGIN_THROTTLE_RATE=30/min` (ou espere 60s entre execuções). O `.env.example` e a produção continuam com `5/min`. Não é preciso mudar código.

## Ajustes para @backend-dev

Nenhum.

## Ajustes para @frontend-dev

- [x] **[MÉDIA] QA-F-01 — Gaveta do menu (< 768px) não move o foco para o menu ao abrir e deixa o Tab "vazar" para trás do fundo escurecido.**
  - **Passos:** viewport de 360px, logado em `/dashboard.html`. Tab até "Abrir menu" e Enter.
  - **Esperado:** foco no 1º link ("Dashboard"), como `setOpen()` pretende (`sidebar.querySelector('a, button')?.focus()`), e o Tab circulando pelo menu enquanto ele estiver aberto.
  - **Obtido:** o foco continua em `#menu-toggle`. O próximo Tab vai para `#month-prev`, um controle **atrás** do backdrop. O menu só é alcançado com Shift+Tab, o que não é óbvio para quem usa teclado ou zoom alto (WCAG 2.4.3).
  - **Causa provável:** `focus()` é chamado no mesmo frame em que `.is-open` é adicionada. Nesse momento a sidebar ainda está `visibility: hidden` (por causa de `transition: … visibility 0.2s`) e o navegador ignora o foco.
  - **Sugestão:**
    - (a) No estado aberto, usar `transition: transform .2s ease, visibility 0s` (visível imediatamente ao abrir, com o atraso só ao fechar), **ou** focar no `transitionend`/`requestAnimationFrame` duplo.
    - (b) Deixar `.app-main` com `inert` enquanto a gaveta estiver aberta, para o Tab ficar no menu.
  - **Arquivos:** `front/public/js/layout.js:20` (`setOpen`) e `front/public/css/layout.css:256-271`.
  - **Teste:** `tests/e2e/layout.spec.js` › "sidebar … (teclado e Escape)" [mobile-360], hoje como `expect.soft` falhando.
- [x] **[BAIXA] QA-F-02 — No layout de cartões da tabela (≤ 600px de container), o rótulo "Descrição" quebra no meio da palavra ("Des/criç/ão" em 360px, "Descri/ção" em 768px).**
  - **Causa:** `.cell-description { overflow-wrap: anywhere }` é herdado pelo `td::before`.
  - **Sugestão:** em `.data-table td::before`, adicionar `flex-shrink: 0; overflow-wrap: normal;` (`front/public/css/components.css:341`).
- [x] **[BAIXA] QA-F-03 — Quando a lista do mês fica vazia (por exemplo, depois de excluir o último lançamento), `renderTable()` só oculta a tabela e não limpa `#entries-body`. As linhas antigas continuam no DOM, ocultas.**
  - Não há efeito visível nem para leitores de tela (a tabela está `hidden`), mas o estado fica inconsistente e pode confundir testes e manutenção.
  - **Sugestão:** `byId('entries-body').replaceChildren()` no ramo vazio (`front/public/js/entries.js`, `renderTable`).

## Observações / melhorias sugeridas

- **Limpeza:** o banco terminou com 0 gastos e 0 rendimentos. Ficaram 14 linhas em `django_session` de execuções anteriores ao teardown; são inofensivas e expiram sozinhas. Os servidores que o QA subiu foram encerrados.
- **Cores:** o card "Excluir" (`btn-ghost`) na tabela tem destaque visual baixo em relação ao "Editar". É aceitável, mas vale conferir o contraste do texto `--text-muted` sobre `--surface-2` no hover.
- **Mês e data padrão:** com o seletor num mês passado (ex.: 2001-02), a data padrão do formulário continua "hoje", como pede o CLAUDE.md. O toast avisa quando o lançamento cai em outro mês, então o comportamento está correto.
- **DoD:** testes do front (`npm test`) ok; lint/format ok; nenhum segredo no código (credenciais E2E só em `front/.env`, não versionado); responsividade em 360/768/1440 ok. O isolamento A/B já foi coberto no back (Tarefa 2). **Pendente:** QA-F-01.
- **Re-teste:** quando QA-F-01 for corrigido, trocar `expect.soft` por `expect` em `layout.spec.js` (linha da asserção "Foco vai para o primeiro link do menu") e rodar `npx playwright test layout.spec.js --project=mobile-360`.

---

## Re-teste (2026-10-07)

**Status do re-teste:** APROVADO. Os 3 itens foram corrigidos e verificados. Não há itens ALTA ou MÉDIA abertos.

### Testes executados

| Comando | Resultado |
|---|---|
| `npm run lint` | OK (0 erros) |
| `npm run format:check` | OK |
| `npm test` | **18/18 passaram** |
| `npx playwright test regressions.spec.js` (1440/768/360) | OK |
| `npx playwright test` (suíte completa, 1 execução, Django em `127.0.0.1:8000 --noreload`) | **100 passaram, 0 falharam, 10 pulados de propósito** |

Sobre os 10 pulados: 6 são os mesmos da 1ª rodada (login pela interface só no desktop, por causa do throttle). Os outros 4 são do novo `regressions.spec.js`, que pula por viewport: o teste da gaveta só roda em 360, o teste do inert em ≥ 768px só roda em 768/1440 e o teste do F-02 não roda em 1440, porque lá a tabela não vira cartão.

### Verificação por item

- **QA-F-01 (MÉDIA) — corrigido.** Verificado em `mobile-360`:
  - Enter em "Abrir menu" leva o foco para "Dashboard". `.app-main` e `.skip-link` recebem `inert`.
  - 10× Tab e 10× Shift+Tab: o foco fica sempre no menu (ou passa pelo `body`/chrome do navegador) e nunca chega ao conteúdo atrás do fundo. A ordem é Dashboard → Adicionar gastos → Adicionar rendimentos → Sair.
  - Escape fecha o menu, o foco volta para `#menu-toggle` (`aria-expanded=false`), o `inert` sai e o próximo Tab vai para o conteúdo.
  - Clique no fundo: mesmo comportamento.
  - Gaveta aberta e viewport trocado para 1440: o menu fecha, o `inert` sai, o backdrop some e o conteúdo volta a ser clicável.
  - **Desktop/tablet sem regressão:** em `dashboard`, `gastos` e `rendimentos` (768 e 1440), `.app-main` e o skip link nunca ficam `inert`, nem depois de Escape, clique e Tab. O skip link continua sendo o 1º Tab.
  - O `expect` (sem `.soft`) em `layout.spec.js` passa.
- **QA-F-02 (BAIXA) — corrigido.** Em 360 e 768, o `td::before` de "Descrição" tem `overflow-wrap: normal`, `word-break: normal` e `flex-shrink: 0`. A largura do rótulo é maior ou igual à largura que "Descrição" precisa numa linha só. A captura do cartão (descrição longa) mostra o rótulo inteiro e só o valor quebra.
- **QA-F-03 (BAIXA) — corrigido.** Com a API simulada (1 lançamento; o DELETE esvazia a lista), depois de excluir o último lançamento a tabela fica oculta e `#entries-body` termina com 0 nós filhos.

### Arquivos de teste alterados neste re-teste (só testes)

- `front/tests/e2e/regressions.spec.js` (novo): QA-F-01 (foco, ciclo de Tab, inert, Escape/fundo/troca de breakpoint), inert nunca ativo em ≥ 768px, QA-F-02 (estilo e largura do rótulo, com captura) e QA-F-03 (tbody vazio).
- `front/tests/e2e/entries.spec.js`: tirado o comentário desatualizado "tbody antigo permanece no DOM".

### DoD (CLAUDE.md §7), parte do front

- [x] `npm test` e E2E passando
- [x] Lint/format sem erros
- [x] Nenhum segredo no código (credenciais E2E só em `front/.env`)
- [x] Isolamento A/B (coberto no back, Tarefa 2)
- [x] 360/768/1440 ok
- [x] Relatório APROVADO

### Ajustes para @frontend-dev (re-teste)

- [ ] **[BAIXA] QA-F-04 — Com a gaveta aberta, o botão do menu (que fica dentro de `.app-main`) também fica `inert`.**
  - **Consequência:** o rótulo "Fechar menu" e o `aria-expanded=true` nunca chegam a ser alcançáveis.
  - **Como fechar hoje:** Escape, clique no fundo ou escolher um link. Isso basta para teclado, mas quem usa leitor de tela no celular (sem tecla Escape) não tem um controle "Fechar" explícito e focável.
  - **Sugestão:** um botão "Fechar menu" dentro da `.sidebar` (visível só abaixo de 768px), **ou** tirar o `.topbar`/`#menu-toggle` do `inert`.
  - **Arquivos:** `front/public/js/layout.js` (`outside`) e os 3 HTML protegidos.
  - Não bloqueia a aprovação.

### Ambiente ao final

- Django (PID 31336) encerrado por PID.
- Portas 8000 e 3000 livres.
- `finances_expense` e `finances_income` com 0 linhas (0 `QA-E2E`).
