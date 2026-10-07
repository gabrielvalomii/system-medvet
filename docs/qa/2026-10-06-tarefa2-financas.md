# QA — Tarefa 2: Finanças (gastos, rendimentos e categorias)
**Status:** APROVADO
**Data:** 2026-10-06

Escopo:
- Modelos `Expense`/`Income` (base abstrata `Entry`), `ExpenseCategory`/`IncomeCategory`, constraints e índice.
- Serializers, `ModelViewSet` de `/api/expenses/` e `/api/incomes/`, `GET /api/categories/`, `parse_month` e admin.
- Re-teste do QA-T1-05, registrado em `docs/qa/2026-10-06-tarefa1-auth.md`, seção "Re-teste 2".

Ambiente: `back/venv` (Python 3.14.4, Django 5.2.18, DRF 3.18.1).

## Testes executados

| Comando | Resultado |
|---|---|
| `pytest --cov=.` (suíte completa) | **391 passaram, 0 falharam**. Cobertura de **98%**; só `config/settings.py` fica em 84%, por causa do bloco `if not DEBUG`, que é testado em subprocesso |
| `pytest finances/tests/test_qa_finances.py` | 186 passaram (testes novos do QA) |
| `pytest accounts/tests/test_qa_retest.py` | 24 passaram (QA-T1-05 reescrito: +6 testes, −1 obsoleto) |
| `ruff check .` | OK |
| `black --check .` | OK (42 arquivos) |
| `python manage.py check` | OK (0 issues) |
| `python manage.py check --deploy` (`DEBUG=False` + `SECRET_KEY` forte) | OK (0 issues) |
| `python manage.py makemigrations --check --dry-run` | OK, "No changes detected" |

Arquivo novo: `back/finances/tests/test_qa_finances.py`. Os testes usam uma **sessão real**: `GET /csrf/`, depois `POST /login/` com `X-CSRFToken`, e o token rotacionado é reutilizado. Não usam `force_authenticate`.

### Verificação por item

- **Isolamento A x B (gastos e rendimentos)**
  - Para A, a lista vem vazia (com e sem `?month`).
  - Em itens de B, `GET`, `PUT`, `PATCH` (inclusive vazio) e `DELETE` retornam **404**. A linha de B no banco fica idêntica antes e depois (snapshot de `values()`).
  - O 404 de um item de outro usuário é igual ao de um id inexistente, então não dá para enumerar ids.
  - Com dados mistos, a lista traz só os ids de A.
- **`user` no payload**
  - `user`/`user_id` são ignorados em POST, PUT e PATCH: o dono continua A e B não recebe nenhum registro.
  - `user` não aparece na resposta.
  - `id`, `created_at`, `updated_at` e `category_label` enviados no payload também são ignorados.
- **Sem login:** `GET`/`POST`/`PUT`/`PATCH`/`DELETE`/`OPTIONS` e `/api/categories/` retornam 403. Depois do logout, as rotas voltam a retornar 403.
- **CSRF com sessão real**
  - Sem token, POST, PUT, PATCH e DELETE recebem 403 com "CSRF" no `detail`, e os dados não mudam.
  - Um token inválido também recebe 403.
  - Com o token, o CRUD completo funciona (201/200/200/204, e depois 404).
- **amount**
  - Retornam 400: `0`, `0.00`, `0.001`, `-0.01`, `-10`, `10.123`, `10000000000.00` (estoura `max_digits`), `1e20`, `NaN`, `±Infinity`, `abc`, `""`, `1,50`, `null`, `true`, `[]` e `{}`.
  - Retornam 201: `0.01`, `9999999999.99`, `" 15.5 "`, `12`, `12.5` e `1e3`.
  - O valor sempre volta como **string** com 2 casas, na criação, na lista e no detalhe.
- **date**
  - Retornam 201: `2000-01-01`, hoje, hoje+365 e `2024-02-29`.
  - Retornam 400: `1999-12-31`, `0001-01-01`, hoje+366, `9999-12-31`, `2026-02-30`, `2025-02-29`, `2026-13-01`, `31/12/2026`, `2026-10`, `hoje`, `""`, `null` e um número inteiro.
  - Um PATCH com data fora da faixa retorna 400 e não altera o registro.
