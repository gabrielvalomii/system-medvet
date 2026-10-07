// Minimal reverse proxy for /api built on node:http (no business logic, no body parsing).
import http from 'node:http';
import https from 'node:https';

const DEFAULT_TIMEOUT_MS = 30_000;

// RFC 9110 §7.6.1: hop-by-hop headers are never forwarded.
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'proxy-connection',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

const UNAVAILABLE = {
  status: 502,
  detail: 'Servidor da API indisponível. Tente novamente em instantes.',
};
const TIMEOUT = { status: 504, detail: 'O servidor demorou para responder. Tente novamente.' };

/** Matches /api and /api/... only (not /apiary). */
export function isApiPath(pathname) {
  return pathname === '/api' || pathname.startsWith('/api/');
}

/** Copies headers, dropping hop-by-hop ones (including those listed in Connection). */
export function stripHopByHop(headers) {
  const listed = String(headers.connection || '')
    .split(',')
    .map((name) => name.trim().toLowerCase())
    .filter(Boolean);
  const result = {};
  for (const [name, value] of Object.entries(headers)) {
    const key = name.toLowerCase();
    if (!HOP_BY_HOP.has(key) && !listed.includes(key)) result[key] = value;
  }
  return result;
}

function appendHeader(current, value) {
  return current ? `${current},${value}` : value;
}

function hostPort(req, encrypted) {
  const match = /:(\d+)$/.exec(req.headers.host || '');
  if (match) return match[1];
  return encrypted ? '443' : '80';
}

// Client-supplied forwarding headers that must never reach the API as-is:
// this proxy is the edge, so only it may describe the original connection.
const UNTRUSTED_FORWARDING = ['forwarded', 'x-real-ip'];

// Response headers from the API that only reveal its stack/version.
const HIDDEN_RESPONSE = ['server', 'x-powered-by'];

/**
 * X-Forwarded-For is appended (the API trusts its last hop, NUM_PROXIES=1);
 * Host/Proto/Port are overwritten with the real connection values.
 */
function forwardedHeaders(req, headers) {
  const encrypted = Boolean(req.socket?.encrypted);
  for (const name of UNTRUSTED_FORWARDING) delete headers[name];
  headers['x-forwarded-for'] = appendHeader(headers['x-forwarded-for'], req.socket.remoteAddress);
  headers['x-forwarded-port'] = hostPort(req, encrypted);
  headers['x-forwarded-proto'] = encrypted ? 'https' : 'http';
  if (req.headers.host) headers['x-forwarded-host'] = req.headers.host;
  else delete headers['x-forwarded-host'];
  return headers;
}

/** Response headers sent back to the client (no hop-by-hop, no server banner). */
function responseHeaders(headers) {
  const result = stripHopByHop(headers);
  for (const name of HIDDEN_RESPONSE) delete result[name];
  return result;
}

function sendError(res, { status, detail }) {
  // Never leak internal details (host/port of the API) to the client.
  if (res.headersSent) {
    res.destroy();
    return;
  }
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ detail }));
}

/**
 * Express middleware that streams /api/* requests to `target`, keeping
 * path, query, method, original Host (CSRF Origin check) and body untouched.
 */
export function createApiProxy(target, { timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const base = new URL(target);
  const client = base.protocol === 'https:' ? https : http;

  return function apiProxy(req, res, next) {
    const url = req.originalUrl || req.url;
    if (!isApiPath(url.split('?')[0])) return next();

    const proxyReq = client.request({
      protocol: base.protocol,
      hostname: base.hostname,
      port: base.port,
      method: req.method,
      path: url,
      headers: forwardedHeaders(req, stripHopByHop(req.headers)),
    });

    let failure = UNAVAILABLE;
    proxyReq.setTimeout(timeout, () => {
      failure = TIMEOUT;
      proxyReq.destroy(new Error('timeout'));
    });
    proxyReq.on('error', () => sendError(res, failure));

    proxyReq.on('response', (proxyRes) => {
      res.writeHead(proxyRes.statusCode, responseHeaders(proxyRes.headers));
      proxyRes.pipe(res);
      proxyRes.on('error', () => res.destroy());
    });

    // Client gave up: abort the upstream request too.
    res.on('close', () => {
      if (!res.writableFinished) proxyReq.destroy();
    });

    req.pipe(proxyReq);
  };
}
