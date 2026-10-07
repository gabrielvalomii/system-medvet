# QA — Tarefa 1: Configuração e autenticação (back-end)
**Status:** APROVADO (re-teste em 2026-10-06; ver seção "Re-teste")
**Data:** 2026-10-06

Escopo: projeto Django, `accounts.User` (login por e-mail), endpoints `/api/auth/{csrf,login,logout,me}/`, settings/segurança, admin. Front ainda não existe (itens de front ignorados).

## Testes executados

Ambiente: `back/venv` (Python 3.14.4, Django 5.2.18, DRF 3.18.1).

| Comando | Resultado |
|---|---|
| `python manage.py check` | OK (0 issues) |
| `python manage.py check --deploy` com `DEBUG=False` + `SECRET_KEY` forte | OK (0 issues) |
| `python manage.py check --deploy` com `.env` de dev (`DEBUG=True`) | 5 warnings esperados de dev (W004/W008/W012/W016/W018) |
| `python manage.py makemigrations --check --dry-run` | OK — "No changes detected" |
| `ruff check .` | OK |
| `black --check .` | OK (29 arquivos) |
| `pytest --cov` (suite completa) | **62 passaram, 2 falharam** — cobertura **97%** (settings.py 84%: bloco `if not DEBUG`, coberto via subprocesso no teste de QA) |

Testes do dev (28): todos passam.
Testes novos de QA: `back/accounts/tests/test_qa_auth.py` (36 testes, 34 passam, 2 falham documentando bugs):

- CSRF: login sem header → 403 e sem cookie `sessionid`; token de outro cliente → 403; `Origin` não confiável → 403; `Origin http://localhost:3000` aceito; falhas de CSRF não consomem o throttle. OK
- Enumeração: senha errada, e-mail inexistente e usuário inativo → 401 com corpo **byte a byte idêntico** e sem cookie de sessão; e-mails malformados/injeção/`null`/número e senha de 5000 chars → 401 genérico. OK
- Payload com `is_staff`/`is_superuser` ignorado. OK
- Rate limit: 6ª tentativa → 429 com `Retry-After` e sem sessão; logins bem-sucedidos também contam; balde separado por IP (`REMOTE_ADDR`). OK
- **Rate limit contornável via `X-Forwarded-For` forjado → FALHOU (QA-T1-01)**
- **`/admin/login/` sem rate limit → FALHOU (QA-T1-02)**
- Cookies: `sessionid` HttpOnly + SameSite=Lax; `csrftoken` SameSite=Lax e legível por JS (necessário). OK
- Sessão: chave de sessão rotacionada no login (anti fixation); token CSRF rotacionado no login; sessão invalidada ao desativar usuário e ao trocar senha. OK
- Logout: sem CSRF → 403 e sessão continua; com CSRF → 204, cookie zerado, `/me/` → 403; replay do cookie antigo → 403; `GET /logout/` → 405. OK
- Erros não autenticados no formato `{"detail": ...}`. OK
- Nenhuma resposta contém `password`, a senha ou o hash; hash no banco (SQL bruto) começa com `pbkdf2_sha256$`. OK
- Modelo/admin: `full_clean()` normaliza e bloqueia duplicado por caixa; login no admin por e-mail; admin rejeita duplicado `DUP@Example.com`; admin aplica validadores de senha. OK
- Settings: CSRF middleware ativo, flags de cookie, 4 validadores, `IsAuthenticated` padrão, hasher PBKDF2; com `DEBUG=False` → `SESSION/CSRF_COOKIE_SECURE=True`, `SECURE_SSL_REDIRECT=True`, HSTS ≥ 1 ano; `SECRET_KEY` sem default/hard-code; `.gitignore` com todas as entradas da seção 8; `.env.example` com `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`. OK

## Ajustes para @backend-dev

