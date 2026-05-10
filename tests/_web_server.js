// Tiny static server for the web/ directory.
// ESM modules can't be loaded from file:// (CORS), so the smoke and e2e
// tests serve web/ over an ephemeral http://127.0.0.1:<port>/ instead.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
};

function startServer(rootDir) {
  const root = path.resolve(rootDir);
  const server = http.createServer((req, res) => {
    let urlPath;
    try {
      urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    } catch (_) {
      res.writeHead(400); res.end('bad url'); return;
    }
    let filePath = path.normalize(path.join(root, urlPath));
    if (!filePath.startsWith(root)) {
      res.writeHead(403); res.end('forbidden'); return;
    }
    fs.stat(filePath, (statErr, stat) => {
      if (statErr) { res.writeHead(404); res.end('not found'); return; }
      if (stat.isDirectory()) filePath = path.join(filePath, 'index.html');
      fs.readFile(filePath, (err, data) => {
        if (err) { res.writeHead(404); res.end('not found'); return; }
        const ext = path.extname(filePath).toLowerCase();
        res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
        res.end(data);
      });
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({
        url: `http://127.0.0.1:${port}/`,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}

module.exports = { startServer };
