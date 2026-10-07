# QA — Tarefa 3: Dashboard (`GET /api/dashboard/summary/`)
**Status:** APROVADO (re-teste QA-T3-01 concluído)
**Data:** 2026-10-06

Escopo: `finances/services.py` (`build_monthly_summary`, `_by_category`, `current_month`, `parse_month`), `DashboardSummaryView` e a rota `dashboard/summary/`.

Ambiente: `back/venv` (Python 3.14.4, SQLite 3.50.4).

## Testes executados

| Comando | Resultado |
|---|---|
| `pytest --cov=.` (suíte completa) | **496 passaram, 1 xfail (QA-T3-01), 0 falharam**. Cobertura de **99%**; `config/settings.py` fica em 84% (bloco `if not DEBUG`, já testado em subprocesso) |
| `pytest finances/tests/test_qa_dashboard.py` | 75 passaram e 1 xfail estrito (testes novos do QA) |
| `ruff check .` | OK |
| `black --check .` | OK (43 arquivos) |
| `python manage.py check` | OK (0 issues) |
| `python manage.py makemigrations --check --dry-run` | OK, "No changes detected" |

Arquivo novo: `back/finances/tests/test_qa_dashboard.py`. Quase todos os testes usam **sessão real** (`/csrf/`, depois `/login/` com `X-CSRFToken`). As exceções:
- Os testes com relógio simulado e os de contagem de queries usam `force_authenticate`. Com o relógio adiantado, a sessão real expiraria.
- Os testes de invariantes do serviço chamam `build_monthly_summary` direto.

### Verificação por item

- **Formato x CLAUDE.md 4.3**
  - As chaves de topo são exatamente as do exemplo, na mesma ordem.
  - Os itens têm exatamente `category`, `label`, `total` e `percent`.
  - `total_*`, `balance` e `total` são **strings** com 2 casas (`-?\d+\.\d{2}`).
  - `percent` é **número JSON float**: `100.0` sai como número, não como string.
  - O exemplo do CLAUDE.md (800 + 720 / 5000) é reproduzido byte a byte nos valores.
  - Um mês vazio devolve `"0.00"` e listas vazias.
  - A resposta não expõe `id`, `user`, e-mail nem descrição.
- **Labels:** os 13 de gasto e os 9 de rendimento vêm iguais aos `TextChoices`. Em empate de total, a ordem é alfabética pela categoria.
- **Totais e saldo**
  - Não há erro de ponto flutuante: `0.10 + 0.20` dá `0.30`, e 99 lançamentos de `0.01` dão `0.99`.
  - Saldo zero dá `"0.00"`, e saldo negativo sai certo (`-0.01`, `-1.09`).
  - `3 × 9999999999.99 + 0.01` dá `29999999999.98`, e `10 × max + 0.01` dá `99999999999.91`.
  - `100 × max + 0.01` dá `999999999999.01`, e `1000 × max + 0.01` dá `9999999999990.01` (sonda manual).
  - O total por categoria bate com a soma dos lançamentos no banco.
  - Depois de criar, editar e excluir pela API, o summary reflete a mudança na hora.
- **Porcentagens**
  - Com fatias iguais (3, 6, 7, 9, 11, 12 e 13 categorias), a soma dá 100 ± 0,01.
  - Com 1 × `9999999999.99` mais 12 × `0.01`, o resultado é 100.0 / 0.0: nenhuma fatia negativa.
  - Com 12 fatias de exatamente 0,005% (que arredondam para 0,01), a maior fatia é ajustada de −0,06, para 99.88. Fica dentro de [0, 100].
  - **60 cenários aleatórios** (semente fixa) confirmam, em todos os casos:
    - a soma é 100 ± 0,01;
    - toda `percent` fica em [0, 100];
    - os valores têm 2 casas;
    - a lista está em ordem decrescente de total;
    - o desvio em relação ao valor exato é ≤ 0,07;
    - o saldo é igual a rendimentos − gastos.
- **Limites de mês**
  - 30/11, 01/12, 31/12 e 01/01 caem cada um no seu mês, inclusive na virada de dezembro para janeiro.
  - 29/02/2024 entra em 2024-02 e 28/02/2026 em 2026-02.
  - Os meses `2000-01` e `9998-12` são aceitos.