- [x] **[ALTA] QA-T1-01 — Rate limit do login contornável com `X-Forwarded-For` forjado.**
  - Passos: `GET /api/auth/csrf/`; enviar 10× `POST /api/auth/login/` com senha errada, cada um com um header diferente `X-Forwarded-For: 1.2.3.<i>` (mesmo `REMOTE_ADDR`).
  - Esperado: 429 a partir da 6ª tentativa. Obtido: 10× 401 (nenhum 429) — força bruta ilimitada.
  - Causa: sem `NUM_PROXIES`, o `get_ident()` do DRF usa o valor **inteiro** do `X-Forwarded-For` enviado pelo cliente como chave do throttle. Atrás do proxy Express há também o risco oposto: se o proxy não enviar XFF, todos os usuários compartilham o IP `127.0.0.1` e 5 erros de qualquer pessoa bloqueiam o login de todos.
  - Correção sugerida: `config/settings.py` (~linha 106, `REST_FRAMEWORK`) definir `"NUM_PROXIES": config("NUM_PROXIES", default=1, cast=int)` (1 = Express na frente), documentar no `.env.example` e combinar com o front que o proxy envia `xfwd: true`. Opcionalmente, somar um limite por e-mail (escopo extra) ou usar `django-axes`.
  - Teste: `accounts/tests/test_qa_auth.py::test_throttle_cannot_be_bypassed_with_spoofed_x_forwarded_for`.

- [x] **[MÉDIA] QA-T1-02 — `/admin/login/` sem rate limit (força bruta na conta mais privilegiada).**
  - Passos: criar superusuário; enviar 10× `POST /admin/login/` com senha errada; na 11ª enviar a senha correta.
  - Esperado: bloqueio (403/429) após N tentativas, conforme "Rate limit no login" (CLAUDE.md 4.4). Obtido: 302 (login aceito), nenhum limite.
  - Correção sugerida: `django-axes` (cobre admin e API) **ou** um throttle no admin, **ou** expor `admin/` só quando `DEBUG=True` / em caminho não óbvio (`config/urls.py` linha 5).
  - Teste: `accounts/tests/test_qa_auth.py::test_admin_login_is_rate_limited`.

- [x] **[BAIXA] QA-T1-03 — Login no admin é sensível a maiúsculas.** `POST /admin/login/` com `Admin@Example.com` falha para o usuário `admin@example.com` (a API normaliza, o `AdminAuthenticationForm` não). Sugestão: backend de autenticação customizado (ou `get_by_natural_key` no manager) usando `email__iexact`/normalização, para ficar consistente com a API.

- [x] **[BAIXA] QA-T1-04 — Throttle depende do cache local (`LocMemCache` padrão).** Com mais de um worker (gunicorn) o limite é por processo. Para produção, configurar `CACHES` compartilhado (ex.: `FileBasedCache`/Redis) e documentar.

## Ajustes para @frontend-dev

- Nenhum (front ainda não existe). Notas para a Tarefa 4:
  - O token CSRF é **rotacionado no login**: após `POST /api/auth/login/` o `api.js` deve reler o cookie `csrftoken` (o token antigo dá 403 no logout — verificado em `test_login_rotates_csrf_token`).
  - O proxy `/api` deve enviar `X-Forwarded-For` (`xfwd: true`) para o throttle funcionar por cliente (ver QA-T1-01).
  - Requisições sem sessão retornam **403** (não 401) — tratar ambos como "redirecionar para login".
  - O login só aceita JSON (`JSONParser`); form-urlencoded retorna 415.

## Observações / melhorias sugeridas

- Cobertura 97% (≥ 85%). O bloco `if not DEBUG` do settings só é medido em subprocesso; não afeta a meta.
- O projeto não é um repositório git ainda; o `.gitignore` está correto (`back/.env`, `back/venv/`, `back/db.sqlite3` etc.), mas vale `git init` + conferir `git status` antes do primeiro commit.
- `check --deploy` limpo com `DEBUG=False`. Em produção, lembrar de ajustar `CSRF_TRUSTED_ORIGINS` para a origem HTTPS real.
- Considerar log de tentativas de login falhas (sem a senha) para auditoria.
- DoD desta tarefa: testes, cobertura, lint/format, segredos e `.env.example` OK; isolamento A x B ainda não aplicável (sem dados financeiros); **bloqueada por QA-T1-01 (ALTA) e QA-T1-02 (MÉDIA)**.

