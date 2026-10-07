# QA — Front: QA-F-04 (botão "Fechar menu") + proxy próprio (`proxy.js`) / npm audit
**Status:** APROVADO
**Data:** 2026-10-08

Escopo:
1. **QA-F-04:** botão `#sidebar-close` ("Fechar menu", `aria-controls="sidebar"`) dentro da gaveta nas 3 páginas protegidas.
2. **Proxy próprio:** `front/proxy.js` (`node:http`) no lugar do `http-proxy-middleware`, e remoção do `nodemon` (`dev` = `node --watch`). Meta: `npm audit` = 0, sem regressões e com a brecha de X-Forwarded-For fechada.

Ambiente: Windows 11, Node 24, Playwright 1.63 (Chromium), Django em `127.0.0.1:8000 --noreload` (`back/venv`, `NUM_PROXIES=1`, `LOGIN_THROTTLE_RATE=5/min`) e front em `:3000` (`node server.js`).

## Testes executados

| Comando | Resultado |
|---|---|
| `npm audit` | **found 0 vulnerabilities** (sem `http-proxy-middleware`/`nodemon` no `package.json`) |
| `npm run lint` | OK (0 erros, incluindo os testes novos do QA) |
| `npm run format:check` | OK |
| `npm test` (`node:test` + supertest) | **34/34 passaram** (24 do dev + 10 novos do QA em `tests/proxy-qa.test.js`) |
| `npx playwright test` (suíte completa, 1 execução, depois de esperar 66s pelo throttle) | **106 passaram, 0 falharam, 16 pulados de propósito** (por viewport/throttle) |
| Teste real de throttle contra o Django pelo `:3000` (script) | 5× 401 e depois **429** no 6º, mesmo com XFF forjado diferente a cada tentativa |
| Fluxo real pelo proxy (script): csrf → login → CRUD → logout | OK (detalhes abaixo) |

### Arquivos de teste criados (só testes)

- `front/tests/proxy-qa.test.js` (novo, 10 testes): usa requisições cruas (`net`) contra o `createApp` com uma API falsa que devolve o eco do que recebeu.
  - Path traversal.
  - URL absoluta e `//`.
  - Query com caracteres especiais.
  - XFF forjado em várias linhas.
  - `Connection: X-Foo` e hop-by-hop na ida e na volta.
  - 100 KB binário (sha256) e corpo chunked.
  - UTF-8.
  - CL+TE conflitantes (smuggling).
  - OPTIONS e HEAD.
  - Cliente que desiste aborta o upstream.
- `front/tests/e2e/qa-f04.spec.js` (novo): QA-F-04 pela **árvore de acessibilidade real do Chromium** (CDP `Accessibility.getFullAXTree`, nós não ignorados), ciclo completo de Tab, tecla Espaço e área de toque, nas 3 páginas.

### QA-F-04: verificado

Em 360px, nas 3 páginas (dashboard, gastos, rendimentos):

- **Gaveta fechada:** o leitor de tela recebe 0 botões "Fechar menu" e 1 botão "Abrir menu".
- **Ao abrir:**
  - O foco vai para o link "Dashboard".
  - Fica exposto **exatamente 1** botão "Fechar menu", o `#sidebar-close`, dentro de `complementary "Navegação"`. O `#menu-toggle` fica inert e o Chromium o marca como ignorado, então não há rótulo duplicado.
  - O botão tem `aria-controls=sidebar` e `type=button`, com área de toque ≥ 24×24.
- **Ciclo de Tab:** fechar → Dashboard → Adicionar gastos → Adicionar rendimentos → Sair → (chrome) → fechar… e nunca chega ao conteúdo atrás.
- **Fechar pelo botão:** Enter, **Espaço** e clique fecham. O foco volta ao `#menu-toggle` (`aria-expanded=false`, `aria-label="Abrir menu"`) e o inert sai.
- **Captura em 360px:** o "×" aparece alinhado à direita do "Finanças", com foco visível.

