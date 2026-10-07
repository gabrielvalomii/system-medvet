import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import dotenv from 'dotenv';
import express from 'express';
import helmet from 'helmet';
import compression from 'compression';
import { createApiProxy } from './proxy.js';

dotenv.config({ quiet: true });

const rootDir = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(rootDir, 'public');
const chartDir = path.join(rootDir, 'node_modules', 'chart.js', 'dist');

const DEFAULT_API_URL = 'http://127.0.0.1:8000';
const DEFAULT_PORT = 3000;

const cspDirectives = {
  defaultSrc: ["'self'"],
  scriptSrc: ["'self'"],
  styleSrc: ["'self'"],
  imgSrc: ["'self'", 'data:'],
  fontSrc: ["'self'"],
  connectSrc: ["'self'"],
  objectSrc: ["'none'"],
  baseUri: ["'self'"],
  formAction: ["'self'"],
  frameAncestors: ["'none'"],
  upgradeInsecureRequests: null,
};

export function createApp({ apiUrl = process.env.API_URL || DEFAULT_API_URL, proxyTimeout } = {}) {
  const app = express();
  app.disable('x-powered-by');

  app.use(
    helmet({
      contentSecurityPolicy: { useDefaults: false, directives: cspDirectives },
    }),
  );

  // Proxy before compression/static so API bodies are streamed untouched.
  app.use(createApiProxy(apiUrl, { timeout: proxyTimeout }));

  app.use(compression());
  app.use('/vendor/chart.js', express.static(chartDir));
  app.use(express.static(publicDir, { extensions: ['html'] }));

  app.use((req, res) => {
    res.status(404).sendFile(path.join(publicDir, '404.html'));
  });

  return app;
}

function isMainModule() {
  return Boolean(process.argv[1]) && import.meta.url === pathToFileURL(process.argv[1]).href;
}

if (isMainModule()) {
  const port = Number(process.env.PORT) || DEFAULT_PORT;
  const apiUrl = process.env.API_URL || DEFAULT_API_URL;
  createApp({ apiUrl }).listen(port, () => {
    console.log(`Front em http://localhost:${port} (API: ${apiUrl})`);
  });
}
