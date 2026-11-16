/* Teenindustöötaja (sw.js) vahemäluloogika test ilma brauserita: caches, fetch ja self on asendatud lihtsate mudelitega.
   Käivitamine: node tests/sw.test.js */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SRC = fs.readFileSync(path.join(path.dirname(__dirname), 'sw.js'), 'utf8');
const BASE = 'https://example.org/teatmik/';
const abs = (u) => new URL(typeof u === 'string' ? u : u.url, BASE + 'sw.js').href;

function makeEnv({ online = true } = {}) {
  const stores = new Map();
  const handlers = {};
  const net = { online, served: [] };
  const open = async (name) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const m = stores.get(name);
    return {
      put: async (k, r) => { m.set(abs(k), await r.text()); },
      addAll: async (list) => { for (const k of list) m.set(abs(k), 'install:' + k); },
      match: async (k, opt = {}) => {
        const want = abs(k);
        for (const [key, body] of m) {
          const same = opt.ignoreSearch ? key.split('?')[0] === want.split('?')[0] : key === want;
          if (same) return new Response(body);
        }
        return undefined;
      },
    };
  };
  const ctx = {
    URL, Response, Promise, setTimeout, clearTimeout, console,
    location: new URL(BASE + 'sw.js'),
    caches: { open, keys: async () => [...stores.keys()], delete: async (k) => stores.delete(k) },
    fetch: async (req) => {
      const u = abs(req);
      if (!net.online) throw new Error('võrguta');
      net.served.push(u);
      return new Response('net:' + u.replace(BASE, ''));
    },
    self: { addEventListener: (n, f) => { handlers[n] = f; }, skipWaiting() {}, clients: { claim: async () => {}, matchAll: async () => [] } },
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  const run = async (name, ev) => { let p; handlers[name](Object.assign({ waitUntil: (x) => { p = x; }, respondWith: (x) => { p = x; } }, ev)); return p; };
  const get = async (url, mode = 'no-cors') => { const r = await run('fetch', { request: { method: 'GET', url: abs(url), mode } }); return r ? r.text() : null; };
  const keys = (name) => [...(stores.get(name) || new Map()).keys()].map((k) => k.replace(BASE, '') || './');
  const shell = () => [...stores.keys()].find((k) => k.startsWith('teatmik-shell'));
  return { net, run, get, keys, shell, stores };
}

(async () => {
  let fail = 0;
  const check = (name, ok, extra = '') => { console.log((ok ? 'OK   ' : 'VIGA ') + name + (extra ? '  ' + extra : '')); if (!ok) fail++; };

  const e = makeEnv();
  await e.run('install', {});
  const shell = e.shell();
  check('paigaldamine: kest ja andmefail vahemälus', e.keys(shell).includes('app.js') && e.keys('teatmik-data-v1').includes('data/data.json'));
  const n0 = e.keys(shell).length;

  check('lehe avamine võrgus tuleb võrgust', (await e.get('./?k=j:puue&tab=noud', 'navigate')).startsWith('net:'));
  await e.get('./?q=holter', 'navigate');
  await e.get('index.html?q=ekg', 'navigate');
  check('eri aadressidega avamised ei lisa vahemällu koopiaid', e.keys(shell).length === n0, `kirjeid ${e.keys(shell).length}, enne ${n0}`);

  await e.get('lisad/pilt.png', 'navigate');
  check('uues aknas avatud pilt jääb oma aadressi alla', e.keys(shell).includes('lisad/pilt.png') && e.keys(shell).length === n0 + 1);

  e.net.online = false;
  const offPage = await e.get('./?k=s:6417', 'navigate');
  check('võrguta: leht tuleb vahemälust (viimati võrgust saadud koopia)', offPage === 'net:index.html?q=ekg', offPage);
  check('võrguta: pilt tuleb vahemälust', (await e.get('lisad/pilt.png')) === 'net:lisad/pilt.png');
  check('võrguta: app.js tuleb vahemälust', (await e.get('app.js')).includes('app.js'));
  check('võrguta: andmefail tuleb vahemälust', (await e.get('data/data.json')) === 'net:data/data.json');
  check('võrguta: version.json annab tühja objekti', (await e.get('data/version.json')) === '{}');
  check('võrguta: vahemälus puuduv fail annab vea, mitte lehe', (await (async () => { const r = await e.run('fetch', { request: { method: 'GET', url: abs('lisad/puudub.png'), mode: 'no-cors' } }); return r.type; })()) === 'error');

  e.net.online = true;
  check('andmefaili uus versioon (?v=) tuleb võrgust ja asendab vahemälu', (await e.get('data/data.json?v=2')) === 'net:data/data.json?v=2' && e.keys('teatmik-data-v1').length === 1);
  e.net.online = false;
  check('võrguta: vahemälus on andmefaili uus versioon', (await e.get('data/data.json')) === 'net:data/data.json?v=2');

  console.log(fail ? `\n${fail} kontrolli ebaõnnestus` : '\nKõik kontrollid läbitud');
  process.exit(fail ? 1 : 0);
})();