- **Mês padrão (America/Sao_Paulo):** com o relógio simulado, os instantes abaixo dão o mês esperado.

  | Instante UTC | Mês |
  |---|---|
  | 01/11 02:59:59 | `2026-10` |
  | 01/11 03:00 | `2026-11` |
  | 01/01/2027 02:30 | `2026-12` |
  | 01/01/2027 03:00 | `2027-01` |
  | 01/03/2028 01:00 | `2028-02` |

  Em todos esses casos o lançamento do dia local é somado. Sem o parâmetro, o resultado é igual ao de `?month=<mês atual>`.
- **Isolamento A x B**
  - B tem dados em todas as categorias. A vê tudo zerado; com os próprios dados, vê só os seus (100% numa categoria).
  - B vê os próprios totais.
  - Os parâmetros `?user=` e `?user_id=` são ignorados.
- **`month` inválido**
  - Os 18 formatos da Tarefa 2 retornam **400** com corpo exatamente `{"month": ["..."]}`, assim como `0000-01`, `+2026-10` e `-2026-10`.
  - A lista inclui vazio, `2026-1`, `2026-13`, `1999-12`, `9999-12`, espaços, `\n`, dígitos full-width e uma tentativa de SQL injection.
- **Métodos**
  - POST, PUT, PATCH e DELETE com CSRF retornam **405** com `detail`, e nada muda no banco.
  - Sem CSRF, retornam 403.
  - HEAD retorna 200. OPTIONS retorna 200 e não anuncia POST.
- **Sem login**
  - Retorna **403** com e sem `month`, inclusive com `month` inválido: a autenticação acontece antes da validação.
  - Depois do logout, também retorna 403.
- **Agregação no banco e número de queries**
  - Revisão do código: `aggregate(Sum)` + `values("category").annotate(Sum)`, com `order_by()` limpo antes do agrupamento.
  - O único loop em Python percorre as linhas **já agregadas**, ou seja, as porcentagens (no máximo 13).
  - O serviço faz exatamente **4 queries** com 0, 1, 13 e 200 lançamentos por modelo. A view faz ≤ 4 com 0 e 50 lançamentos.

## Ajustes para @backend-dev

- [x] [BAIXA] **QA-T3-01 (CORRIGIDO — ver Re-teste): depois do ajuste de arredondamento, a maior fatia pode ficar com % menor que a seguinte.**
  - **Passos:** em 2026-10, crie gastos `gasolina 100.01` e `100.00` em mais 6 categorias. Depois chame `GET /api/dashboard/summary/?month=2026-10`.
  - **Esperado:** a ordem das porcentagens acompanha a ordem dos totais. A categoria com o maior total nunca deve exibir % menor que outra.
  - **Obtido:** `[14.26, 14.29, 14.29, 14.29, 14.29, 14.29, 14.29]`. Cada fatia arredonda para 14.29 (soma 100.03), e o −0,03 vai inteiro para a maior.
  - **Impacto:** só visual, de poucos centésimos, na lista abaixo do gráfico. O mesmo acontece em empates (6 fatias iguais dão `16.65` e 5 × `16.67`).
  - **Sugestão:** em `back/finances/services.py`, `_by_category` (linha `percents[0] += ...`), usar o método do **maior resto** (Hamilton). A ideia é truncar as fatias em centésimos e distribuir os centésimos que faltam, um por fatia, às de maior resto. Assim a soma continua exatamente 100 e a monotonicidade é preservada.
  - **Teste:** `test_largest_slice_ordering_kept_after_adjustment` está como `xfail(strict=True)`. Depois da correção ele vai passar (XPASS strict = falha), e a marca `xfail` deve ser removida.

## Ajustes para @frontend-dev

- [ ] [BAIXA] (Tarefa 5, sugestão) Com o maior resto, uma categoria com valor > 0 pode vir com `percent: 0.0` (fatia < 0,005%). Na lista do dashboard, exibir `< 0,01%` quando `percent === 0` e `total !== "0.00"`, para não sugerir que a categoria está zerada.

- Nenhum nesta tarefa, que é só de back-end.

## Observações / melhorias sugeridas

