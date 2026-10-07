// QA (2026-10-08) — proxy /api (proxy.js): segurança e casos de borda com requisições cruas.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { createHash } from 'node:crypto';
import { createApp } from '../server.js';

let upstream;
let front;
let frontPort;
const seen = [];
let aborted = 0;

/** Fake API: echoes method, url, headers and a hash of the body. */
function startUpstream() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const chunks = [];
      req.on('data', (chunk) => chunks.push(chunk));
      // Upstream response closed before being finished = proxy aborted the request.
      res.on('close', () => {
        if (req.url === '/api/hang/' && !res.writableFinished) aborted += 1;
      });
      req.on('end', () => {
        if (req.url === '/api/hang/') return; // never answers
        const body = Buffer.concat(chunks);
        seen.push({ url: req.url, headers: req.headers });
        if (req.url === '/api/banner/') {
          res.setHeader('Server', 'WSGIServer/0.2 CPython/3.14.4');
          res.setHeader('X-Powered-By', 'Django');
        }
        res.writeHead(200, {
          'Content-Type': 'application/json; charset=utf-8',
          Connection: 'keep-alive, X-Up-Secret',
          'X-Up-Secret': 'nao-repassar',
          'Proxy-Authenticate': 'Basic',
        });
        res.end(
          req.method === 'HEAD'
            ? undefined
            : JSON.stringify({
                method: req.method,
                url: req.url,
                headers: req.headers,
                length: body.length,
                sha: createHash('sha256').update(body).digest('hex'),
                text: body.length < 4096 ? body.toString('utf8') : null,
              }),
        );
      });
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

/** Sends raw bytes and returns { status, headers (lowercase), body }. */
function raw(head, payload) {
  return new Promise((resolve, reject) => {
    const socket = net.connect(frontPort, '127.0.0.1', () => {
      socket.write(head);
      if (payload) socket.write(payload);
    });
    const chunks = [];
    socket.on('data', (chunk) => chunks.push(chunk));
    socket.on('error', reject);
    socket.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8');
      const split = text.indexOf('\r\n\r\n');
      const lines = text.slice(0, split).split('\r\n');
      const headers = {};
      for (const line of lines.slice(1)) {
        const i = line.indexOf(':');
        const key = line.slice(0, i).trim().toLowerCase();
        const value = line.slice(i + 1).trim();
        headers[key] = headers[key] ? [].concat(headers[key], value) : value;
      }
      let body = text.slice(split + 4);
      if (headers['transfer-encoding'] === 'chunked') body = dechunk(body);
      resolve({ status: Number(lines[0].split(' ')[1]), headers, body });
    });
  });
}

/** Decodes a chunked body (enough for these tests). */
function dechunk(text) {
  const bytes = Buffer.from(text, 'utf8');
  const out = [];
  let pos = 0;
  for (;;) {
    const eol = bytes.indexOf('\r\n', pos);
    const size = parseInt(bytes.subarray(pos, eol).toString(), 16);
    if (!size) break;
    out.push(bytes.subarray(eol + 2, eol + 2 + size));
    pos = eol + 2 + size + 2;
  }
  return Buffer.concat(out).toString('utf8');
}

const get = (path, extra = '') =>
  raw(`GET ${path} HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\n${extra}\r\n`);

before(async () => {
  upstream = await startUpstream();
  const app = createApp({ apiUrl: `http://127.0.0.1:${upstream.address().port}` });
  front = http.createServer(app);
  await new Promise((resolve) => front.listen(0, '127.0.0.1', resolve));
  frontPort = front.address().port;
});

after(() => {
  front.close();
  upstream.close();
});