Em 768px e 1440px: `#sidebar-close` fica oculto, fora da árvore de acessibilidade, e não aparece em 40 Tabs seguidos em nenhuma das 3 páginas.

Observação técnica: o `getByRole` e o `ariaSnapshot` do Playwright **não** respeitam `inert` e contam 2 "Fechar menu". Por isso o spec do QA usa a árvore AX do Chromium. O spec do dev (`regressions.spec.js`) restringe a busca a `#sidebar` e por isso não é afetado.

### Proxy: verificado contra o Django real

- **Brecha do XFF fechada.** 8 logins inválidos pelo `:3000`, um após o outro, com estes `X-Forwarded-For`: `1.2.3.4`, `5.6.7.8, 9.9.9.9`, `10.0.0.1`, `8.8.8.8, 8.8.4.4, 1.1.1.1`, `203.0.113.7`, nenhum, `198.51.100.1` e `127.0.0.1`.
  - Resultado: 1–5 → 401 genérico; **6–8 → 429** com `Retry-After: 58`.
  - O proxy anexa o IP do socket ao final do XFF, inclusive quando o cliente manda várias linhas de XFF, e o `NUM_PROXIES=1` passa a usar esse IP.
- **Cookies e CSRF:**
  - `csrftoken` (SameSite=Lax) e `sessionid` (HttpOnly, SameSite=Lax) chegam ao cliente.
  - Fluxo completo:
    - login → 200
    - `me` → 200
    - POST gasto → 201
    - PATCH → 200
    - GET com `?month=…&x=%C3%A7%26%3D%23%20+` → 200
    - summary → 200
    - DELETE → 204 sem corpo
    - logout → 204
    - `me` → 403
- **UTF-8:** a descrição `QA-E2E proxy Ção ✓ 日本 😀` volta idêntica do Django.
- **Corpo grande:**
  - Descrição com 100 KB → 400 `{"description":["…255 caracteres."]}`, tratado pelo Django sem 502/413.
  - JSON de ~100 KB (campo extra ignorado) → 201.
  - No teste unitário, 100 KB binário chegam com o sha256 idêntico.
- **Hop-by-hop:**
  - `Connection: X-Foo, close` remove `X-Foo`, além de `Keep-Alive`, `TE`, `Upgrade`, `Proxy-Authorization` e `Proxy-Connection`. O `X-Bar` passa.
  - Na volta, `Connection`, os headers listados nele, `Keep-Alive` e `Proxy-Authenticate` da API não chegam ao cliente.
  - O `Host` original (`localhost:3000`) é preservado.
- **Path traversal:**
  - `/api/../server.js`, `/api/%2e%2e/server.js`, `/api/%2e%2e/%2e%2e/front/.env`, `/api/..%2fserver.js`, `/api/%5c..%5cserver.js`, `/api/../.env`, `/api/%2e%2e/admin/login/` e `/api/auth/csrf/../../../admin/` são repassados literalmente ao Django, que responde 404. Nenhum arquivo do front é exposto e o `/admin/` não fica alcançável.
  - `/server.js`, `/proxy.js`, `/.env`, `/%2e%2e/server.js` e `/apiary` → 404 do front.
  - URL absoluta (`GET http://evil.example/api/…`) e `//127.0.0.1:8000/api/…` **não** passam pelo proxy (404), então não há proxy aberto (SSRF).
  - `/x/../api/…` → 404.
- **Smuggling:** `Content-Length` junto com `Transfer-Encoding: chunked` → 400 do parser do Node, e nada chega à API.
- **OPTIONS e HEAD:** repassados (OPTIONS → 200 com metadados do DRF; HEAD → 200 sem corpo).
- **Falhas:**
  - API fora do ar → 502 `{"detail":"Servidor da API indisponível…"}`, sem host/porta.
  - Timeout → 504, coberto no teste do dev.
  - Cliente que desiste → upstream abortado (teste do QA).
- **Compression:** respostas de `/api` não são recomprimidas (teste do dev).

