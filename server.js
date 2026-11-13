// Companion AI CRUD server — no dependencies. Run: node server.js
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const PORT = process.env.PORT || 3000;
const DATA_FILE = path.join(__dirname, 'data.json');
const INDEX_FILE = path.join(__dirname, 'index.html');

// ---- Storage (JSON file) ----
function load() {
  try { return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8')); }
  catch { return []; }
}
function save(items) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(items, null, 2));
}

// ---- Helpers ----
function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(body === undefined ? '' : JSON.stringify(body));
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', chunk => {
      data += chunk;
      if (data.length > 1e6) { reject(new Error('Body too large')); req.destroy(); }
    });
    req.on('end', () => {
      try { resolve(data ? JSON.parse(data) : {}); }
      catch { reject(new Error('Invalid JSON')); }
    });
  });
}
// Keep only known fields, with sane types and limits
function clean(input) {
  const str = (v, max) => String(v ?? '').trim().slice(0, max);
  return {
    name: str(input.name, 60),
    avatar: str(input.avatar, 8),
    role: str(input.role, 30) || 'Friend',
    personality: str(input.personality, 30) || 'Friendly',
    description: str(input.description, 1000),
    active: input.active === undefined ? true : !!input.active,
  };
}

// ---- Routes ----
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const match = url.pathname.match(/^\/api\/companions(?:\/([\w-]+))?\/?$/);

  try {
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return fs.createReadStream(INDEX_FILE).pipe(res);
    }

    if (!match) return send(res, 404, { error: 'Not found' });
    const id = match[1];
    const items = load();

    // List
    if (req.method === 'GET' && !id) return send(res, 200, items);

    // Read one
    if (req.method === 'GET' && id) {
      const item = items.find(c => c.id === id);
      return item ? send(res, 200, item) : send(res, 404, { error: 'Companion not found' });
    }

    // Create
    if (req.method === 'POST' && !id) {
      const data = clean(await readBody(req));
      if (!data.name) return send(res, 400, { error: 'Name is required' });
      const now = Date.now();
      const item = { id: crypto.randomUUID(), ...data, createdAt: now, updatedAt: now };
      items.push(item);
      save(items);
      return send(res, 201, item);
    }

    // Update
    if ((req.method === 'PUT' || req.method === 'PATCH') && id) {
      const idx = items.findIndex(c => c.id === id);
      if (idx === -1) return send(res, 404, { error: 'Companion not found' });
      const body = await readBody(req);
      const data = clean({ ...items[idx], ...body });
      if (!data.name) return send(res, 400, { error: 'Name is required' });
      items[idx] = { ...items[idx], ...data, updatedAt: Date.now() };
      save(items);
      return send(res, 200, items[idx]);
    }

    // Delete
    if (req.method === 'DELETE' && id) {
      const next = items.filter(c => c.id !== id);
      if (next.length === items.length) return send(res, 404, { error: 'Companion not found' });
      save(next);
      return send(res, 204);
    }

    send(res, 405, { error: 'Method not allowed' });
  } catch (err) {
    send(res, 400, { error: err.message });
  }
});

server.listen(PORT, () => {
  console.log(`Companion AI running at http://localhost:${PORT}`);
});