---

## Re-teste — 2026-10-06

**Status final:** APROVADO. Nenhum item ALTA ou MÉDIA aberto. Fica pendente um novo item BAIXA (QA-T1-05), que não bloqueia a entrega.

### Testes executados

| Comando | Resultado |
|---|---|
| `pytest --cov` (suíte completa) | **90 passaram, 1 falhou** (o teste que falha documenta o QA-T1-05, BAIXA). Cobertura de **97%**; `settings.py` fica em 84% por causa do bloco `if not DEBUG`, que é testado em subprocesso |
| `ruff check .` | OK |
| `black --check .` | OK (32 arquivos) |
| `python manage.py check` | OK (0 issues) |
| `python manage.py check --deploy` (`DEBUG=False` + `SECRET_KEY` forte) | OK (0 issues) |
| `python manage.py makemigrations --check --dry-run` | OK, "No changes detected" |

Os 72 testes do dev e do QA anterior passam, incluindo os dois testes que antes falhavam: `test_throttle_cannot_be_bypassed_with_spoofed_x_forwarded_for` e `test_admin_login_is_rate_limited`. Não há regressões.
Testes novos de re-teste: `back/accounts/tests/test_qa_retest.py` (19 testes: 18 passam e 1 documenta o QA-T1-05).

### Verificação por item

- **QA-T1-01 (ALTA): CORRIGIDO.**
  - Sem a variável no ambiente, `NUM_PROXIES` vale `0`, o que foi conferido em um subprocesso sem `NUM_PROXIES`.
  - Com `NUM_PROXIES=0`, variar o XFF (`7.7.7.i, 8.8.8.i`) não muda o balde: a 6ª tentativa recebe 429.
  - Com `NUM_PROXIES=1` e XFF no formato `"forjado, real"`, em que a parte forjada muda a cada requisição (`6.6.6.i, 200.10.10.10`), o resultado é 5×401 seguidos de 3×429. O contador usa o IP real.
  - Também com `NUM_PROXIES=1`: um XFF de vários saltos com espaços (`1.1.1.i,2.2.2.i ,  200.10.10.11`) é bloqueado na 6ª tentativa; sem XFF, o throttle volta a usar `REMOTE_ADDR`.
  - Quando chega o 429, nenhum cookie de sessão é criado, mesmo com a senha correta.
  - O `.env.example` documenta `NUM_PROXIES`, inclusive a exigência de o Django escutar só em 127.0.0.1 quando o valor for 1.
- **QA-T1-02 (MÉDIA): CORRIGIDO.**
  - Um POST em `/admin/login/` **sem CSRF** recebe 403 e não consome o balde: depois de 8×403, o login com CSRF válido retorna 302.
  - Com CSRF válido: 5 falhas e depois 429 com `Retry-After` > 0, sem `sessionid`, mesmo usando a senha correta.
  - O throttle do admin não pode ser contornado com XFF forjado (`NUM_PROXIES=0`). Com `NUM_PROXIES=1` ele usa o IP real, e outro cliente atrás do mesmo proxy continua conseguindo entrar.
  - O bloqueio é liberado depois da janela de 60 s (timer simulado).
  - Os baldes do admin e da API são independentes. `admin:index` sem login redireciona para o login sobrescrito. Um usuário sem `is_staff` não entra no admin.
- **QA-T1-03 (BAIXA): CORRIGIDO.** O admin aceita `ADMIN@example.com` e ` Admin@Example.COM ` (com CSRF). Uma senha errada com e-mail em caixa mista continua retornando 401 genérico. Há, porém, um efeito colateral (QA-T1-05, abaixo).
- **QA-T1-04 (BAIXA): CORRIGIDO.** `CACHE_BACKEND`/`CACHE_LOCATION` vêm do `.env`: com `FileBasedCache` em um diretório temporário, o cache grava e lê. Está documentado no `settings.py` e no `.env.example`.