- **Precisão no SQLite.** O SQLite guarda `DecimalField` com afinidade NUMERIC, e o `SUM` é feito em ponto flutuante; o Django converte com 15 dígitos.
  - Até `1000 × 9999999999.99 + 0.01` (cerca de 10¹³) o resultado é exato.
  - Com 10 000 × max, ou seja, cerca de 10¹⁴ no mês, os centavos se perdem: obtido `99999999999900.00`, esperado `...900.01`.
  - Isso é irrelevante para finanças pessoais. Fica registrado só caso o banco mude ou haja importações em massa. Não requer ação.
- **Front (Tarefa 5).** As porcentagens já vêm prontas da API. O front não deve recalculá-las e deve formatar `percent` com `Intl.NumberFormat('pt-BR')`. Os valores monetários são strings: converter com cuidado (`Number(...)`) só na hora de exibir ou plotar.
- **Mês padrão.** `current_month()` usa `timezone.localdate()`, então segue `TIME_ZONE`. O comportamento está correto e coberto com relógio simulado.
- **Definição de pronto (back):** testes passando, cobertura de 99%, lint/format OK, `check` e `makemigrations --check` OK, e isolamento A x B testado. Os itens de tela (360/768/1440 px) não se aplicam a esta tarefa.

## Re-teste (2026-10-06) — QA-T3-01

**Status do re-teste:** APROVADO

Correção: `back/finances/services.py`, `_largest_remainder_percents`, que usa o método do maior resto (Hamilton). O `xfail` de `test_largest_slice_ordering_kept_after_adjustment` foi removido, e o teste agora passa: `[14.29, 14.29, 14.29, 14.28, 14.28, 14.28, 14.28]`.

| Comando | Resultado |
|---|---|
| `pytest --cov=.` (suíte completa) | **509 passaram, 0 falharam, 0 xfail**, cobertura de 99% |
| `pytest finances/tests/test_qa_dashboard.py` | 83 passaram |
| `ruff check .` | OK |
| `black --check .` | OK (43 arquivos) |
| `python manage.py check` | OK |
| `makemigrations --check --dry-run` | OK, "No changes detected" |

Mudanças nos testes do QA (`back/finances/tests/test_qa_dashboard.py`):

- **`_assert_percent_invariants` ficou mais rígido.** Agora exige:
  - soma **exatamente 100.00**, e não mais 100 ± 0,01;
  - `percent` monotônico não crescente, acompanhando a ordem dos totais;
  - diferença ≤ 0,01 entre fatias empatadas;
  - desvio **< 0,01** em relação ao valor exato (antes era ≤ 0,07).

  Esses invariantes valem em todos os testes que usam o helper, inclusive nos 60 cenários aleatórios via API/serviço.
- **`test_tiny_slices_round_up_never_exceed_100`** foi substituído por `test_tiny_slices_largest_remainder`.
  - O cenário é 199.88 + 12 × 0.01, com total 200.00.
  - O resultado esperado agora é `[99.94, 0.01 × 6, 0.00 × 6]`. As 6 primeiras em ordem alfabética recebem o centésimo, por empate no resto de 0,005.
- **Novo:** `test_equal_totals_percents_differ_at_most_one_cent`, com 2, 3, 6, 7, 9 e 13 fatias iguais.
- **Novo:** `test_largest_remainder_pure_function_random`, com 3000 cenários aleatórios (semente 42, de 1 a 13 fatias, escalas de 0,01 a 10⁷). Em todos eles:
  - a soma é 100.00;
  - cada % fica em [0, 100];
  - os valores têm 2 casas;
  - a ordem é monotônica;
  - o desvio é < 0,01.

Análise crítica do caso `0.00%` para uma fatia > 0:

- **Aceitável no back.** O valor exato é 0,005%, então 0.00 e 0.01 ficam igualmente distantes do real. O método mantém a soma exata e a ordem.
- **Não é regressão.** O comportamento antigo já exibia `0.0` no cenário de 1 × máximo + 12 × 0.01.
- **Efeito colateral do desempate:** fatias com o mesmo total podem diferir em 0,01 (14.29 x 14.28). Isso é inerente a qualquer método com soma exata em 2 casas, e o desempate é determinístico (ordem por categoria).
- **Encaminhamento:** fica como sugestão BAIXA de exibição para o front (`< 0,01%`), sem item para o back.

**Status final da Tarefa 3:** APROVADO. Não há itens ALTA, MÉDIA ou BAIXA abertos para o back.