test('path traversal via /api não serve arquivos do front nem sai do /api', async () => {
  const paths = [
    '/api/../server.js',
    '/api/%2e%2e/server.js',
    '/api/%2e%2e/%2e%2e/front/.env',
    '/api/..%2fproxy.js',
    '/api/%5c..%5cserver.js',
    '/%2e%2e/server.js',
    '/server.js',
    '/proxy.js',
    '/.env',
    '/package.json',
  ];
  for (const path of paths) {
    const res = await get(path);
    assert.doesNotMatch(
      res.body,
      /createApiProxy|createApp|API_URL=|E2E_PASSWORD|"dependencies"/,
      path,
    );
    if (path.startsWith('/api/')) {
      // Repassado literalmente para a API (que só conhece rotas /api/...).
      assert.equal(seen.at(-1).url, path, path);
    } else {
      assert.equal(res.status, 404, path);
    }
  }
});

test('URLs absolutas ou com // não são tratadas como /api (sem proxy aberto)', async () => {
  const before = seen.length;
  for (const path of ['http://evil.example/api/x/', '//evil.example/api/x/', '/x/../api/x/']) {
    const res = await get(path);
    assert.equal(res.status, 404, path);
  }
  assert.equal(seen.length, before);
});

test('query com caracteres especiais chega intacta', async () => {
  const query = '/api/q/?a=%C3%A7&b=1%2B2&c=a%20b&d=%26%3D%23&e=%3Cx%3E&f=+&g=%25';
  const res = await get(query);
  assert.equal(JSON.parse(res.body).url, query);
});

test('X-Forwarded-For forjado (inclusive em várias linhas) termina com o IP real do socket', async () => {
  const res = await get(
    '/api/xff/',
    'X-Forwarded-For: 6.6.6.6\r\nX-Forwarded-For: 7.7.7.7, 8.8.8.8\r\nX-Forwarded-Proto: https\r\n',
  );
  const xff = JSON.parse(res.body)
    .headers['x-forwarded-for'].split(',')
    .map((ip) => ip.trim());
  assert.equal(xff.at(-1), '127.0.0.1');
  assert.deepEqual(xff.slice(0, -1), ['6.6.6.6', '7.7.7.7', '8.8.8.8']);
});

test('Connection: X-Foo remove X-Foo e demais hop-by-hop; headers fim a fim seguem', async () => {
  const res = await get(
    '/api/hop/',
    'Connection: X-Foo, close\r\nX-Foo: segredo\r\nX-Bar: ok\r\nKeep-Alive: 5\r\nTE: trailers\r\n' +
      'Upgrade: h2c\r\nProxy-Authorization: Basic eDp5\r\nProxy-Connection: keep-alive\r\n',
  );
  const received = JSON.parse(res.body).headers;
  for (const name of [
    'x-foo',
    'keep-alive',
    'te',
    'upgrade',
    'proxy-authorization',
    'proxy-connection',
  ]) {
    assert.equal(received[name], undefined, name);
  }
  assert.equal(received['x-bar'], 'ok');
  assert.equal(received.host, 'localhost:3000');
  // Resposta: hop-by-hop da API não vaza para o cliente.
  assert.equal(res.headers['x-up-secret'], undefined);
  assert.equal(res.headers['proxy-authenticate'], undefined);
});

test('corpo de 100 KB (binário) e corpo chunked chegam íntegros', async () => {
  const big = Buffer.alloc(100 * 1024);
  for (let i = 0; i < big.length; i += 1) big[i] = i % 251;
  const res = await raw(
    `POST /api/big/ HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\n` +
      `Content-Type: application/octet-stream\r\nContent-Length: ${big.length}\r\n\r\n`,
    big,
  );
  const echo = JSON.parse(res.body);
  assert.equal(echo.length, big.length);
  assert.equal(echo.sha, createHash('sha256').update(big).digest('hex'));

  const chunked = await raw(
    'POST /api/ch/ HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\nTransfer-Encoding: chunked\r\n\r\n',
    '4\r\nCção\r\n0\r\n\r\n'.replace('4', String(Buffer.byteLength('Cção'))),
  );
  assert.equal(JSON.parse(chunked.body).text, 'Cção');
});