### Ajustes para @backend-dev

- [x] **[BAIXA] QA-T1-05 (CORRIGIDO, ver "Re-teste 2"): login retorna 500 se existirem dois e-mails iguais com caixa diferente.**
  - Passos: criar `dup@example.com` via `create_user`, criar `DUP@example.com` com `User(email=...).save()` (o `save()` não normaliza, e o `unique` do SQLite diferencia maiúsculas) e fazer `POST /api/auth/login/` com `dup@example.com`.
  - Esperado: 200 ou 401 genérico. Obtido: **500** (`User.MultipleObjectsReturned` em `UserManager.get_by_natural_key`, porque o `ModelBackend` só trata `DoesNotExist`).
  - O caso só acontece com dados inseridos fora do manager ou do admin. Hoje o banco não tem e-mails em caixa mista, por isso a severidade é BAIXA.
  - Sugestão: normalizar o e-mail em `User.save()`/`clean()` e/ou criar uma `UniqueConstraint(Lower("email"))` (com migração). Outra opção é `get_by_natural_key` capturar `MultipleObjectsReturned` e convertê-lo em `DoesNotExist`. Arquivo: `back/accounts/models.py`, método `get_by_natural_key`.
  - Teste: `accounts/tests/test_qa_retest.py::test_case_duplicate_emails_do_not_crash_login`.

### Ajustes para @frontend-dev (Tarefa 4)

- O proxy `/api` precisa de `xfwd: true`, e o back deve rodar com `NUM_PROXIES=1` atrás do Express, com o Django escutando só em `127.0.0.1:8000`. Com `NUM_PROXIES=0` atrás do proxy, todos os clientes compartilhariam o IP `127.0.0.1` e um único atacante bloquearia o login de todos.

### Observações

- O admin 429 responde em `text/plain` em vez de uma página HTML; para o admin isso é aceitável.
- As tentativas bem-sucedidas também contam no throttle do admin (5 logins por minuto por IP). Esse comportamento é consistente com a API.

## Re-teste 2 — 2026-10-06 (QA-T1-05, junto com a Tarefa 2)

**Status final:** APROVADO. Não há itens abertos na Tarefa 1.

- **QA-T1-05 (BAIXA): CORRIGIDO.**
  - `User.save()` normaliza o e-mail (strip + minúsculas). A migração `accounts/0002` normaliza os registros existentes e cria `UniqueConstraint(Lower("email"))`.
  - `get_by_natural_key` trata `MultipleObjectsReturned`: nesse caso, só aceita o e-mail normalizado exato.
- O teste `test_case_duplicate_emails_do_not_crash_login` foi substituído, porque o cenário dele (gravar um duplicado via `save()`) deixou de ser possível. No lugar entraram:
  - `test_case_duplicate_email_cannot_be_created`: `save()`, `bulk_create` e `update()` com um duplicado por caixa geram `IntegrityError`. Nos dois últimos, que não passam pelo `save()`, quem barra é a constraint do banco.
  - `test_save_normalizes_email`.
  - Dados legados: o índice `Lower(email)` é removido via `DROP INDEX` dentro da transação do teste e os e-mails são gravados sem normalizar.
    - `test_legacy_case_duplicates_login_uses_exact_normalized_email`: login com `dup@example.com` e com ` Dup@Example.COM ` retorna 200 com o registro exato.
    - `test_legacy_case_duplicates_without_exact_match_return_401_not_500`: quando nenhum registro é o e-mail exato, o login retorna 401 genérico, não 500.
    - `test_legacy_case_duplicates_admin_login_does_not_crash`: o admin retorna 302.
- Suíte completa: **391 passaram, 0 falharam**, cobertura de 98%. `ruff`, `black --check`, `check`, `check --deploy` e `makemigrations --check` estão OK.
