import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import request from 'supertest';
import { createApp } from '../server.js';

let fakeApi;
let apiUrl;
let app;

/** Fake Django: echoes what it received so we can assert on the proxied request. */
function startFakeApi() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let body = '';
      req.on('data', (chunk) => (body += chunk));
      req.on('end', () => {
        if (req.url === '/api/auth/logout/') {
          res.writeHead(204);
          res.end();
          return;
        }
        if (req.url === '/api/slow/') return; // never answers (timeout test)
        if (req.url === '/api/cookies/') {
          res.writeHead(200, {
            'Content-Type': 'application/json',
            'Set-Cookie': ['sessionid=s1; HttpOnly; Path=/', 'csrftoken=c1; Path=/'],
          });
          res.end('{}');
          return;
        }
        if (req.url === '/api/banner/') {
          res.writeHead(200, {
            'Content-Type': 'application/json',
            Server: 'WSGIServer/0.2 CPython/3.14.4',
            'X-Powered-By': 'Django',
          });
          res.end('{}');
          return;
        }
        if (req.url === '/api/hop/') {
          res.writeHead(200, {
            'Content-Type': 'application/json',
            Connection: 'keep-alive, X-Hop-Secret',
            'Keep-Alive': 'timeout=5',
            'X-Hop-Secret': 'nao-repassar',
            'X-End-To-End': 'ok',
          });
          res.end('{}');
          return;
        }
        res.writeHead(200, {
          'Content-Type': 'application/json',
          'Set-Cookie': 'csrftoken=abc123; Path=/; SameSite=Lax',
        });
        res.end(JSON.stringify({ method: req.method, url: req.url, headers: req.headers, body }));
      });
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

before(async () => {
  fakeApi = await startFakeApi();
  apiUrl = `http://127.0.0.1:${fakeApi.address().port}`;
  app = createApp({ apiUrl });
});

after(() => new Promise((resolve) => fakeApi.close(resolve)));

test('serve as páginas HTML', async () => {
  const pages = {
    '/': 'Entrar',
    '/index.html': 'Entrar',
    '/dashboard.html': 'Gastos por categoria',
    '/gastos.html': 'Adicionar gastos',
    '/rendimentos.html': 'Adicionar rendimentos',
  };
  for (const [path, text] of Object.entries(pages)) {
    const res = await request(app).get(path);
    assert.equal(res.status, 200, path);
    assert.match(res.headers['content-type'], /text\/html/);
    assert.ok(res.text.includes(text), `${path} deve conter "${text}"`);
  }
});

