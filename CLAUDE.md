# CLAUDE.md — Projeto Financeiro Pessoal

> Guia mestre do projeto. Todo agente (humano ou IA) deve ler este arquivo **antes** de escrever qualquer linha de código.
> Postura esperada: engenheiro(a) full stack sênior — código simples, seguro, testado e fácil de manter.

---

## 1. Visão geral

Aplicação web de controle financeiro pessoal com:

1. **Tela de login** (e-mail + senha). O acesso só é liberado quando as credenciais batem com as do banco de dados.
2. **Dashboard** (tema escuro) com:
   - Menu lateral: **Dashboard**, **Adicionar gastos**, **Adicionar rendimentos**, **Sair**.
   - Dois gráficos de pizza lado a lado: **Gastos por categoria** (esquerda) e **Ganhos por categoria** (direita).
   - Abaixo de cada gráfico, uma **lista com valor e porcentagem** de cada categoria.
   - Cards de resumo: total de gastos, total de ganhos e saldo do período.
   - Filtro por mês (padrão: mês atual).
3. **Tela Adicionar gastos**: formulário com categoria, valor, data e descrição + lista dos últimos lançamentos (editar/excluir).
4. **Tela Adicionar rendimentos**: mesma estrutura, com categorias de rendimento.

### Categorias

| Gastos (`ExpenseCategory`) | Rendimentos (`IncomeCategory`) |
|---|---|
| `gasolina` — Gasolina | `salario_fixo` — Rendimento fixo / salário |
| `alimentacao` — Alimentação | `dividendos` — Dividendos |
| `lazer` — Lazer | `trabalho_informal` — Trabalhos informais |
| `luz` — Luz | `freelance` — Freelance |
| `agua` — Água | `aluguel_recebido` — Aluguel recebido |
| `faculdade` — Faculdade | `juros` — Juros / rendimentos de aplicações |
| `aluguel` — Aluguel / moradia | `bonus` — Bônus / 13º |
| `internet` — Internet / telefone | `vendas` — Vendas |
| `saude` — Saúde | `outros` — Outros |
| `transporte` — Transporte | |
| `mercado` — Mercado | |
| `assinaturas` — Assinaturas | |
| `outros` — Outros | |

Categorias são `TextChoices` no Django (fonte única da verdade). O front obtém a lista via `GET /api/categories/` — **nunca** duplicar a lista em hard-code no front.

---

## 2. Stack

| Camada | Tecnologia |
|---|---|
| Back-end | Python 3.12+, Django 5.x, Django REST Framework |
| Banco | SQLite (`back/db.sqlite3`) — visualizável no VS Code (extensão *SQLite Viewer*) |
| Front-end | Node.js 20+ com Express (servidor + proxy), HTML5, CSS3, JavaScript (ES Modules, sem framework) |
| Gráficos | Chart.js (instalado via npm, servido localmente — sem CDN) |
| Testes back | pytest + pytest-django + coverage |
| Testes front | `node:test` + supertest (servidor), Playwright (E2E) |
| Qualidade | ruff + black (Python), eslint + prettier (JS) |

---

## 3. Arquitetura

```
Navegador ──► Node/Express :3000 ──► /           → arquivos estáticos (front/public)
                                └──► /api/*      → proxy para Django :8000
```

- O Express serve as páginas e faz **proxy reverso** de `/api` para o Django. Assim front e API ficam na **mesma origem**: sem CORS, cookies de sessão e CSRF funcionam nativamente.
- Autenticação: **sessão do Django** (cookie `HttpOnly`, `SameSite=Lax`) + **token CSRF** enviado no header `X-CSRFToken` em toda requisição que altera dados.
- O Node **não** guarda regra de negócio nem acessa o banco. Toda regra fica no Django.

### Estrutura de pastas

```
system medvet/
├── CLAUDE.md
├── .claude/agents/          # definição dos agentes (backend, frontend, qa)
├── docs/qa/                 # relatórios do QA por tarefa
├── back/
│   ├── venv/                # ambiente virtual (NÃO versionar)
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── .env.example
│   ├── manage.py
│   ├── pytest.ini
│   ├── config/              # settings, urls, wsgi
│   ├── accounts/            # usuário customizado (login por e-mail), auth API
│   └── finances/            # Expense, Income, categorias, dashboard
└── front/
    ├── package.json
    ├── server.js            # Express + helmet + proxy /api
    ├── .env.example
    ├── public/
    │   ├── index.html       # login
    │   ├── dashboard.html
    │   ├── gastos.html
    │   ├── rendimentos.html
    │   ├── css/  (variables.css, base.css, layout.css, components.css)
    │   └── js/   (api.js, auth.js, dashboard.js, gastos.js, rendimentos.js, ui.js)
    └── tests/  (server.test.js, e2e/*.spec.js)
```

---

## 4. Back-end (Django)

### 4.1 Ambiente

```bash
cd back
python -m venv venv
# Windows:  venv\Scripts\activate      | Linux/WSL: source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser          # cria o primeiro usuário (e-mail + senha)
python manage.py runserver 8000
```