## Ajustes para @backend-dev

Nenhum.

## Ajustes para @frontend-dev

- [x] **[BAIXA] QA-F-05 — O proxy é a borda, mas confia em `X-Forwarded-Host`/`-Proto`/`-Port` enviados pelo cliente.**
  - **Passos:** `GET /api/qualquer/` com `X-Forwarded-Host: evil.example` e `X-Forwarded-Proto: https`. Ver `tests/proxy-qa.test.js` ou o eco da API falsa.
  - **Esperado:** como o Express é o primeiro proxy, o valor deveria ser **definido** por ele (`X-Forwarded-Host: localhost:3000`, `X-Forwarded-Proto: http`), descartando o que o cliente mandou.
  - **Obtido:** o upstream recebe `x-forwarded-host: evil.example`, e o Proto/Port vêm como lista (`https,http`).
  - **Impacto hoje:** nenhum, porque o Django não usa `USE_X_FORWARDED_HOST` nem `SECURE_PROXY_SSL_HEADER`. Mas é uma armadilha: se alguém ativar uma dessas opções, abre envenenamento de Host (links absolutos e reset de senha) ou faz o Django tratar HTTP como HTTPS.
  - **Sugestão:** em `front/proxy.js` (`forwardedHeaders`), sobrescrever `x-forwarded-host`, `x-forwarded-proto` e `x-forwarded-port`. Só o XFF deve continuar sendo anexado.
- [x] **[BAIXA] QA-F-06 (opcional) — O header `Server: WSGIServer/0.2 CPython/3.14.4` do Django passa pelo proxy e revela a stack e a versão.**
  - Isso só acontece com o `runserver` de dev; em produção, o servidor WSGI será outro.
  - **Sugestão:** remover `server` dos headers de resposta em `proxy.js`, uma linha junto do `stripHopByHop` da resposta.

## Observações / melhorias sugeridas

- **Dev:** com `DEBUG=True`, um 404 em `/api/...` devolve a página de debug do Django com a lista de rotas, o que é esperado em dev. Confirmar `DEBUG=False` em produção (`check --deploy`, já previsto no CLAUDE.md §4.4).
- **Throttle:** a mensagem 429 vem da tradução do DRF ("…diponível…", com erro de digitação upstream). O front já mostra a sua própria mensagem amigável para 429, então não há impacto.
- **Rodadas de E2E:** a suíte usa 4 logins por execução (setup + 3 pela interface). Rodar `qa-f04.spec.js` ou `regressions.spec.js` isolados também consome 1 login (setup). Esperar 60s antes da suíte completa, como já registrado em 2026-10-07.
- **DoD (§7), parte do front:**
  - [x] `npm test` e E2E passando
  - [x] Lint/format ok
  - [x] `npm audit` = 0
  - [x] Nenhum segredo no código
  - [x] 360/768/1440 ok
  - [x] Isolamento A/B (coberto no back)
  - [x] Relatório APROVADO

## Ambiente ao final

- Django (PID 30488) e front (`node server.js`, PID 2248), que o QA subiu, foram encerrados por PID. As portas 3000 e 8000 ficaram livres.
- Lançamentos de teste: os criados pelo script (gasto 119 e rendimento 104) foram excluídos no próprio fluxo, e o teardown do Playwright removeu os `QA-E2E` restantes. Contagem final: `finances_expense` = 0 e `finances_income` = 0.

## Re-teste (QA-F-05 e QA-F-06)

**Data:** 2026-10-08
**Status final:** APROVADO. QA-F-05 e QA-F-06 corrigidos, sem regressões.

Correção do dev, em `front/proxy.js`:
- `forwardedHeaders` continua anexando o IP do socket ao `X-Forwarded-For`.
- `X-Forwarded-Host`, `-Proto` e `-Port` passam a ser **sobrescritos** com os valores reais da conexão.
- `Forwarded` e `X-Real-IP` enviados pelo cliente são descartados.
- A nova `responseHeaders()` remove `Server` e `X-Powered-By` das respostas da API.