test('serve CSS e JS estáticos', async () => {
  const css = await request(app).get('/css/variables.css');
  assert.equal(css.status, 200);
  assert.match(css.text, /--bg: #0f1115/);
  const js = await request(app).get('/js/api.js');
  assert.equal(js.status, 200);
  assert.match(js.headers['content-type'], /javascript/);
});

test('aplica headers de segurança do helmet com CSP restrita', async () => {
  const res = await request(app).get('/');
  const csp = res.headers['content-security-policy'];
  assert.ok(csp, 'CSP ausente');
  for (const directive of [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
  ]) {
    assert.ok(csp.includes(directive), `CSP sem ${directive}`);
  }
  assert.ok(!csp.includes('unsafe-inline'), 'CSP não pode permitir unsafe-inline');
  assert.ok(!csp.includes('https:'), 'CSP não pode liberar CDN');
  assert.equal(res.headers['x-content-type-options'], 'nosniff');
  assert.equal(res.headers['x-powered-by'], undefined);
});

test('as páginas não usam scripts/estilos inline nem CDN', async () => {
  for (const path of ['/index.html', '/dashboard.html', '/gastos.html', '/rendimentos.html']) {
    const { text } = await request(app).get(path);
    assert.ok(!/<script(?![^>]*\ssrc=)[^>]*>/.test(text), `${path}: script inline`);
    assert.ok(!/<style[\s>]/.test(text), `${path}: <style> inline`);
    assert.ok(!/\sstyle="/.test(text), `${path}: atributo style`);
    assert.ok(!/\son[a-z]+="/.test(text), `${path}: handler inline`);
    assert.ok(!/(src|href)="https?:\/\//.test(text), `${path}: recurso externo`);
  }
});

test('expõe o Chart.js local em /vendor/chart.js', async () => {
  const res = await request(app).get('/vendor/chart.js/chart.umd.min.js');
  assert.equal(res.status, 200);
  assert.match(res.headers['content-type'], /javascript/);
  assert.ok(res.text.length > 1000);
});

test('arquivo inexistente em /vendor/chart.js retorna 404', async () => {
  const res = await request(app).get('/vendor/chart.js/nao-existe.js');
  assert.equal(res.status, 404);
});

test('rota desconhecida retorna 404 em HTML', async () => {
  const res = await request(app).get('/nao-existe');
  assert.equal(res.status, 404);
  assert.match(res.text, /Página não encontrada/);
});

test('proxy de /api preserva caminho, query, Host e envia X-Forwarded-For', async () => {
  const res = await request(app)
    .get('/api/expenses/?month=2026-10')
    .set('Host', 'localhost:3000')
    .set('Cookie', 'sessionid=xyz; csrftoken=abc');
  assert.equal(res.status, 200);
  assert.equal(res.body.url, '/api/expenses/?month=2026-10');
  assert.equal(res.body.headers.host, 'localhost:3000', 'Host deve ser preservado (CSRF)');
  assert.ok(res.body.headers['x-forwarded-for'], 'X-Forwarded-For ausente');
  assert.equal(res.body.headers.cookie, 'sessionid=xyz; csrftoken=abc');
  assert.match(res.headers['set-cookie'][0], /csrftoken=abc123/);
});

test('proxy encaminha método, corpo JSON e headers de CSRF', async () => {
  const payload = { email: 'qa@example.com', password: 'x' };
  const res = await request(app)
    .post('/api/auth/login/')
    .set('Origin', 'http://localhost:3000')
    .set('X-CSRFToken', 'abc')
    .send(payload);
  assert.equal(res.status, 200);
  assert.equal(res.body.method, 'POST');
  assert.equal(res.body.url, '/api/auth/login/');
  assert.deepEqual(JSON.parse(res.body.body), payload);
  assert.equal(res.body.headers['x-csrftoken'], 'abc');
  assert.equal(res.body.headers.origin, 'http://localhost:3000');
});

test('proxy repassa 204 sem corpo', async () => {
  const res = await request(app).post('/api/auth/logout/');
  assert.equal(res.status, 204);
  assert.equal(res.text, '');
});

test('não encaminha caminhos que só começam com "api" fora de /api', async () => {
  const res = await request(app).get('/apiary');
  assert.equal(res.status, 404);
  assert.match(res.text, /Página não encontrada/);
});

test('API fora do ar retorna 502 em JSON sem vazar detalhes', async () => {
  const offline = createApp({ apiUrl: 'http://127.0.0.1:1' });
  const res = await request(offline).get('/api/auth/me/');
  assert.equal(res.status, 502);
  assert.match(res.headers['content-type'], /application\/json/);
  assert.match(res.body.detail, /indisponível/);
  assert.ok(!JSON.stringify(res.body).includes('127.0.0.1'));
});

test('proxy repassa múltiplos Set-Cookie', async () => {
  const res = await request(app).get('/api/cookies/');
  assert.equal(res.status, 200);
  assert.deepEqual(res.headers['set-cookie'], [
    'sessionid=s1; HttpOnly; Path=/',
    'csrftoken=c1; Path=/',
  ]);
});

test('proxy repassa corpo JSON de POST/PUT intacto (UTF-8) e Content-Type', async () => {
  const payload = { category: 'outros', amount: '1234.56', description: 'Ção & "aspas" <b>' };
  for (const method of ['post', 'put']) {
    const res = await request(app)[method]('/api/expenses/1/?x=1').send(payload);
    assert.equal(res.status, 200);
    assert.equal(res.body.method, method.toUpperCase());
    assert.equal(res.body.url, '/api/expenses/1/?x=1');
    assert.match(res.body.headers['content-type'], /application\/json/);
    assert.deepEqual(JSON.parse(res.body.body), payload);
  }
});

test('proxy anexa o IP do cliente ao X-Forwarded-For existente e define Proto/Host/Port', async () => {
  const res = await request(app)
    .get('/api/auth/me/')
    .set('Host', 'localhost:3000')
    .set('X-Forwarded-For', '203.0.113.7');
  const { headers } = res.body;
  assert.match(
    headers['x-forwarded-for'],
    /^203\.0\.113\.7,(::ffff:)?127\.0\.0\.1$|^203\.0\.113\.7,::1$/,
  );
  assert.equal(headers['x-forwarded-proto'], 'http');
  assert.equal(headers['x-forwarded-port'], '3000');
  assert.equal(headers['x-forwarded-host'], 'localhost:3000');
});

test('proxy sobrescreve X-Forwarded-Host/Proto/Port e descarta Forwarded/X-Real-IP do cliente', async () => {
  const res = await request(app)
    .get('/api/auth/me/')
    .set('Host', 'localhost:3000')
    .set('X-Forwarded-For', '203.0.113.7')
    .set('X-Forwarded-Host', 'evil.example')
    .set('X-Forwarded-Proto', 'https')
    .set('X-Forwarded-Port', '443')
    .set('X-Real-IP', '6.6.6.6')
    .set('Forwarded', 'for=6.6.6.6;host=evil.example;proto=https');
  const { headers } = res.body;
  assert.equal(headers['x-forwarded-host'], 'localhost:3000');
  assert.equal(headers['x-forwarded-proto'], 'http');
  assert.equal(headers['x-forwarded-port'], '3000');
  assert.equal(headers['x-real-ip'], undefined);
  assert.equal(headers.forwarded, undefined);
  assert.match(headers['x-forwarded-for'], /^203\.0\.113\.7,/);
});

test('proxy não expõe Server/X-Powered-By da API', async () => {
  const res = await request(app).get('/api/banner/');
  assert.equal(res.status, 200);
  assert.equal(res.headers.server, undefined);
  assert.equal(res.headers['x-powered-by'], undefined);
});

test('proxy remove headers hop-by-hop na requisição e na resposta', async () => {
  const res = await request(app)
    .get('/api/auth/me/')
    .set('Connection', 'keep-alive, X-Client-Hop')
    .set('Keep-Alive', 'timeout=5')
    .set('X-Client-Hop', 'nao-repassar')
    .set('Proxy-Authorization', 'Basic abc')
    .set('TE', 'trailers');
  const { headers } = res.body;
  for (const name of ['keep-alive', 'x-client-hop', 'proxy-authorization', 'te']) {
    assert.equal(headers[name], undefined, `${name} não deveria chegar à API`);
  }

  const hop = await request(app).get('/api/hop/');
  assert.equal(hop.status, 200);
  assert.equal(hop.headers['keep-alive'], undefined);
  assert.equal(hop.headers['x-hop-secret'], undefined);
  assert.equal(hop.headers['x-end-to-end'], 'ok');
});

test('proxy responde 504 em JSON quando a API não responde a tempo', async () => {
  const slow = createApp({ apiUrl, proxyTimeout: 100 });
  const res = await request(slow).get('/api/slow/');
  assert.equal(res.status, 504);
  assert.match(res.headers['content-type'], /application\/json/);
  assert.match(res.body.detail, /demorou/);
  assert.ok(!JSON.stringify(res.body).includes('127.0.0.1'));
});

test('respostas da API não são recomprimidas nem alteradas pelo compression', async () => {
  const res = await request(app).get('/api/auth/me/').set('Accept-Encoding', 'gzip');
  assert.equal(res.headers['content-encoding'], undefined);
});