- **Toda** dependência é instalada dentro de `back/venv`. Nunca usar o Python global.
- Versões fixadas em `requirements.txt` (`pip freeze` filtrado).

### 4.2 Modelos

- `accounts.User` — `AbstractUser` customizado com `email` único e `USERNAME_FIELD = "email"`; `username` removido. Definir `AUTH_USER_MODEL = "accounts.User"` **antes** da primeira migração.
- `finances.Expense` — `user (FK)`, `category (TextChoices)`, `amount (DecimalField max_digits=12, decimal_places=2, > 0)`, `date`, `description (opcional, máx. 255)`, `created_at`, `updated_at`.
- `finances.Income` — mesmos campos, com `IncomeCategory`.
- Valores monetários **sempre** `Decimal`, nunca `float`.
- Índices em `(user, date)`.

### 4.3 API (prefixo `/api/`)

| Método | Rota | Descrição | Auth |
|---|---|---|---|
| GET | `/api/auth/csrf/` | Define o cookie CSRF | Não |
| POST | `/api/auth/login/` | `{email, password}` → 200 + dados do usuário / 401 genérico | Não |
| POST | `/api/auth/logout/` | Encerra a sessão | Sim |
| GET | `/api/auth/me/` | Usuário logado (ou 401/403) | Sim |
| GET | `/api/categories/` | `{expenses:[{value,label}], incomes:[...]}` | Sim |
| GET/POST | `/api/expenses/` | Lista (filtro `?month=YYYY-MM`) / cria | Sim |
| GET/PUT/PATCH/DELETE | `/api/expenses/<id>/` | Detalhe | Sim (dono) |
| GET/POST | `/api/incomes/` | Idem | Sim |
| GET/PUT/PATCH/DELETE | `/api/incomes/<id>/` | Idem | Sim (dono) |
| GET | `/api/dashboard/summary/?month=YYYY-MM` | Totais, saldo e agregação por categoria com `%` | Sim |

Formato do `summary`:

```json
{
  "month": "2026-10",
  "total_expenses": "1520.00",
  "total_incomes": "5000.00",
  "balance": "3480.00",
  "expenses_by_category": [{"category":"alimentacao","label":"Alimentação","total":"800.00","percent":52.63}],
  "incomes_by_category":  [{"category":"salario_fixo","label":"Rendimento fixo / salário","total":"5000.00","percent":100.0}]
}
```

- Agregação feita no banco (`values().annotate(Sum)`), não em loop Python.
- Porcentagens com 2 casas; soma tolerada de 100 ± 0,01.
- Valores serializados como **string** decimal.
- Erros no padrão DRF: `{"detail": "..."}` ou `{"campo": ["mensagem"]}`.

### 4.4 Segurança (obrigatório)

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` lidos de `.env` (`django-environ` ou `python-decouple`). `.env` **nunca** versionado.
- Senhas apenas via `set_password` / hashers do Django (PBKDF2 ou Argon2). Nunca logar senha.
- Login com `authenticate()` + `login()`; mensagem de erro **genérica** ("E-mail ou senha inválidos") — não revelar se o e-mail existe.
- **Rate limit** no login (ex.: `django-axes` ou throttle DRF `5/min` por IP).
- `CsrfViewMiddleware` ativo; nada de `csrf_exempt`.
- Cookies: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`, `CSRF_COOKIE_SAMESITE="Lax"`; em produção `*_SECURE=True`, `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`.
- `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`; querysets **sempre** filtrados por `request.user` (`get_queryset`) — usuário nunca acessa dados de outro (retornar 404).
- `user` definido no `perform_create`, nunca aceito do payload.
- Validação: `amount > 0`, categoria válida, data não absurda (ex.: até 1 ano no futuro), descrição sanitizada pelo serializer.
- `AUTH_PASSWORD_VALIDATORS` padrão ativos.
- Rodar `python manage.py check --deploy` antes de qualquer entrega para produção.

### 4.5 Convenções Python

- PEP 8, `black` + `ruff`. Type hints em funções públicas.
- Views finas: lógica de agregação em `finances/services.py`.
- Cada app com `tests/` (`test_models.py`, `test_api.py`, `test_services.py`).
- Migrações versionadas; nunca editar migração já aplicada.

---

## 5. Front-end (Node.js + HTML/CSS/JS)

### 5.1 Ambiente

```bash
cd front
npm install
cp .env.example .env        # PORT=3000, API_URL=http://127.0.0.1:8000
npm run dev                 # node --watch server.js
```

Scripts esperados em `package.json`: `dev`, `start`, `lint`, `format`, `test`, `test:e2e`.

### 5.2 Servidor (`server.js`)

- Express + `helmet` (CSP restrita a `'self'`), `compression` e proxy reverso próprio (`proxy.js`, `node:http`) para `/api` — sem `http-proxy-middleware` (dependência com vulnerabilidade sem correção). O proxy anexa o IP do cliente ao `X-Forwarded-For` (o back usa `NUM_PROXIES=1`).
- Servir `public/` e `node_modules/chart.js/dist` em `/vendor/chart.js`.
- Sem lógica de negócio. Sem armazenar credenciais.

