/* Rakenduse suitsutest: index.html ja app.js jsdom-is päris andmefailiga (data/data.json).
   Kontrollib, et vaated renderduvad vigadeta, otsing, tagasiliikumine, otselingid ja andmete uuenemine töötavad.

   Käivitamine repo juurkaustast:
       npm ci --prefix tests
       node tests/smoke.js
   Töövoog käivitab selle ka värskelt ehitatud andmetega enne avaldamist. */
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');

const ROOT = path.dirname(__dirname);
const APP = fs.readFileSync(process.env.APP_JS || path.join(ROOT, 'app.js'), 'utf8'); // APP_JS: teise versiooni võrdluseks
const HTML = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8').replace('<script src="app.js"></script>', '');
const DATA_RAW = fs.readFileSync(path.join(ROOT, 'data', 'data.json'), 'utf8');
const VERSION_RAW = fs.readFileSync(path.join(ROOT, 'data', 'version.json'), 'utf8');
const DATA = JSON.parse(DATA_RAW);

const unhandled = [];
process.on('unhandledRejection', (e) => unhandled.push(String((e && e.message) || e)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* Käivitab rakenduse. files: aadress → vastuse tekst (null = võrguviga); võti "data/data.json?" on päring koos ?v=… osaga. */
async function boot({ search = '', files = {}, storage = {} } = {}) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => errors.push('jsdom: ' + e.message));
  vc.on('error', (...a) => errors.push('console.error: ' + a.map((x) => String((x && x.message) || x)).join(' ')));
  const dom = new JSDOM(HTML, { url: 'http://localhost/' + search, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: vc });
  const w = dom.window;
  for (const [k, v] of Object.entries(storage)) w.localStorage.setItem(k, v);
  const requests = [];
  w.fetch = async (url) => {
    const u = String(url);
    requests.push(u);
    const key = u.split('?')[0];
    let body = (u.includes('?') ? files[key + '?'] : undefined);
    if (body === undefined) body = files[key];
    if (body === undefined) body = key === 'data/data.json' ? DATA_RAW : key === 'data/version.json' ? VERSION_RAW : null;
    if (body === null) throw new Error('võrguta: ' + u);
    return { ok: true, json: async () => JSON.parse(body) };
  };
  w.scrollTo = () => {};
  w.Element.prototype.scrollIntoView = function () {};
  w.eval(APP);
  const res = () => w.document.querySelector('#results');
  for (let i = 0; i < 100 && /Laadin andmeid/.test(res().textContent); i++) await sleep(20);
  await sleep(60); // uuenduse kontroll (version.json) jõuab lõpuni
  const click = (el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const type = async (q) => { const i = w.document.querySelector('#q'); i.value = q; i.dispatchEvent(new w.Event('input', { bubbles: true })); await sleep(140); };
  const back = async () => { w.history.back(); await sleep(60); };
  const forward = async () => { w.history.forward(); await sleep(60); };
  const sections = () => res().querySelectorAll('section.section').length;
  const rows = () => res().querySelectorAll('article.row').length;
  const param = (k) => new w.URL(w.location.href).searchParams.get(k);
  const title = () => { const n = res().querySelector('article.row .name, article.row b'); return n ? n.textContent.trim() : ''; };
  return { w, errors, requests, res, click, type, back, forward, sections, rows, param, title, close: () => w.close() };
}

async function openRows(app, n) {
  for (let i = 0; i < n; i++) {
    const heads = app.res().querySelectorAll('button.head[data-open]');
    if (i >= heads.length) break;
    if (heads[i].getAttribute('aria-expanded') !== 'true') app.click(heads[i]);
  }
}
// Rikutud HTML-olem jääb lehele nähtava tekstina (nt „&#39;“); korras lehel selliseid tekstijuppe ei ole.
const literalEntities = (el) => (el.textContent.match(/&#\d+;|&(?:amp|lt|gt|quot);/g) || []);
const itemsOf = (t) => DATA.items.map((it, i) => [it, i]).filter(([it]) => it.t === t);

(async () => {
  let fail = 0;
  const check = (name, ok, extra = '') => { console.log((ok ? 'OK   ' : 'VIGA ') + name + (extra ? '  ' + extra : '')); if (!ok) fail++; };
  const noErr = (a) => (a.errors.length ? ' vead: ' + a.errors.slice(0, 2).join(' | ') : '');

  // ---------- 1. avaleht ja vahelehed
  for (const tab of ['', '?tab=rahastus', '?tab=noud', '?tab=kys', '?tab=rj']) {
    const a = await boot({ search: tab });
    check(`vaheleht „${tab || 'avaleht'}“ renderdub`, a.sections() > 0 && !/tekkis viga|Laadin andmeid/.test(a.res().textContent) && !a.errors.length, `${a.sections()} jaotist${noErr(a)}`);
    a.close();
  }

  // ---------- 2. otsingud ja kirjete avamine
  {
    const qs = ['holter', '6417', 'haigusleht', 'tonsilliit', 'IGRA', 'jalaortoos', '1966', 'raviarve', 'hüpertoonia', 'marevan', 'õe retsept', '7050', 'TSH', 'puude taotlemine', 'koloskoopia', 'ratastool', 'EEK-2', 'vaimse tervise õde', 'KNH', '9072'];
    const a = await boot();
    const empty = [];
    for (const q of qs) {
      await a.type(q);
      if (!a.rows() && !a.res().querySelector('.ycard')) empty.push(q);
      await openRows(a, 12);
    }
    check(`${qs.length} otsingut annavad vasteid ja kirjed avanevad vigadeta`, !empty.length && !a.errors.length, (empty.length ? 'vasteta: ' + empty.join(', ') : '') + noErr(a));
    a.close();
  }

  // ---------- 3. iga kategooria nimekiri ja kirjete detailvaated
  {
    const a = await boot();
    const filters = [...a.w.document.querySelectorAll('#chips [data-filter]')].map((c) => c.dataset.filter).filter((f) => f !== 'all');
    let opened = 0;
    for (const f of filters) {
      a.click(a.w.document.querySelector(`#chips [data-filter="${f}"]`));
      const before = a.res().querySelectorAll('button.head[aria-expanded="true"]').length;
      await openRows(a, 25);
      opened += a.res().querySelectorAll('button.head[aria-expanded="true"]').length - before;
    }
    for (const c of [...a.w.document.querySelectorAll('#chips [data-fund]')].map((x) => x.dataset.fund)) {
      a.click(a.w.document.querySelector(`#chips [data-fund="${c}"]`));
      await openRows(a, 10);
    }
    check(`kategooriate (${filters.join(', ')}) ja fondide nimekirjad: kirjed avanevad vigadeta`, opened > 50 && !a.errors.length, `${opened} avatud kirjet${noErr(a)}`);
    a.close();
  }

  // ---------- 4. kõik teemakaardid täisvaates (otselingiga võtme järgi)
  {
    const a = await boot();
    let n = 0;
    const bad = [];
    for (const [it] of itemsOf('j')) {
      a.w.history.pushState({ tab: 'avaleht', q: '', filter: 'all', fund: null, k: 'j:' + it.k }, '', '?k=' + encodeURIComponent('j:' + it.k));
      a.w.dispatchEvent(new a.w.PopStateEvent('popstate', { state: a.w.history.state }));
      const shown = a.res().querySelector('article.row');
      if (!shown || !a.res().textContent.includes(it.n)) bad.push(it.k); else n++;
    }
    check(`kõik ${itemsOf('j').length} teemakaarti avanevad täisvaates`, !bad.length && !a.errors.length, `${n} avatud${bad.length ? '; ei avanenud: ' + bad.join(', ') : ''}${noErr(a)}`);
    a.close();
  }

  // ---------- 5. esiletõst ei riku HTML-olemeid
  {
    const hit = itemsOf('j').find(([it]) => [...(it.r || []), ...(it.e || [])].some((r) => (r.s || '').includes("'")));
    if (hit) {
      const a = await boot({ search: '?k=' + encodeURIComponent('j:' + hit[0].k) });
      await a.type('39');
      const pin = a.res().querySelector('.pin');
      check('esiletõst: avatud kaart + otsing „39“ ei jäta lehele rikutud olemeid', !!pin && literalEntities(pin).length === 0 && !a.errors.length, noErr(a));
      a.close();
    } else console.log('     (ülakomaga teemakaarti andmetes ei ole, esiletõstu test jäi vahele)');
  }

  // ---------- 6. ajalugu: tagasiliikumine ja otselingid
  {
    const a = await boot();
    const home = a.res().innerHTML;
    const card = a.res().querySelector('button.qbtn.teema[data-focus]');
    const key = 'j:' + DATA.items[+card.dataset.focus].k;
    a.click(card);
    const focusHtml = a.res().innerHTML;
    check('kaardi avamine lisab aadressi võtme (?k=)', a.param('k') === key && a.res().querySelector('[data-act="home"]') != null, `k=${a.param('k')}`);
    await a.back();
    check('tagasi: kaardilt avalehele', a.param('k') == null && a.res().innerHTML === home && !a.errors.length, noErr(a));
    await a.forward();
    check('edasi: tagasi kaardile', a.param('k') === key && a.res().innerHTML === focusHtml);
    await a.back();
    await a.type('holter');
    const n1 = a.rows();
    await a.type('holter ekg');
    check('otsing on aadressis (?q=) ja trükkimine ei lisa ajalukku kirjeid', a.param('q') === 'holter ekg' && n1 > 0);
    await a.back();
    check('tagasi: otsingust avalehele ühe sammuga', a.param('q') == null && a.w.document.querySelector('#q').value === '' && a.res().innerHTML === home);
    a.click(a.w.document.querySelector('#tabs [data-tab="rahastus"]'));
    check('vahelehe vahetus on aadressis (?tab=)', a.param('tab') === 'rahastus');
    await a.back();
    check('tagasi: eelmisele vahelehele', a.param('tab') == null && a.res().innerHTML === home && !a.errors.length, noErr(a));
    a.close();

    // rakenduse enda nupud, mis viivad tagasi sinna, kust tuldi, ei kasvata ajalugu
    const b = await boot();
    const home2 = b.res().innerHTML;
    const len0 = b.w.history.length;
    await b.type('holter');
    b.click(b.w.document.querySelector('#clear'));
    await sleep(80);
    check('Tühjenda otsingust: avaleht, ajalukku ei lisandu kirjet', b.res().innerHTML === home2 && b.param('q') == null && b.w.history.length === len0 + 1 && b.w.history.state.prev == null, `ajaloo pikkus ${b.w.history.length} (algul ${len0})`);
    b.click(b.res().querySelector('button.qbtn.teema[data-focus]'));
    const kA = b.param('k');
    b.click(b.res().querySelector('[data-act="home"]'));
    await sleep(80);
    check('„← Avaleht“ kaardilt: avaleht, ajalukku ei lisandu kirjet', b.res().innerHTML === home2 && b.param('k') == null && b.w.history.length === len0 + 1, `ajaloo pikkus ${b.w.history.length}`);
    await b.forward();
    check('edasi pärast „← Avaleht“: sama kaart', b.param('k') === kA && !b.errors.length, noErr(b));
    // kaart → otsing (kaart jääb tulemuste alla lahti) → Tühjenda → tagasi samal kaardil
    await b.type('ekg');
    const pinned = !!b.res().querySelector('.pin');
    b.click(b.w.document.querySelector('#clear'));
    await sleep(80);
    check('kaart → otsing → Tühjenda: tagasi samal kaardil', pinned && b.param('k') === kA && b.param('q') == null && b.res().querySelector('[data-act="home"]') != null && !b.errors.length, noErr(b));
    await b.back();
    check('tagasi kaardilt: avaleht', b.res().innerHTML === home2 && !b.errors.length, noErr(b));
    b.close();

    const d = await boot({ search: '?k=' + encodeURIComponent('s:6417') });
    check('otselink ?k=s:6417 avab koodi täisvaates', d.res().textContent.includes('6417') && d.res().querySelector('[data-act="home"]') != null && !d.errors.length, noErr(d));
    d.close();
    const x = await boot({ search: '?k=' + encodeURIComponent('j:sellist-ei-ole') });
    check('tundmatu võtmega otselink avab avalehe', x.sections() > 0 && !x.errors.length, noErr(x));
    x.close();
  }

  // ---------- 7. püsivad võtmed: andmete uuenemine ei vaheta avatud kirjet
  {
    const fresh = JSON.parse(DATA_RAW);
    fresh.items.unshift({ t: 'k', id: 'test-uus-link', n: 'Testlink (nihutab kõigi kirjete indeksit)', u: 'https://example.org/', d: '' });
    fresh.meta.fingerprint = 'uus';
    const target = itemsOf('j')[3][0];
    const a = await boot({ search: '?k=' + encodeURIComponent('j:' + target.k), files: { 'data/version.json': JSON.stringify({ built: 'x', fingerprint: 'uus', checked: '2099-01-01' }), 'data/data.json?': JSON.stringify(fresh) } });
    await sleep(150);
    const loaded = a.requests.some((u) => u.startsWith('data/data.json?'));
    check('andmete uuenemisel jääb sama kirje avatuks', loaded && a.res().textContent.includes(target.n) && a.res().querySelector('[data-act="home"]') != null && a.param('k') === 'j:' + target.k && !a.errors.length, `uus andmefail laaditud: ${loaded}${noErr(a)}`);
    a.close();
  }

  // ---------- 8. kuvamisviga vana andmefailiga ei jäta rakendust kinni
  {
    const bad = JSON.parse(DATA_RAW);
    delete bad.items.find((x) => x.t === 'l').b; // indeksi ehitamine viskab vea
    bad.meta.fingerprint = 'vana';
    const good = JSON.parse(DATA_RAW);
    good.meta.fingerprint = 'uus';
    const a = await boot({ files: { 'data/data.json': JSON.stringify(bad), 'data/version.json': JSON.stringify({ built: 'x', fingerprint: 'uus' }), 'data/data.json?': JSON.stringify(good) } });
    await sleep(200);
    check('vigane vahemälu + uuem versioon olemas: rakendus taastub ise', a.sections() > 0 && !/tekkis viga/.test(a.res().textContent));
    a.close();
    const b = await boot({ files: { 'data/data.json': JSON.stringify(bad), 'data/version.json': JSON.stringify({ built: 'x', fingerprint: 'vana' }) } });
    check('vigane andmefail, uuemat ei ole: veateade ja nupp „Laadi uuesti“', /tekkis viga/.test(b.res().textContent) && !!b.res().querySelector('button[data-act="reload"]'));
    b.close();
    const c = await boot({ files: { 'data/version.json': null } });
    check('võrguta (version.json ei vasta): rakendus töötab olemasolevate andmetega', c.sections() > 0 && !c.errors.length, noErr(c));
    c.close();
  }

  // ---------- 9. kontrolli kuupäev ja vananemise hoiatus
  {
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const daysAgo = (n) => iso(new Date(Date.now() - n * 86400000));
    const old = JSON.parse(DATA_RAW);
    old.meta.date = daysAgo(120);
    const oldRaw = JSON.stringify(old);
    const ver = (checked) => JSON.stringify(Object.assign({ built: old.meta.built, fingerprint: old.meta.fingerprint }, checked ? { checked } : {}));
    const stale = await boot({ files: { 'data/data.json': oldRaw, 'data/version.json': ver(daysAgo(60)) } });
    check('kontrollist üle 45 päeva: avalehel hoiatus ja staatuses märge', !!stale.res().querySelector('#stale') && /vananenud/.test(stale.res().querySelector('#status').textContent) && !stale.errors.length, noErr(stale));
    stale.close();
    const ok = await boot({ files: { 'data/data.json': oldRaw, 'data/version.json': ver(daysAgo(2)) } });
    const st = ok.res().querySelector('#status').textContent;
    check('andmed vanad, kuid kontroll värske: hoiatust ei ole, staatuses mõlemad kuupäevad', !ok.res().querySelector('#stale') && /Andmed viimati muutusid/.test(st) && /Viimati kontrollitud/.test(st) && !/vananenud/.test(st) && !ok.errors.length, noErr(ok));
    ok.close();
    const off = await boot({ files: { 'data/data.json': oldRaw, 'data/version.json': null }, storage: { 'teatmik-checked': daysAgo(3) } });
    check('võrguta: kehtib seadmes meelde jäetud kontrolli kuupäev', !off.res().querySelector('#stale') && !off.errors.length, noErr(off));
    off.close();
  }

  if (unhandled.length) { console.log('VIGA käsitlemata vead: ' + unhandled.slice(0, 3).join(' | ')); fail++; }
  console.log(fail ? `\n${fail} kontrolli ebaõnnestus` : '\nKõik kontrollid läbitud');
  process.exit(fail ? 1 : 0);
})();