- **description**
  - Retornam 400: `<script>`, `a < b`, `a > b`, `<`, 256 caracteres, 256 caracteres cercados de espaços, `\x00`, `null` e uma lista.
  - Ficam OK:
    - 255 caracteres, com espaços e `\t\n` nas pontas: o texto é aparado.
    - Só espaços: vira `""`.
    - Acentos, `&`, aspas e emoji.
    - `&lt;b&gt;`: guardado literalmente.
  - O campo é opcional; quando omitido, vira `""`.
- **category**
  - Cada um dos 13 valores de gasto é aceito em `/expenses/` e cada um dos 9 de rendimento em `/incomes/`.
  - Uma categoria do outro tipo retorna 400; `outros`, que existe nos dois, é aceita.
  - Também retornam 400: `""`, `null`, `MERCADO`, `" mercado"`, `Outros`, `inexistente`, `1` e `["outros"]`.
  - Um PATCH para uma categoria do outro tipo retorna 400 e não altera o registro.
- **Campos obrigatórios**
  - POST `{}` retorna 400 com `category`, `amount` e `date`.
  - PUT parcial retorna 400.
  - Um corpo form-urlencoded retorna 415, e JSON malformado retorna 400.
- **Filtro de mês**
  - Limites conferidos: 30/11 e 01/12, 31/12 e 01/01 (dezembro vira o ano), 29/02 e 01/03 em ano bissexto. Um mês sem dados devolve `[]`.
  - Retornam 400: `""`, `2026`, `2026-1`, `2026-001`, `26-10`, `2026-00`, `2026-13`, `1999-12`, `9999-12`, `2026/10`, `10-2026`, `2026-10-01`, espaços nas pontas, `\n` final, dígitos de largura total (`２０２６-１０`), `abcd-ef` e uma tentativa de injeção SQL.
  - A ordem é `-date, -id`.
- **Categorias x CLAUDE.md:** o teste lê a tabela **direto do `CLAUDE.md`** e compara com os `TextChoices` e com `GET /api/categories/`. Valores, rótulos e ordem são idênticos (13 de gasto e 9 de rendimento). O endpoint é somente leitura (POST/DELETE retornam 405).
- **Banco**
  - A `CheckConstraint` barra `amount` `0`, `-0.01` e `-100` com `IntegrityError`, tanto no `create` quanto no `update()`, que não passa pelo validador.
  - O índice `(user_id, date)` existe nas duas tabelas (conferido por introspecção).
  - Excluir um usuário remove em cascata só os lançamentos dele.
- **Admin**
  - Para um superusuário, carregam: a changelist (inclusive a busca por e-mail), as telas de adicionar e de alterar e o `autocomplete` de usuário.
  - O formulário do admin rejeita `amount=0`.
  - Um usuário sem `is_staff` é redirecionado para o login.

## Ajustes para @backend-dev

Nenhum item ALTA, MÉDIA ou BAIXA aberto.

## Ajustes para @frontend-dev

Não se aplica nesta tarefa. Vale levar para as Tarefas 5 e 6:
- Enviar `amount` como **string** decimal com ponto (`"12.50"`). A API aceita número JSON, mas a string evita imprecisão de float. Vírgula (`"1,50"`) retorna 400, então o front deve converter o formato pt-BR antes de enviar.
- A descrição com `<` ou `>` retorna 400 com mensagem em `description`. O front deve mostrar essa mensagem inline.
- `GET /api/expenses/` sem `?month` devolve **todos** os lançamentos (sem paginação). As telas devem sempre enviar `?month=AAAA-MM`.

## Observações / melhorias sugeridas

- (Opcional) A API aceita notação científica (`"1e3"` vira `1000.00`) e número JSON em `description` (`123` vira `"123"`). É o comportamento padrão do DRF e não causa dano; só documento aqui.
- (Opcional) Sem paginação, a listagem sem filtro pode crescer bastante com o tempo. Avaliar um limite ou paginação quando o volume justificar.
- QA-T1-05 da Tarefa 1 está **corrigido**. Os testes foram reescritos conforme o comportamento novo: o duplicado agora gera `IntegrityError`, e o fallback para dados legados é simulado removendo o índice dentro da transação do teste.