### 5.3 Telas

**Login (`index.html`)** — card central, campos e-mail e senha, botão "Entrar", mensagem de erro inline, estado de carregamento no botão. Ao abrir, chama `/api/auth/csrf/`; se `/api/auth/me/` já responder 200, redireciona para o dashboard.

**Dashboard (`dashboard.html`)** — sidebar fixa à esquerda (colapsável em telas < 768px), topo com nome do usuário e seletor de mês, 3 cards de resumo, grid de 2 colunas com os gráficos de pizza (doughnut) e, abaixo de cada um, a lista `categoria — R$ valor — %` com marcador colorido igual à fatia. Estado vazio amigável quando não houver dados.

**Gastos (`gastos.html`) / Rendimentos (`rendimentos.html`)** — formulário (categoria `select`, valor, data com padrão hoje, descrição) + tabela dos lançamentos do mês com editar/excluir (confirmação antes de excluir). Toast de sucesso/erro.

Todas as páginas protegidas verificam `/api/auth/me/` ao carregar; 401/403 → redireciona para o login.

### 5.4 Design (tema escuro)

Tokens em `css/variables.css` — usar **somente** variáveis, nunca cores soltas:

```css
:root {
  --bg: #0f1115; --surface: #171a21; --surface-2: #1f232c; --border: #2a2f3a;
  --text: #e6e8ee; --text-muted: #9aa3b2;
  --primary: #6c8cff; --success: #2ecc8f; --danger: #ff6b6b; --warning: #f5b84b;
  --radius: 12px; --gap: 16px; --font: "Inter", system-ui, sans-serif;
}
```

- Gastos em tons quentes, ganhos em tons frios/verdes; paleta das fatias definida em um único lugar (`ui.js`).
- Contraste mínimo WCAG AA, foco visível em todos os controles, `label` em todo input, navegação por teclado.
- Responsivo: gráficos empilham em uma coluna abaixo de 900px.
- Valores formatados com `Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'})`.

### 5.5 Convenções JS

- ES Modules, `const`/`let`, funções pequenas, sem jQuery, sem frameworks.
- **Todo** acesso à API passa por `js/api.js` (wrapper de `fetch` com `credentials: 'same-origin'`, header `X-CSRFToken`, tratamento de 401 e de erros).
- Nunca usar `innerHTML` com dados do usuário — usar `textContent` / `createElement` (prevenção de XSS).
- Nada de token/senha em `localStorage`.
- eslint + prettier sem erros antes de entregar.

---

## 6. Fluxo de trabalho com agentes

Agentes em `.claude/agents/`:

| Agente | Arquivo | Responsabilidade |
|---|---|---|
| Back-end | `backend-dev.md` | Django, modelos, API, segurança, testes unitários do back |
| Front-end | `frontend-dev.md` | Express, HTML/CSS/JS, telas em tema escuro |
| QA | `qa-tester.md` | Testes a cada tarefa, relatório de ajustes para back/front |

Ciclo de cada tarefa:

1. **Dev** (back ou front) implementa a tarefa + testes básicos e descreve o que mudou.
2. **QA** escreve/roda testes (unitários, integração, E2E), registra o resultado em `docs/qa/AAAA-MM-DD-<tarefa>.md` com status **APROVADO** ou **REPROVADO** e uma lista de ajustes endereçados a `@backend-dev` ou `@frontend-dev`.
3. Dev corrige os itens apontados; QA re-testa. A tarefa só é concluída com **APROVADO**.

Ordem sugerida das tarefas:

1. Back: projeto Django + venv + usuário customizado + auth API.
2. Back: modelos Expense/Income + CRUD + categorias.
3. Back: endpoint de dashboard/summary.
4. Front: servidor Express + proxy + tela de login.
5. Front: layout base (sidebar) + dashboard com gráficos e listas.
6. Front: telas de gastos e rendimentos.
7. QA: suíte E2E completa (login → lançar gasto/rendimento → ver no dashboard → logout).

---

## 7. Definição de pronto (DoD)

- [ ] Testes passando (`pytest` no back, `npm test` no front, E2E quando aplicável).
- [ ] Cobertura do back ≥ 85%.
- [ ] Lint/format sem erros.
- [ ] Nenhum segredo no código; `.env.example` atualizado.
- [ ] Usuário A não vê/edita dados do usuário B (teste obrigatório).
- [ ] Telas funcionam em 360px, 768px e 1440px.
- [ ] Relatório do QA com status APROVADO.

## 8. Regras gerais

- Simplicidade primeiro: não adicionar biblioteca sem necessidade clara.
- Commits pequenos no padrão Conventional Commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`).
- `.gitignore`: `back/venv/`, `back/.env`, `back/db.sqlite3` (opcional versionar só em dev), `front/node_modules/`, `front/.env`, `__pycache__/`, `.coverage`, `playwright-report/`.
- Mensagens para o usuário final em **português do Brasil**; código e nomes de variáveis em **inglês**.