test('corpo UTF-8 (acentos, emoji, CJK) chega intacto', async () => {
  const body = Buffer.from(JSON.stringify({ d: 'Ção ✓ 日本 😀' }), 'utf8');
  const res = await raw(
    `POST /api/u/ HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\n` +
      `Content-Type: application/json; charset=utf-8\r\nContent-Length: ${body.length}\r\n\r\n`,
    body,
  );
  assert.deepEqual(JSON.parse(JSON.parse(res.body).text), { d: 'Ção ✓ 日本 😀' });
});

test('CL + TE conflitantes são rejeitados antes de chegar à API (sem smuggling)', async () => {
  const before = seen.length;
  const res = await raw(
    'POST /api/s/ HTTP/1.1\r\nHost: localhost:3000\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n' +
      'Connection: close\r\n\r\n0\r\n\r\nGET /api/smuggled/ HTTP/1.1\r\nHost: x\r\n\r\n',
  );
  assert.equal(res.status, 400);
  assert.ok(!seen.slice(before).some((r) => r.url === '/api/smuggled/'));
});

test('OPTIONS e HEAD são repassados (HEAD sem corpo)', async () => {
  const options = await raw(
    'OPTIONS /api/o/ HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\n\r\n',
  );
  assert.equal(JSON.parse(options.body).method, 'OPTIONS');
  const head = await raw(
    'HEAD /api/h/ HTTP/1.1\r\nHost: localhost:3000\r\nConnection: close\r\n\r\n',
  );
  assert.equal(head.status, 200);
  assert.equal(head.body, '');
  assert.equal(seen.at(-1).url, '/api/h/');
});

test('cliente que desiste aborta a requisição na API', async () => {
  const start = aborted;
  await new Promise((resolve) => {
    const socket = net.connect(frontPort, '127.0.0.1', () => {
      socket.write('GET /api/hang/ HTTP/1.1\r\nHost: localhost:3000\r\n\r\n');
      setTimeout(() => {
        socket.destroy();
        resolve();
      }, 150);
    });
  });
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert.equal(aborted, start + 1);
});

// Re-teste QA-F-05 / QA-F-06 (2026-10-08)
test('QA-F-05: X-Forwarded-Host/Proto/Port forjados (várias linhas, caixa mista) são sobrescritos', async () => {
  const res = await get(
    '/api/xfh/',
    'X-Forwarded-Host: evil.example\r\nx-forwarded-host: evil2.example\r\n' +
      'X-FORWARDED-PROTO: https\r\nX-Forwarded-Proto: https\r\nX-Forwarded-Port: 443\r\n' +
      'Forwarded: for=6.6.6.6;host=evil.example;proto=https\r\nX-Real-IP: 6.6.6.6\r\n',
  );
  const received = JSON.parse(res.body).headers;
  assert.equal(received['x-forwarded-host'], 'localhost:3000');
  assert.equal(received['x-forwarded-proto'], 'http');
  assert.equal(received['x-forwarded-port'], '3000');
  assert.equal(received.forwarded, undefined);
  assert.equal(received['x-real-ip'], undefined);
});

test('QA-F-05: HTTP/1.0 sem Host não repassa X-Forwarded-Host forjado', async () => {
  const res = await raw(
    'GET /api/nohost/ HTTP/1.0\r\nX-Forwarded-Host: evil.example\r\nX-Forwarded-Proto: https\r\n\r\n',
  );
  assert.equal(res.status, 200);
  const received = JSON.parse(res.body).headers;
  assert.notEqual(received['x-forwarded-host'], 'evil.example');
  assert.equal(received['x-forwarded-proto'], 'http');
});

test('QA-F-06: Server e X-Powered-By da API não chegam ao cliente', async () => {
  const res = await get('/api/banner/');
  assert.equal(res.status, 200);
  assert.equal(res.headers.server, undefined);
  assert.equal(res.headers['x-powered-by'], undefined);
});