| Verificação | Resultado |
|---|---|
| `npm run lint` | OK |
| `npm run format:check` | OK |
| `npm test` | **39/39** passaram (36 do dev + 3 novos do QA) |
| `npm audit` | found 0 vulnerabilities |
| `npx playwright test` (1 execução) | **106 passaram, 0 falharam, 16 pulados de propósito**, total 122 |

**Testes novos do QA** em `front/tests/proxy-qa.test.js`, com requisições cruas:
- **QA-F-05, headers forjados:** o cliente manda `X-Forwarded-Host` em 2 linhas, `X-Forwarded-Proto` em 2 linhas com caixa mista, `X-Forwarded-Port: 443`, `Forwarded` e `X-Real-IP`. O upstream recebe `localhost:3000`, `http` e `3000`, e não recebe `Forwarded` nem `X-Real-IP`.
- **QA-F-05, HTTP/1.0 sem `Host`:** o `X-Forwarded-Host` forjado não é repassado e o Proto chega como `http`.
- **QA-F-06:** a API falsa envia `Server: WSGIServer/...` e `X-Powered-By: Django`, e nenhum dos dois chega ao cliente.

### Teste real com Django (`runserver 127.0.0.1:8000 --noreload`) e front (`node server.js`)

**`Server`/`X-Powered-By` (QA-F-06):**
- `curl -i :3000/api/auth/csrf/` → 200 sem `Server` e sem `X-Powered-By`. Os headers do helmet (CSP, nosniff) e o `Set-Cookie csrftoken` (SameSite=Lax) estão presentes.
- Direto em `:8000`, a mesma rota responde com `Server: WSGIServer/0.2 CPython/3.14.4`. Ou seja, quem remove o header é o proxy.

**Headers forjados não chegam ao Django (QA-F-05):**
- **Montagem:** um relay TCP no scratchpad (`:8001` → Django `:8000`) registrou a requisição exatamente como o Django a recebeu. Uma segunda instância do front ficou em `:3001` com `API_URL=http://127.0.0.1:8001`.
- **Requisição:** `GET /api/auth/csrf/` com `X-Forwarded-Host: evil.example`, `X-Forwarded-Proto: https`, `X-Forwarded-Port: 443`, `Forwarded: for=6.6.6.6;host=evil.example` e `X-Real-IP: 6.6.6.6`.
- **O que o Django recebeu:**
  - `host: localhost:3001`
  - `x-forwarded-host: localhost:3001`
  - `x-forwarded-proto: http`
  - `x-forwarded-port: 3001`
  - `x-forwarded-for: 1.2.3.4,::1`
  - nenhum `Forwarded`/`X-Real-IP`
- Relay e front `:3001` foram encerrados por PID.

**Brecha do throttle continua fechada:**
- **Teste:** 8 logins inválidos seguidos pelo `:3000`, com XFF variado: `1.2.3.4`, `5.6.7.8, 9.9.9.9`, `10.0.0.1`, `8.8.8.8, 8.8.4.4`, `203.0.113.7`, nenhum, `198.51.100.1` e `127.0.0.1`.
- **Resultado:** 1–5 → 401, **6–8 → 429**.

**Fluxo do usuário de teste:** depois que a janela do throttle liberou:
- login → 200
- `me` → 200 (`qa@example.com`, sem `Server`)
- logout → 204
- `me` → 403

### Ambiente ao final

- Django (PID 11052) e front (PID 22484) foram encerrados por PID. As portas 3000, 8000, 3001 e 8001 ficaram livres.
- Lançamentos: `finances_expense` = 0 e `finances_income` = 0.
- Os logs ficaram em `front/test-results`, que o Playwright limpa a cada execução. O relay ficou só no scratchpad da sessão.

### Pendências

Nenhum ajuste ALTA, MÉDIA ou BAIXA em aberto para @frontend-dev ou @backend-dev.
