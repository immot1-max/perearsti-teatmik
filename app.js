/* Perearsti teatmik – otsing ja vaated. Andmed: data/data.json (ehitab build/build.py). */
(() => {
  'use strict';

  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const eur = new Intl.NumberFormat('et-EE', { style: 'currency', currency: 'EUR' });
  const fmtEur = (v) => (v == null ? '' : eur.format(v));
  const fmtNum = (v) => (v == null ? '' : v.toLocaleString('et-EE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const fmtDate = (iso) => (iso ? iso.split('-').reverse().join('.') : '');
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9%.]+/g, ' ').replace(/(^|\s)\.+|\.+(\s|$)/g, ' ').trim();

  const SRC = {
    ttl: 'Tervishoiuteenuste loetelu',
    metoodika: 'Metoodika',
    abivahendid: 'Abivahendite määrus',
    mootorsoidukijuht: 'Mootorsõidukijuhi tervisenõuded',
    meditsiiniseadmed: 'Meditsiiniseadmete loetelu',
    toru: 'Toru',
  };
  function srcName(k) {
    const s = state.data && state.data.meta.sources[k];
    return SRC[k] || (s && s.nimi) || k || '';
  }
  // Küsimuse abisõnad, mida otsingus ei nõuta (nt „kui kaua haigusleht“).
  const STOP = new Set(['kui', 'kaua', 'pikalt', 'mis', 'kes', 'kas', 'ja', 'on', 'mitu', 'palju', 'millal', 'kuidas', 'viisil', 'moodi', 'see', 'ning', 'saab', 'tohib', 'mida', 'kus', 'mille', 'ma', 'me', 'ei', 'vaja', 'tuleb', 'peab', 'ka', 'aga', 'et', 'oma', 'seda', 'selle', 'mul', 'meil', 'kelle', 'mitme', 'miks']);
  const FUND_SHORT = { f37: 'Uuringufond 37%', f13: 'Teraapiafond 13%', lisaks: 'Tegevusfond' };
  const FUND_HELP = {
    f37: 'Tasutakse kuni 37% ulatuses nimistu pearahadeks arvestatud summast aastas.',
    f13: 'Tasutakse kuni 13% ulatuses nimistu pearahadeks arvestatud summast aastas.',
    lisaks: 'Tasutakse raviarvega lisaks pearahale, tervishoiuteenuste loetelu piirhinna alusel. Protsendilist piirmäära sellel lõikel ei ole.',
  };
  const KS_CAT = { ylevaade: 'Ülevaade', ennetus: 'Ennetus', krooniline: 'Kroonilised haiged', jalgimine: 'Jälgimisindikaatorid', lisapadevus: 'Erialane lisapädevus', soeluuring: 'Sõeluuringud' };
  const KS_ORDER = ['ylevaade', 'ennetus', 'krooniline', 'jalgimine', 'lisapadevus', 'soeluuring'];
  const ksPrefix = (q) => (q.cat === 'lisapadevus' ? 'Lisapädevus' : 'KS');
  function ksValue(q) {
    if (q.cat === 'lisapadevus') { const v = (q.rows || []).find((r) => r.v && r.v !== '0'); return v ? `koef ${v.v}` : ''; }
    if (q.cat === 'ennetus' || q.cat === 'soeluuring') return q.kokku ? `${q.kokku} p` : '';
    if (q.cat === 'jalgimine') return '0 p';
    return '';
  }
  function zeroLabel(it) {
    if (it.p !== 0) return null;
    const hk = (it.tp && it.tp.hk) || '';
    if (hk === 'PEREARSTIABI') return 'pearahasisene';
    if (/STAT/.test(hk)) return 'statistiline';
    return null;
  }
  // ------------------------------------------------------------ sõeluuringud
  const soelItems = () => (state.data ? state.data.items.filter((x) => x.t === 'v') : []);
  const soelYear = () => Math.max(0, ...soelItems().map((v) => v.aasta || 0)) || new Date().getFullYear();
  const ageRange = (v) => (v.vanus ? `${v.vanus[0]}–${v.vanus[1]} a` : '');
  const intText = (v) => (typeof v.int === 'number' ? `iga ${v.int} a` : '');
  // Sünniaasta otsingus: millise sõeluuringu sihtrühma inimene sel aastal kuulub.
  function birthYearCard(toks) {
    const year = soelYear();
    const y = toks.map((t) => (/^(19|20)\d\d$/.test(t) ? +t : 0)).find((n) => n && n >= year - 100 && n <= year - 18);
    if (!y) return '';
    const age = year - y;
    const lines = [];
    let hits = 0;
    for (const v of soelItems()) {
      const inAge = v.vanus && age >= v.vanus[0] && age <= v.vanus[1];
      if (v.sy) {
        if (v.sy.includes(y)) {
          hits++;
          lines.push(`<button class="yl yes" data-focus="${v._id}"><b>✓ ${esc(v.n)}</b><small>${esc(v.kes || '')} · ${esc(ageRange(v))} · ${esc(intText(v))}</small></button>`);
        } else if (inAge) {
          lines.push(`<button class="yl no" data-focus="${v._id}"><b>– ${esc(v.n)}</b><small>vanus sobib, kuid ${y} ei ole ${v.aasta}. aasta kutsutute seas</small></button>`);
        }
      } else if (inAge) {
        lines.push(`<button class="yl maybe" data-focus="${v._id}"><b>? ${esc(v.n)}</b><small>vanus sobib (${esc(ageRange(v))}); ${esc(v.lyh || 'riskihinnangu järgi')}</small></button>`);
      }
    }
    const none = hits ? '' : `<p class="yl-none">${year}. aastal ei kuulu ühegi sünniaasta põhise vähi sõeluuringu sihtrühma.</p>`;
    const stale = new Date().getFullYear() > year ? `<p class="note">Terviseportaalis on veel ${year}. aasta sihtrühmad.</p>` : '';
    return `<div class="ycard"><div class="yh"><b>Sünniaasta ${y}</b> · ${year}. aastal saab ${age}-aastaseks</div>${none}${lines.join('')}${stale}</div>`;
  }

  const AB_LABEL = {
    2: 'Täpsustus', 3: 'Kasutusaeg', 4: 'Tehingu liik', 5: 'Koguseline piirlimiit', 6: 'Individuaalne', 7: 'Seotud hooldusteenusega',
    8: 'Soodustus', 9: 'Piirhind (üür/kuu)', 10: 'Piirhind (müük)', 11: 'Ühik', 12: 'Kellele ja millal', 13: 'Eelduskood',
    14: 'Välistav kood', 15: 'Hoolduse min sagedus', 16: 'Vajaduse tuvastaja', 17: 'Müüja kvalifikatsioon',
  };
  const AB_ORDER = [16, 12, 8, 10, 9, 11, 3, 4, 5, 2, 6, 7, 13, 14, 15, 17];

  let paPref = true;
  try { paPref = localStorage.getItem('teatmik-pa') !== '0'; } catch (e) { /* ignoreeri */ }
  const state = { data: null, idx: [], filter: 'all', fund: null, q: '', open: new Set(), limit: 60, focus: null, pa: paPref, labsAll: new Set(), msAll: new Set() };
  const el = {};

  // ------------------------------------------------------------ andmed
  async function load() {
    let data;
    try {
      const r = await fetch('data/data.json');
      data = await r.json();
    } catch (e) {
      $('#results').innerHTML = '<p class="empty">Andmeid ei õnnestunud laadida. Ava leht korra võrgu olemasolul, siis töötab see edaspidi ka võrguta.</p>';
      return;
    }
    setData(data);
    checkUpdate();
  }

  async function checkUpdate() {
    if (!navigator.onLine || !state.data) return;
    try {
      const v = await (await fetch('data/version.json', { cache: 'no-store' })).json();
      if (v.fingerprint && v.fingerprint !== state.data.meta.fingerprint) {
        const fresh = await (await fetch('data/data.json?v=' + encodeURIComponent(v.built), { cache: 'no-store' })).json();
        setData(fresh);
        toast('Andmed uuendati (seis ' + fmtDate(fresh.meta.date) + ')');
      }
    } catch (e) { /* võrguta: kasutame olemasolevat */ }
  }

  function setData(data) {
    state.data = data;
    const items = data.items;
    const rules = data.rules;
    const codeSet = new Set(items.filter((x) => x.t === 's').map((x) => x.c));
    state.idx = items.map((it, i) => {
      it._id = i;
      let cls = 'teenus';
      if (it.t === 's') cls = it.f ? it.f[0] : 'teenus';
      else if (it.t === 'a') cls = 'abiv';
      else if (it.t === 'l') cls = it.src === 'mootorsoidukijuht' ? 'juhi' : 'sate';
      else if (it.t === 'k') cls = 'link';
      else if (it.t === 'f') cls = it.k;
      else if (it.t === 'q') cls = 'ks';
      else if (it.t === 'b') cls = 'lab';
      else if (it.t === 'm') cls = 'ms';
      else if (it.t === 'v') cls = 'soel';
      else if (it.t === 'j') cls = 'teema';
      it._cls = cls;
      let name = it.n || '';
      let ctx = '', txt = '', code = '';
      let boost = 0;
      if (it.t === 's') {
        code = norm(it.c);
        ctx = [it.pt, it.sub, it.par].join(' ');
        const rt = (it.r || []).map((ri) => rules[ri]).filter((r) => (r.s.match(/\b(?=[0-9A-Z]*\d)[0-9A-Z]{3,8}\b/g) || []).filter((c) => codeSet.has(c)).length <= 4);
        txt = rt.map((r) => r.s).join(' ');
        if (it.f) boost += 30;
        if ((it.ptk || '').startsWith('2.')) boost += 20;
        if (it.src === 'toru') boost -= 5;
      } else if (it.t === 'a') {
        code = norm(it.c);
        ctx = (it.g || []).join(' ') + ' ' + (it.v['2'] || '');
        txt = it.v['12'] || '';
      } else if (it.t === 'l') {
        name = `${it.par} ${it.n}`;
        ctx = srcName(it.src) + ' ' + (it.ptk || '');
        txt = it.b.map((b) => (b.t === 'tbl' ? b.rows.map((r) => r.join(' ')).join(' ') : b.s)).join(' ');
        boost += 8;
      } else if (it.t === 'f') {
        ctx = it.par + ' ' + (it.s || '');
        boost += 40;
      } else if (it.t === 'k') {
        txt = it.d || '';
      } else if (it.t === 'm') {
        code = norm(it.c || '');
        ctx = (it.subs || []).map((x) => x[0]).join(' ') + ' meditsiiniseade';
        txt = (it.b || []).map((b) => b.s || '').join(' ') + ' ' + (it.pr || []).map((x) => `${x[0]} ${x[1]}`).join(' ');
        boost += 20;
      } else if (it.t === 'b') {
        ctx = `${it.cat || ''} ${(it.c || []).map((x) => x[0]).join(' ')} ${it.mat || ''}`;
        boost += it.f ? 25 : 15;
      } else if (it.t === 'q') {
        name = `${it.n} ${it.sn || ''}`;
        ctx = `${KS_CAT[it.cat] || ''} ${it.title || ''} kvaliteedisüsteem ${it.par || ''}`;
        txt = (it.rows || []).map((r) => `${r.s || ''} ${r.d} ${r.c.join(' ')}`).join(' ') + ' ' + (it.notes || []).join(' ');
        boost += 45;
      } else if (it.t === 'v') {
        name = `${it.n} ${it.sn || ''}`;
        ctx = `vähi sõeluuring ${it.kes || ''} ${(it.sy || []).join(' ')}`;
        txt = (it.notes || []).join(' ') + ' ' + (it.osale || '') + ' ' + (it.codes || []).map((c) => c.join(' ')).join(' ');
        boost += 50;
      } else if (it.t === 'j') {
        name = `${it.n} ${it.sn || ''}`;
        ctx = `${it.g || ''} teema`;
        const tabTxt = (it.tab || []).map((tb) => [tb.n, tb.tekst || '', tb.markus || '', (tb.legend || []).join(' '),
          (tb.read || []).map((r) => r.join(' ')).join(' '),
          (tb.rows || []).map((r) => [r.pohjus.join(' '), r.nr.join(' '), r.liik, r.kord.join(' '), r.kestus].join(' ')).join(' ')].join(' ')).join(' ');
        txt = [...(it.r || []), ...(it.e || []), ...(it.tul || [])].map((r) => r.s + ' ' + (r.a || []).map((a) => a.n).join(' ')).join(' ') + ' ' + tabTxt;
        boost += 45 + (it.boost || 0);
      }
      const syn = (it.syn || []).map(norm);
      if (it.t === 'b' && it.ab) {
        syn.push(norm(it.ab));
        const core = it.ab.replace(/^[A-Za-z,]+-/, '');
        if (core !== it.ab) syn.push(norm(core));
      }
      return {
        it, code, name: ' ' + norm(name) + ' ', ctx: ' ' + norm(ctx) + ' ', txt: ' ' + norm(txt) + ' ',
        syn, boost,
      };
    });
    state.qByKey = {};
    state.byCode = {};
    state.labsByCode = {};
    for (const it of items) {
      if (it.t === 'q') state.qByKey[it.k] = it;
      if (it.t === 's') state.byCode[it.c] = it;
      if (it.t === 'b') for (const [c] of it.c || []) (state.labsByCode[c] = state.labsByCode[c] || []).push(it);
    }
    renderChips();
    renderStatus();
    route();
  }

  // ------------------------------------------------------------ otsing
  function passPa(e) {
    return !(state.pa && e.it.t === 's' && !e.it.pa);
  }
  function passFilter(e) {
    const t = e.it.t;
    if (state.fund) return t === 's' && (e.it.f || []).includes(state.fund);
    if (state.filter === 'all') return true;
    if (state.filter === 'l') return t === 'l' || t === 'f';
    if (state.filter === 'q') return t === 'q';
    if (state.filter === 'b') return t === 'b';
    if (state.filter === 'm') return t === 'm';
    if (state.filter === 'v') return t === 'v';
    if (state.filter === 'j') return t === 'j';
    return t === state.filter;
  }

  // Ühe otsingusõna skoor kirjele (0 = ei sobi). via = vaste ainult sisutekstis.
  function tokScore(e, t) {
    let s = 0;
    if (e.code) {
      if (e.code === t) s = 400;
      else if (t.length >= 2 && e.code.startsWith(t)) s = 150;
    }
    if (e.name.includes(' ' + t + ' ')) s = Math.max(s, 60);
    else if (e.name.includes(' ' + t)) s = Math.max(s, 45);
    else if (t.length >= 5 && e.name.includes(t)) s = Math.max(s, 20);
    for (const sy of e.syn) {
      if (sy === t) s = Math.max(s, 90);
      else if ((' ' + sy).includes(' ' + t)) s = Math.max(s, 40);
    }
    if (!s && t.length >= 6) {
      // eesti käändelõpud: haiguslehte → haiguslehe → haigusleh
      const cuts = t.length >= 7 ? [1, 2, 3] : [1, 2];
      for (const n of cuts) {
        const cut = t.slice(0, -n);
        if (e.name.includes(' ' + cut)) { s = 30; break; }
        if (e.syn.some((sy) => (' ' + sy).includes(' ' + cut))) { s = 30; break; }
      }
    }
    if (!s && e.ctx.includes(' ' + t)) s = 12;
    if (!s && e.txt.includes(' ' + t)) return { s: 6, via: true };
    return { s, via: false };
  }

  function search(q) {
    const qn = norm(q);
    let toks = qn.split(' ').filter(Boolean);
    const core = toks.filter((t) => !STOP.has(t));
    if (core.length) toks = core;
    const run = (tk) => {
      const out = [];
      let hidden = 0;
      for (const e of state.idx) {
        if (!passFilter(e)) continue;
        const exact = e.code && e.code === qn;
        const paOk = passPa(e) || exact;
        let score = 0, via = false, ok = true;
        for (const t of tk) {
          const r = tokScore(e, t);
          if (!r.s) { ok = false; break; }
          score += r.s;
          via = via || r.via;
        }
        if (!ok) continue;
        if (tk.length > 1) for (const sy of e.syn) if (sy === qn) score += 200;
        if (exact) score += 600;
        if (!paOk) { hidden++; continue; }
        out.push({ e, score: score + e.boost, via });
      }
      out.sort((a, b) => b.score - a.score || a.e.name.length - b.e.name.length);
      return { list: out, hidden };
    };
    let res = run(toks);
    let dropped = [];
    if (!res.list.length && toks.length > 1) {
      // Sõnad, mis ei sobi ühegi kirjega, jäetakse kõrvale (nt „rahastatakse“).
      const known = toks.filter((t) => state.idx.some((e) => passFilter(e) && tokScore(e, t).s));
      if (known.length && known.length < toks.length) {
        dropped = toks.filter((t) => !known.includes(t));
        res = run(known);
        toks = known;
      }
    }
    return { list: res.list, toks, hidden: res.hidden, dropped };
  }

  // tähemärgitundetu esiletõst
  const FOLD = { a: '[aäàáâ]', o: '[oõöóò]', u: '[uüúù]', s: '[sš]', z: '[zž]', e: '[eéè]', i: '[iíì]', c: '[cč]' };
  function hlRegex(toks) {
    const parts = toks.filter((t) => t.length >= 2).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/[aousezic]/g, (c) => FOLD[c] || c));
    return parts.length ? new RegExp('(' + parts.join('|') + ')', 'gi') : null;
  }
  const hl = (s, re) => (re ? esc(s).replace(re, '<mark>$1</mark>') : esc(s));

  // ------------------------------------------------------------ vaated
  function route() {
    const r = el.results;
    const q = state.q.trim();
    state.hl = q ? hlRegex(norm(q).split(' ')) : null;
    if (state.focus != null) {
      const it = state.data.items[state.focus];
      state.open.add(it._id);
      r.innerHTML = `<div class="summary"><span>${esc(srcName(it.src) || '')}</span><button class="btn" data-act="home">← Avaleht</button></div><div class="list">${row(it)}</div>`;
      return;
    }
    if (!q && !state.fund && state.filter === 'all') { renderHome(); return; }
    let list;
    let hidden = 0;
    let dropped = [];
    if (q) {
      const res = search(q);
      hidden = res.hidden;
      dropped = res.dropped || [];
      list = res.list.map((x) => ({ it: x.e.it, via: x.via }));
    } else {
      const all = state.idx.filter(passFilter);
      list = all.filter(passPa).map((e) => ({ it: e.it }));
      hidden = all.length - list.length;
      if (state.fund || state.filter === 's') {
        const gk = (it) => it.pt || (it.tp && it.tp.hk) || '';
        list.sort((a, b) => gk(a.it).localeCompare(gk(b.it), 'et') || a.it.n.localeCompare(b.it.n, 'et'));
      }
      if (state.filter === 'q') list.sort((a, b) => KS_ORDER.indexOf(a.it.cat) - KS_ORDER.indexOf(b.it.cat));
    }
    const total = list.length;
    const shown = list.slice(0, state.limit);
    let html = '';
    const fundItem = state.fund ? state.data.items.find((x) => x.t === 'f' && x.k === state.fund) : null;
    if (fundItem) {
      html += `<div class="row ${fundItem.k}"><div class="detail" style="border-top:0"><div class="text"><p><strong>${esc(fundItem.n)}</strong> · metoodika ${esc(fundItem.par)}</p><p>${esc(FUND_HELP[fundItem.k] || '')}</p>${state.data.meta.starRule && fundItem.k === 'f37' ? `<p>* ${esc(state.data.meta.starRule)}</p>` : ''}</div><div class="actions"><a href="${esc(fundItem.url)}" target="_blank" rel="noopener">Säte Riigi Teatajas ↗</a></div></div></div>`;
    }
    const yCard = q && !state.fund && (state.filter === 'all' || state.filter === 'v') ? birthYearCard(norm(q).split(' ')) : '';
    html += yCard;
    html += `<div class="summary"><span>${total ? `${total} vastet` : ''}${q && total > state.limit ? `, näitan ${state.limit}` : ''}</span>${q || state.fund || state.filter !== 'all' ? '<button class="btn" data-act="home">Tühjenda</button>' : ''}</div>`;
    if (dropped.length) html += `<div class="hidden-note">Neid sõnu ei leitud, otsisin ilma nendeta: ${dropped.map(esc).join(', ')}</div>`;
    if (hidden && state.pa) html += `<div class="hidden-note">${hidden} vastet väljaspool perearstiabi on peidetud.<button class="btn" data-act="pa-off">Näita kõiki</button></div>`;
    if (!total && yCard) {
      // sünniaasta kaart on vastus
    } else if (!total) {
      html += `<p class="empty">Midagi ei leitud. Proovi lühemat sõna või koodi algust.</p>`;
      if (q && (state.fund || state.filter !== 'all')) html += '<button class="btn solid" data-act="all">Otsi kõigist kategooriatest</button>';
    } else {
      html += '<div class="list">';
      const grouped = !q && (state.fund || state.filter === 'a' || state.filter === 'l' || state.filter === 'q' || state.filter === 'b' || state.filter === 's' || state.filter === 'm' || state.filter === 'j');
      if (!q && state.filter === 'm') shown.sort((a, b) => a.it.n.localeCompare(b.it.n, 'et'));
      let lastG = null;
      for (const x of shown) {
        if (grouped) {
          const g = x.it.t === 'j' ? x.it.g : x.it.t === 'm' ? 'Tervisekassa meditsiiniseadmed' : x.it.t === 'a' ? (x.it.g || [])[0] || x.it.n : x.it.t === 'l' ? srcName(x.it.src) : x.it.t === 'f' ? 'Fondid' : x.it.t === 'q' ? KS_CAT[x.it.cat] : x.it.t === 'b' ? x.it.cat : x.it.pt || (x.it.tp && x.it.tp.hk) || srcName(x.it.src);
          if (g !== lastG) { html += `<div class="group-h">${esc(g)}</div>`; lastG = g; }
        }
        html += row(x.it, x.via);
      }
      html += '</div>';
      if (total > shown.length) html += `<button class="btn more" data-act="more">Näita veel ${Math.min(60, total - shown.length)}</button>`;
    }
    r.innerHTML = html;
  }

  function row(it, via) {
    const open = state.open.has(it._id);
    const re = state.hl;
    if (it.t === 'k') {
      return `<article class="row link"><a class="head" href="${esc(it.u)}" target="_blank" rel="noopener"><span class="name">${hl(it.n, re)} ↗</span><span></span><span class="meta">${esc(it.d || '')}</span></a></article>`;
    }
    if (it.t === 'f') {
      return `<article class="row ${it.k}"><button class="head" data-fund="${it.k}"><span class="name">${esc(it.n)}</span><span class="price">${it.cnt} <small>teenust</small></span><span class="meta"><span class="badge ${it.k}">${esc(FUND_SHORT[it.k] || it.k)}</span>metoodika ${esc(it.par)} · ava loetelu</span></button></article>`;
    }
    let head = '';
    if (it.t === 'm') {
      const pct = (it.pct || []).map((x) => x + '%').join(' / ');
      head = `<span class="name">${hl(it.n, re)}</span><span class="price"><small>${esc(pct)}</small></span>
        <span class="meta">${it.c ? `<span class="code" data-copy="${esc(it.c)}" title="Kopeeri rühma kood">${esc(it.c)}</span>` : ''}<span class="badge msb">meditsiiniseade</span><span>${esc(it.par || '')} · ${(it.pr || []).length} toodet</span>${via ? '<span class="via">· vaste tingimustes või toodetes</span>' : ''}</span>`;
    } else if (it.t === 'b') {
      const fund = (it.f || []).map((f) => `<span class="badge ${f}">${esc(FUND_SHORT[f] || f)}</span>`).join('') || '<span class="badge no">ei ole perearsti fondis</span>';
      const ks = (it.ks || []).map((k) => state.qByKey[k]).filter(Boolean).map((qq) => `<span class="badge ks" data-focus="${qq._id}">${esc(ksPrefix(qq))}: ${esc(qq.sn)}</span>`).join('');
      const codes = (it.c || []).map(([c, x]) => `<span class="code" data-copy="${esc(c)}" title="Kopeeri TK kood">${esc(c)}${x > 1 ? ' ×' + x : ''}</span>`).join('');
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${it.p != null ? fmtEur(it.p) : ''}</span>
        <span class="meta">${it.ab ? `<span>${hl(it.ab, re)}</span>` : ''}${codes || '<span class="badge no">TK koodi pole</span>'}${codes ? fund : ''}${ks}<span>SYNLAB</span>${via ? '<span class="via">· vaste</span>' : ''}</span>`;
    } else if (it.t === 'q') {
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${esc(ksValue(it))}</span>
        <span class="meta"><span class="badge ks">${esc(KS_CAT[it.cat] || '')}</span><span>metoodika ${esc(it.par)}</span>${via ? '<span class="via">· vaste sisus</span>' : ''}</span>`;
    } else if (it.t === 's') {
      const fund = (it.f || []).map((f) => `<span class="badge ${f}">${esc(FUND_SHORT[f] || f)}</span>`).join('');
      const zl = zeroLabel(it);
      const price = zl ? `<small>${zl}</small>` : it.p != null ? fmtEur(it.p) : '';
      const ks = (it.ks || []).map((k) => state.qByKey[k]).filter(Boolean).map((qq) => `<span class="badge ks" data-focus="${qq._id}" title="Ava kvaliteedisüsteemi jaotis">${esc(ksPrefix(qq))}: ${esc(qq.sn)}</span>`).join('');
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${price}</span>
        <span class="meta"><span class="code" data-copy="${esc(it.c)}" title="Kopeeri kood">${esc(it.c)}</span>${fund}${ks}${it.fn ? '<span class="badge f37">* ainult S00–S09</span>' : ''}<span>${esc(it.par ? it.par + ' ' + (it.pt || '') : srcName(it.src))}</span>${via ? '<span class="via">· vaste tingimustes</span>' : ''}</span>`;
    } else if (it.t === 'a') {
      const v = it.v;
      const price = v['10'] ? `${esc(v['10'])} €` : v['9'] ? `${esc(v['9'])} € <small>/kuu</small>` : '';
      const pe = /perearst/i.test(v['16'] || '') ? '<span class="badge abiv">perearst võib tuvastada</span>' : '';
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${price}</span>
        <span class="meta"><span class="code" data-copy="${esc(it.c)}" title="Kopeeri kood">${esc(it.c)}</span>${v['8'] ? `<span class="badge plain">${esc(v['8'])}</span>` : ''}${pe}${it.grp ? '<span class="badge plain">rühm</span>' : ''}<span>${esc((it.g || []).slice(-1)[0] || '')}</span>${via ? '<span class="via">· vaste kirjelduses</span>' : ''}</span>`;
    } else if (it.t === 'l') {
      head = `<span class="name">${esc(it.par)} ${hl(it.n, re)}</span><span></span><span class="meta"><span>${esc(srcName(it.src))}</span>${via ? '<span class="via">· vaste tekstis</span>' : ''}</span>`;
    } else if (it.t === 'j') {
      const changed = (it.r || []).some((r) => r.muutus);
      head = `<span class="name">${hl(it.n, re)}</span><span></span>
        <span class="meta"><span class="badge teema">${esc(it.g || 'teema')}</span><span>${(it.r || []).length} punkti</span>${(it.e || []).length ? `<span class="badge warn">${it.e.length} erinevus${it.e.length > 1 ? 't' : ''} allikates</span>` : ''}${changed ? '<span class="badge warn">allikas muutunud</span>' : ''}${via ? '<span class="via">· vaste sisus</span>' : ''}</span>`;
    } else if (it.t === 'v') {
      const yrs = it.sy ? `${it.aasta}: ${it.sy.length} sünniaastat` : (it.lyh || '');
      head = `<span class="name">${hl(it.n, re)}</span><span class="price"><small>${esc(ageRange(it))}</small></span>
        <span class="meta"><span class="badge soel">sõeluuring</span>${it.sy ? `<span>${esc(it.kes || '')}</span>` : ''}${intText(it) ? `<span>${esc(intText(it))}</span>` : ''}<span>${esc(yrs)}</span>${via ? '<span class="via">· vaste sisus</span>' : ''}</span>`;
    }
    return `<article class="row ${it._cls}"><button class="head" data-open="${it._id}" aria-expanded="${open}">${head}</button>${open ? `<div class="detail">${detail(it)}</div>` : ''}</article>`;
  }

  function detail(it) {
    const d = state.data;
    const re = state.hl;
    if (it.t === 's') {
      let h = '<dl class="kv">';
      if (zeroLabel(it)) {
        h += `<div><dt>Piirhind</dt><dd>${zeroLabel(it) === 'pearahasisene' ? 'Pearahasisene tegevuse kood' : 'Statistiline kood'} (Torus piirhind 0 €)</dd></div>`;
      } else if (it.p != null) {
        const tp = it.tp || {};
        let extra = tp.from ? `kehtib alates ${fmtDate(tp.from)}` : '';
        if (tp.prev) extra += `${extra ? ', ' : ''}varem ${fmtEur(tp.prev[0])}`;
        h += `<div><dt>Piirhind</dt><dd><b>${fmtEur(it.p)}</b>${extra ? ` <span class="kv inh">${extra}</span>` : ''}${it.pl ? it.pl.map(([k, v]) => `<br>${esc(k)}: ${fmtEur(v)}`).join('') : ''}</dd></div>`;
      }
      if (it.f) {
        for (const f of it.f) {
          const fi = d.items.find((x) => x.t === 'f' && x.k === f);
          h += `<div><dt>Rahastus</dt><dd><span class="badge ${f}">${esc(FUND_SHORT[f])}</span> ${esc(FUND_HELP[f] || '')}${fi ? ` <a href="${esc(fi.url)}" target="_blank" rel="noopener">metoodika ${esc(fi.par)} ↗</a>` : ''}</dd></div>`;
        }
      } else if (it.src !== 'toru' || (it.tp && it.tp.hk === 'PEREARSTIABI')) {
        h += `<div><dt>Rahastus</dt><dd>Metoodika § 6 fondide loeteludes seda koodi ei ole.</dd></div>`;
      }
      if (it.fn && d.meta.starRule) h += `<div><dt>Tärn (*)</dt><dd>${esc(d.meta.starRule)}</dd></div>`;
      for (const k of it.ks || []) {
        const qq = state.qByKey[k];
        if (!qq) continue;
        const base = it.c.replace(/[KV]$/, '');
        const rows = (qq.rows || []).filter((r) => r.c.includes(it.c) || r.c.includes(base));
        const lines = rows.map((r) => `${r.s ? esc(r.s) + ' › ' : ''}${esc(r.d)}`).filter((x, i, a) => a.indexOf(x) === i).join('<br>');
        h += `<div><dt>${esc(ksPrefix(qq) === 'KS' ? 'Kvaliteedisüsteem' : 'Lisapädevus')}</dt><dd><button class="badge ks" data-focus="${qq._id}">${esc(qq.n)}</button>${ksValue(qq) ? ` <span class="inh">${esc(ksValue(qq))}</span>` : ''}<br>${lines}</dd></div>`;
      }
      if (it.src === 'ttl') {
        h += `<div><dt>Allikas</dt><dd>Tervishoiuteenuste loetelu ${esc(it.par)} ${esc(it.pt)}${it.sub ? ` (${esc(it.sub)})` : ''} <a href="${esc(it.url)}" target="_blank" rel="noopener">Riigi Teataja ↗</a></dd></div>`;
      } else if (it.src === 'toru') {
        h += `<div><dt>Allikas</dt><dd>Ainult Toru failis (${esc(d.meta.toru?.file || '')}); kehtiva loetelu tabelites koodi ei ole.</dd></div>`;
      } else if (it.src === 'metoodika') {
        h += `<div><dt>Allikas</dt><dd>Kood on metoodika § 6 loetelus, kuid kehtiva tervishoiuteenuste loetelu tabelites ega Torus seda ei leidu. <a href="${esc(it.url)}" target="_blank" rel="noopener">Säte ↗</a></dd></div>`;
      }
      if (it.tp && it.tp.hk) h += `<div><dt>Toru liik</dt><dd>${esc(it.tp.hk)}</dd></div>`;
      if (it.muud) h += `<div><dt>Esineb ka</dt><dd>${it.muud.map((m) => esc(m.par)).join(', ')}</dd></div>`;
      h += '</dl>';
      if (it.tmis) h += `<p class="note">Toru failis on selle koodi hind ${fmtEur(it.tp.p)}, mis erineb kehtivast loetelust. Õiguslikult kehtib loetelu hind.</p>`;
      const labs = state.labsByCode[it.c] || [];
      if (labs.length) {
        const showAll = state.labsAll.has(it.c) || labs.length <= 30;
        const shown = showAll ? labs : labs.slice(0, 30);
        h += `<div class="rules"><h4>SYNLABi analüüsid selle koodiga (${labs.length})</h4><div class="labs">`
          + shown.map((lb) => `<button class="btn" data-q="${esc(lb.ab || lb.n)}" title="${esc(lb.n)}">${esc(lb.n)}${lb.ab ? ' · ' + esc(lb.ab) : ''}</button>`).join('')
          + (showAll ? '' : `<button class="btn solid" data-labs-all="${esc(it.c)}">Näita kõiki ${labs.length}</button>`) + '</div></div>';
      }
      if (it.r && it.r.length) {
        h += '<div class="rules"><h4>Tingimused ja seotud sätted</h4>';
        for (const ri of it.r) {
          const rr = d.rules[ri];
          h += `<div class="rule"><span class="ref">${esc(srcName(rr.src))} ${esc(rr.par)}</span>${hl(rr.s, re)} <a href="${esc(rr.url)}" target="_blank" rel="noopener">↗</a></div>`;
        }
        h += '</div>';
      }
      return h;
    }
    if (it.t === 'a') {
      const inh = new Set((it.inh || []).map(String));
      let h = '<dl class="kv">';
      if (it.g && it.g.length) h += `<div><dt>Rühm</dt><dd>${it.g.map(esc).join(' › ')}</dd></div>`;
      for (const k of AB_ORDER) {
        let v = it.v[String(k)];
        if (!v) continue;
        if (k === 4) v = v.replace(/\bM\b/g, 'müük').replace(/\bÜ\b/g, 'üür');
        if (k === 6 && v === 'I') v = 'jah (individuaalne)';
        if (k === 7 && v === 'H') v = 'jah';
        const body = hl(v, re).replace(/\n/g, '<br>');
        h += `<div><dt>${esc(AB_LABEL[k])}</dt><dd>${body}${inh.has(String(k)) ? ' <span class="inh">(rühma tingimus)</span>' : ''}</dd></div>`;
      }
      h += '</dl>';
      const ab = d.meta.sources.abivahendid;
      h += `<div class="actions">${ab.lisaUrl ? `<a href="${esc(ab.lisaUrl)}" target="_blank" rel="noopener">Abivahendite loetelu (PDF) ↗</a>` : ''}<a href="https://sotsiaalkindlustusamet.ee/abivahendite-otsimootor" target="_blank" rel="noopener">SKA otsimootor ↗</a><button class="btn" data-goto="abivahendid:§ 2¹">Tõendi andmed (§ 2¹)</button></div>`;
      return h;
    }
    if (it.t === 'm') {
      const ms = d.meta.sources.meditsiiniseadmed || {};
      let h = '<dl class="kv">';
      if (it.c) h += `<div><dt>Rühma kood</dt><dd><button class="code" data-copy="${esc(it.c)}">${esc(it.c)}</button> (meditsiiniseadme kaardil)</dd></div>`;
      h += `<div><dt>Väljakirjutamine</dt><dd>Meditsiiniseadme kaart retseptikeskuses. Välja kirjutada võib Terviseametis registreeritud arst (määruse § 64 lg 2), kui tingimused on täidetud.</dd></div>`;
      h += `<div><dt>Hüvitis</dt><dd>${(it.pct || []).map((x) => x + '%').join(' / ')} Tervisekassa piirhinnast; omaosalus on vahe piirhinna (või odavama jaemüügihinna) ja hüvitise vahel (§ 3).</dd></div>`;
      h += '</dl>';
      if (it.b && it.b.length) {
        h += `<div class="rules"><h4>Tingimused (${esc(it.par || '')})</h4><div class="text">` + it.b.map((b) => (b.t === 'p' ? `<p>${hl(b.s, re)}</p>` : b.t === 'li' ? `<p class="li">${hl(b.s, re)}</p>` : '')).join('') + '</div></div>';
      }
      h += '<h4>Alarühmad</h4><div class="tbl"><table><tr><td>Alarühm</td><td>Tooteid</td><td>TK piirhind</td><td>%</td></tr>'
        + (it.subs || []).map(([n, cnt, mn, mx, pc]) => `<tr><td>${hl(n, re)}</td><td class="num">${cnt}</td><td class="num">${mn == null ? '' : mn === mx ? fmtEur(mn) : fmtNum(mn) + '–' + fmtEur(mx)}</td><td class="num">${(pc || []).join('/')}</td></tr>`).join('') + '</table></div>';
      const all = state.msAll.has(it._id);
      const reNG = state.hl ? new RegExp(state.hl.source, 'i') : null;
      const tokens = reNG ? (it.pr || []).filter((x) => reNG.test(x[1]) || reNG.test(x[0])) : [];
      const prs = all ? it.pr : tokens.slice(0, 40);
      if (prs.length) {
        h += `<h4>${all ? 'Tooted' : 'Otsingule vastavad tooted'} (${prs.length})</h4><div class="tbl"><table><tr><td>Kood</td><td>Toode</td><td>Pakendi piirhind</td><td>TK piirhind</td><td>%</td></tr>`
          + prs.map((x) => `<tr><td><span class="code">${esc(x[0])}</span></td><td>${hl(x[1], re)}<br><small class="inh">${esc((it.subs[x[2]] || [])[0] || '')}</small></td><td class="num">${x[3] != null ? fmtEur(x[3]) : ''}</td><td class="num">${x[4] != null ? fmtEur(x[4]) : ''}</td><td class="num">${x[5] ?? ''}</td></tr>`).join('') + '</table></div>';
      }
      h += '<div class="actions">' + (all ? '' : `<button class="btn" data-ms-all="${it._id}">Näita kõiki tooteid (${(it.pr || []).length})</button>`)
        + (it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">Määrus ${esc(it.par)} ↗</a>` : '')
        + (ms.lisaUrl ? `<a href="${esc(ms.lisaUrl)}" target="_blank" rel="noopener">Meditsiiniseadmete loetelu (PDF) ↗</a>` : '') + '</div>';
      return h;
    }
    if (it.t === 'b') {
      let h = '<dl class="kv">';
      if (it.ab) h += `<div><dt>Lühend</dt><dd>${esc(it.ab)}</dd></div>`;
      for (const [c, x] of it.c || []) {
        const s = state.byCode[c];
        const fund = s && s.f ? s.f.map((f) => `<span class="badge ${f}">${esc(FUND_SHORT[f])}</span>`).join(' ') : '<span class="badge no">ei ole perearsti fondis</span>';
        h += `<div><dt>TK kood${x > 1 ? ` (×${x})` : ''}</dt><dd><button class="code" data-q="${esc(c)}" title="Ava kood">${esc(c)}</button> ${s ? esc(s.n) : ''}${s && s.p != null ? ` · ${fmtEur(s.p)}` : ''}<br>${fund}</dd></div>`;
      }
      if (!(it.c || []).length) h += '<div><dt>TK kood</dt><dd>Puudub. Tervisekassa seda analüüsi ei hüvita (tasuline).</dd></div>';
      if (it.p != null) h += `<div><dt>SYNLABi hind</dt><dd>${fmtEur(it.p)}</dd></div>`;
      if (it.mat) h += `<div><dt>Materjal</dt><dd>${esc(it.mat)}</dd></div>`;
      if (it.aeg) h += `<div><dt>Vastuse aeg</dt><dd>${esc(it.aeg)}</dd></div>`;
      if (it.vah) h += `<div><dt>Vahendatav</dt><dd>${esc(it.vah)}</dd></div>`;
      if (it.cat) h += `<div><dt>Rühm</dt><dd>${esc(it.cat)}</dd></div>`;
      h += '</dl>';
      const sm = d.meta.synlab || {};
      h += `<div class="actions"><a href="${esc(sm.page || 'https://synlab.ee/arstile/hinnakiri/')}" target="_blank" rel="noopener">SYNLABi hinnakiri${sm.seisuga ? ' (alates ' + esc(sm.seisuga) + ')' : ''} ↗</a></div>`;
      return h;
    }
    if (it.t === 'q') {
      let h = '';
      if (it.k === 'ylevaade') {
        if (it.lisatasud && it.lisatasud.length) {
          h += '<h4>Lisatasud (tervishoiuteenuste loetelu § 3)</h4><div class="tbl"><table><tr><td>Kood</td><td>Teenus</td><td>Piirhind</td></tr>'
            + it.lisatasud.map(([c, n, p]) => `<tr><td><button class="code" data-q="${esc(c)}">${esc(c)}</button></td><td>${esc(n)}</td><td class="num">${p != null ? fmtEur(p) : ''}</td></tr>`).join('') + '</table></div>';
        }
        const secs = KS_ORDER.slice(1).map((cat) => [cat, d.items.filter((x) => x.t === 'q' && x.cat === cat)]).filter(([, l]) => l.length);
        h += '<h4>Jaotised</h4><div class="actions">' + secs.map(([cat, l]) => l.map((qq) => `<button class="btn" data-focus="${qq._id}">${esc(qq.sn)}</button>`).join('')).join('') + '</div>';
      } else {
        h += '<div class="tbl"><table><tr><td>Tegevus</td><td>Kood</td><td>' + esc(it.vl || '') + '</td></tr>';
        let lastS = null, lastD = null;
        for (const r of it.rows || []) {
          if (r.s && r.s !== lastS) h += `<tr><td colspan="3"><b>${esc(r.s)}</b></td></tr>`;
          lastS = r.s;
          const desc = r.d === lastD ? '' : hl(r.d, re);
          lastD = r.d;
          const codes = r.c.map((c) => `<button class="code" data-q="${esc(c)}" title="Otsi koodi">${esc(c)}</button>`).join(' ');
          h += `<tr><td>${desc}</td><td>${codes}</td><td class="num">${esc(r.v || '')}</td></tr>`;
        }
        if (it.kokku) h += `<tr><td>Lõige kokku</td><td></td><td class="num">${esc(it.kokku)}</td></tr>`;
        h += '</table></div>';
      }
      for (const v of d.items.filter((x) => x.t === 'v' && x.sy && (x.ks || []).includes(it.k))) {
        h += `<div class="rules"><h4>Sihtrühm ${v.aasta} (terviseportaal)</h4><div class="rule">Sünniaastad ${v.sy.join(', ')} (${esc(ageRange(v))}, ${esc(intText(v))}). <button class="badge soel" data-focus="${v._id}">${esc(v.n)}</button></div></div>`;
      }
      if (it.notes && it.notes.length) {
        const src = d.meta.ksNotes && d.meta.ksNotes.allikas ? d.meta.ksNotes.allikas : 'Tervisekassa juhendid';
        h += `<div class="rules"><h4>Selgitused (${esc(src)})</h4>${it.notes.map((n) => `<div class="rule">${hl(n, re)}</div>`).join('')}</div>`;
      }
      const docs = (d.meta.tk && d.meta.tk.docs) || [];
      h += `<div class="actions"><a href="${esc(it.url)}" target="_blank" rel="noopener">Metoodika ${esc(it.par)} ↗</a>`
        + docs.filter((x) => it.k === 'ylevaade' || x.k === 'ind' || x.k === 'juhis').map((x) => `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.n)}${x.aasta ? ' ' + x.aasta : ''} ↗</a>`).join('')
        + (it.k === 'ylevaade' && d.meta.tk ? `<a href="${esc(d.meta.tk.page)}" target="_blank" rel="noopener">Tervisekassa kvaliteedisüsteemi leht ↗</a>` : '')
        + '</div>';
      return h;
    }
    if (it.t === 'j') {
      const chips = (a) => (a || []).filter(Boolean).map((x) => (x.src && !/^lisa/.test(x.par || '')
        ? `<button class="badge srcb" data-goto="${esc(x.src)}:${esc(x.par)}" title="Ava säte">${esc(x.n)}</button>`
        : `<a class="badge srcb" href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.n)} ↗</a>`)).join(' ');
      let h = '';
      for (const f of it.tul || []) {
        if (f.alates <= new Date().toISOString().slice(0, 10)) continue;
        h += `<p class="note"><b>Alates ${fmtDate(f.alates)}:</b> ${hl(f.s, re)} ${chips(f.a)}</p>`;
      }
      for (const tb of it.tab || []) {
        h += `<h4>${esc(tb.n)}</h4>`;
        if (tb.dyn === 'huvitised') {
          h += '<div class="hv">' + tb.rows.map((r) => `<div class="hvr"><div class="hvh">${r.nr.map((n) => `<span class="code">${esc(n)}</span>`).join('')}<b>${r.pohjus.map((x) => hl(x, re)).join(' / ')}</b><small>${esc(r.liik)}</small></div>`
            + `<div>${r.kord.map((x) => hl(x, re)).join(' ')}</div><div class="hvk">${hl(r.kestus, re)}</div></div>`).join('') + '</div>';
          if (tb.uuendatud && tb.uuendatud.length) h += `<p class="small">Tervisekassa leht uuendatud ${tb.uuendatud.map(fmtDate).join(', ')}.</p>`;
        } else if (tb.read) {
          h += `<div class="tbl"><table><tr>${(tb.pais || []).map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`
            + tb.read.map((r) => `<tr>${r.map((c) => `<td>${hl(c, re)}</td>`).join('')}</tr>`).join('') + '</table></div>';
        } else if (tb.tekst) {
          const open = re && new RegExp(re.source, 'i').test(tb.tekst);
          h += `<details class="lisa"${open ? ' open' : ''}><summary>Näita loetelu (PDF-i tekst)</summary><div class="pre">${hl(tb.tekst, re)}</div></details>`;
        }
        if (tb.markus) h += `<p class="small">${hl(tb.markus, re).replace(/\n/g, '<br>')}</p>`;
        if (tb.legend && tb.legend.length) h += `<p class="small">${tb.legend.map((x) => hl(x, re)).join('; ')}</p>`;
        if (tb.a && tb.a.length) h += `<div class="srcs">${chips(tb.a)}</div>`;
      }
      if ((it.r || []).length) {
        h += '<div class="rules"><h4>Põhireeglid</h4>' + it.r.map((r) => `<div class="rule${r.muutus ? ' changed' : ''}">${r.muutus ? '<span class="badge warn">allika tekst muutunud, vaata üle</span> ' : ''}${hl(r.s, re)}<div class="srcs">${chips(r.a)}</div></div>`).join('') + '</div>';
      }
      if ((it.e || []).length) {
        h += '<div class="rules"><h4>Erinevused allikates</h4>' + it.e.map((r) => `<div class="note">${hl(r.s, re)}<div class="srcs">${chips(r.a)}</div></div>`).join('') + '</div>';
      }
      const links = [...(it.lisad || []).map((x) => ({ n: 'Lisa: ' + x.n, u: x.u })), ...(it.l || [])];
      if (links.length) h += `<div class="actions">${links.map((x) => `<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.n)} ↗</a>`).join('')}</div>`;
      const tm = d.meta.teemad || {};
      h += `<p class="small">Kokkuvõte on koostatud allikate põhjal (kontrollitud ${fmtDate(tm.kontrollitud)}). Automaatkontroll võrdleb igal kuul viidatud sätete teksti; õiguslikult kehtib alati allikas.</p>`;
      return h;
    }
    if (it.t === 'v') {
      let h = '<dl class="kv">';
      h += `<div><dt>Kellele</dt><dd>${esc(it.kes || '')}</dd></div>`;
      if (it.vanus) h += `<div><dt>Vanus</dt><dd>${it.vanus[0]}–${it.vanus[1]} aastat (sünniaasta järgi)</dd></div>`;
      if (it.int) h += `<div><dt>Intervall</dt><dd>${typeof it.int === 'number' ? `iga ${it.int} aasta järel` : esc(it.int)}</dd></div>`;
      if (it.sy) h += `<div><dt>Sünniaastad ${it.aasta}</dt><dd><span class="years">${it.sy.map((y) => `<span>${hl(String(y), re)}</span>`).join('')}</span></dd></div>`;
      if (it.osale) h += `<div><dt>Osalemine</dt><dd>${esc(it.osale)}</dd></div>`;
      if (it.dg) h += `<div><dt>Raviarve</dt><dd>diagnoos <b>${esc(it.dg)}</b>${it.dgAllikas ? ` <span class="inh">(${esc(it.dgAllikas)})</span>` : ''}</dd></div>`;
      for (const k of it.ks || []) {
        const qq = state.qByKey[k];
        if (qq) h += `<div><dt>Kvaliteedisüsteem</dt><dd><button class="badge ks" data-focus="${qq._id}">${esc(qq.n)}</button>${ksValue(qq) ? ` <span class="inh">${esc(ksValue(qq))}</span>` : ''}</dd></div>`;
      }
      h += '</dl>';
      if (it.sy && new Date().getFullYear() > it.aasta) h += `<p class="note">Terviseportaalis on veel ${it.aasta}. aasta sihtrühmad. Uue aasta sünniaastad tulevad siia automaatselt, kui terviseportaal need avaldab.</p>`;
      if (it.erinevus) h += `<p class="note">${esc(it.erinevus)}</p>`;
      if ((it.codes || []).length) {
        h += '<h4>Koodid</h4><div class="tbl"><table><tr><td>Kood</td><td>Tegevus</td><td>Piirhind</td></tr>' + it.codes.map(([c, role]) => {
          const s = state.byCode[c];
          const zl = s ? zeroLabel(s) : null;
          const price = !s ? '' : zl ? `<small>${esc(zl)}</small>` : s.p != null ? fmtEur(s.p) : '';
          const fund = s ? (s.f || []).map((f) => `<span class="badge ${f}">${esc(FUND_SHORT[f])}</span>`).join(' ') : '';
          const same = s && (norm(role).includes(norm(s.n)) || norm(s.n).includes(norm(role)));
          return `<tr><td><button class="code" data-q="${esc(c)}" title="Ava kood">${esc(c)}</button></td><td>${hl(role, re)}${s && !same ? `<br><small class="inh">${esc(s.n)}</small>` : ''}${fund ? '<br>' + fund : ''}</td><td class="num">${price}</td></tr>`;
        }).join('') + '</table></div>';
      }
      const notes = (it.notes || []).concat(it.sy ? ((d.meta.soel || {}).yld || []) : []);
      if (notes.length) h += `<div class="rules"><h4>Selgitused</h4>${notes.map((n) => `<div class="rule">${hl(n, re)}</div>`).join('')}</div>`;
      h += `<div class="actions"><a href="${esc(it.url)}" target="_blank" rel="noopener">${it.src === 'terviseportaal' ? 'Terviseportaal' : 'Tervisekassa'} ↗</a>`
        + (it.juhend ? `<a href="${esc(it.juhend)}" target="_blank" rel="noopener">Tegevusjuhend (PDF) ↗</a>` : '')
        + (it.uuendatud ? `<span class="inh">leht uuendatud ${fmtDate(it.uuendatud)}</span>` : '') + '</div>';
      return h;
    }
    if (it.t === 'l') {
      let h = '<div class="text">';
      for (const b of it.b) {
        if (b.t === 'p') h += `<p>${hl(b.s, re)}</p>`;
        else if (b.t === 'li') h += `<p class="li">${hl(b.s, re)}</p>`;
        else if (b.t === 'tbl') {
          h += '<div class="tbl"><table>' + b.rows.map((r) => '<tr>' + r.map((c) => `<td${/^[\d\s]+,\d\d$/.test(c) ? ' class="num"' : ''}>${hl(c, re)}</td>`).join('') + '</tr>').join('') + '</table></div>';
        }
      }
      h += `</div><div class="actions"><a href="${esc(it.url)}" target="_blank" rel="noopener">Ava Riigi Teatajas ↗</a></div>`;
      return h;
    }
    return '';
  }

  function renderHome() {
    const d = state.data;
    const funds = d.items.filter((x) => x.t === 'f');
    const order = ['f37', 'lisaks', 'f13'];
    funds.sort((a, b) => order.indexOf(a.k) - order.indexOf(b.k));
    const q = (src, par) => d.items.find((x) => x.t === 'l' && x.src === src && x.par === par);
    const quick = [
      ['sate', 'ttl', '§ 2', 'Pearaha', 'Piirhinnad vanuse ja haiguskoormuse järgi'],
      ['sate', 'ttl', '§ 3', 'Baasraha ja lisatasud', 'Koodid 3315, 3317 jt'],
      ['sate', 'metoodika', '§ 5', 'Pearaha arvel osutatavad teenused', 'Mis kuulub pearaha sisse'],
      ['sate', 'metoodika', '§ 8', 'Lisatasud perearstile', 'Kvaliteedisüsteem, lisapädevus jm'],
      ['abiv', 'abivahendid', '§ 2¹', 'Abivahendi tõend', 'Kohustuslikud andmed'],
      ['abiv', 'abivahendid', '§ 3', 'Abivahendi kaart', 'Kaardi andmed ja kord'],
      ['juhi', 'mootorsoidukijuht', '§ 3', 'Juhi tervisenõuded, 1. grupp', 'ja § 4 vastunäidustused'],
      ['juhi', 'mootorsoidukijuht', '§ 5', 'Juhi tervisenõuded, 2. grupp', 'ja § 6 vastunäidustused'],
      ['juhi', 'mootorsoidukijuht', '§ 10', 'Tervisetõendi vormistamine', 'Väljastamine ja kehtivus'],
      ['msq', 'meditsiiniseadmed', '§ 64', 'Meditsiiniseadme kaart', 'Kes kirjutab ja kuidas hüvitatakse'],
    ].map(([cls, src, par, t, sub]) => {
      const it = q(src, par);
      return it ? `<button class="qbtn ${cls}" data-focus="${it._id}"><b>${esc(t)}</b><small>${esc(srcName(src))} ${esc(par)} · ${esc(sub)}</small></button>` : '';
    }).join('');
    const ex = ['holter', 'IGRA', 'HCV', 'jalaortoos', '7115', 'hüpertoonia', '1966', 'haigusleht', 'P21', 'relvaluba', 'nakkushaiguse teatis', 'ratastool', 'juhiload'];
    const tj = d.items.filter((x) => x.t === 'j');
    const groups = [...new Set(tj.map((x) => x.g))];
    const teemaHtml = !tj.length ? '' : `<section class="section"><h2>Igapäevatöö reeglid</h2><div class="tgroups">`
      + groups.map((g) => `<div class="tgroup"><h3>${esc(g)}</h3><div class="quick">`
        + tj.filter((x) => x.g === g).map((x) => `<button class="qbtn teema" data-focus="${x._id}"><b>${esc(x.sn)}</b><small>${x.n !== x.sn ? esc(x.n) + ' · ' : ''}${(x.r || []).length} punkti${(x.e || []).length ? ' · ⚠ ' + x.e.length : ''}</small></button>`).join('')
        + '</div></div>').join('') + '</div></section>';
    const sv = d.items.filter((x) => x.t === 'v');
    const sy0 = soelYear();
    const soelHtml = !sv.length ? '' : `<section class="section"><h2>Vähi sõeluuringud ${sy0}</h2><div class="soel">`
      + sv.map((v) => `<button class="srow" data-focus="${v._id}"><span class="sn"><b>${esc(v.sn)}</b><small>${v.sy ? `${esc(v.kes || '')} · ${esc(ageRange(v))} · ${esc(intText(v))}` : esc(ageRange(v))}</small></span>${v.sy ? `<span class="sy">${v.sy.join(' ')}</span>` : `<span class="sy txt">${esc(v.lyh || '')}</span>`}</button>`).join('')
      + `</div><p class="hint">Sisesta otsingusse sünniaasta (nt 1966): näed, millise sõeluuringu sihtrühma inimene ${sy0}. aastal kuulub.</p>`
      + (new Date().getFullYear() > sy0 ? `<p class="note">Terviseportaalis on veel ${sy0}. aasta sihtrühmad.</p>` : '') + '</section>';
    const ksCards = d.items.filter((x) => x.t === 'q').sort((a, b) => KS_ORDER.indexOf(a.cat) - KS_ORDER.indexOf(b.cat))
      .map((x) => `<button class="qbtn ks" data-focus="${x._id}"><b>${esc(x.k === 'ylevaade' ? 'Ülevaade ja lisatasud' : x.sn)}</b><small>${esc(KS_CAT[x.cat])}${ksValue(x) ? ' · ' + esc(ksValue(x)) : ''} · ${esc(x.par)}</small></button>`).join('');
    el.results.innerHTML = `
      <section class="section"><h2>Rahastus (metoodika § 6)</h2><div class="funds">
        ${funds.map((f) => `<button class="fund ${f.k}" data-fund="${f.k}"><strong>${esc(f.n)}</strong><span>${esc(FUND_HELP[f.k] || '')}</span><span class="cnt">${f.cnt} teenust · ${esc(f.par)}</span></button>`).join('')}
      </div></section>
      ${teemaHtml}
      <section class="section"><h2>Kvaliteedisüsteem (metoodika § 8)</h2><div class="quick">${ksCards}</div></section>
      ${soelHtml}
      <section class="section"><h2>Kiirvalikud</h2><div class="quick">${quick}<button class="qbtn msq" data-filter="m"><b>Meditsiiniseadmed (9MS)</b><small>${d.meta.counts.m || 0} rühma · ortoosid, testribad, sensorid, kompressioontooted jm</small></button></div></section>
      <section class="section"><h2>Proovi otsida</h2><div class="examples">${ex.map((w) => `<button class="chip" data-q="${esc(w)}">${esc(w)}</button>`).join('')}</div></section>
      <section class="section"><h2>Andmete seis</h2><div class="status" id="status"></div></section>
      <section class="section"><h2>Värvid</h2><div class="legend">
        <span><i style="--k:var(--c-f37)"></i>uuringufond 37%</span><span><i style="--k:var(--c-lisaks)"></i>tegevusfond</span><span><i style="--k:var(--c-f13)"></i>teraapiafond 13%</span>
        <span><i style="--k:var(--c-teenus)"></i>muu teenus</span><span><i style="--k:var(--c-abiv)"></i>abivahend</span><span><i style="--k:var(--c-sate)"></i>säte</span><span><i style="--k:var(--c-juhi)"></i>juhi tervisenõuded</span><span><i style="--k:var(--c-ks)"></i>kvaliteedisüsteem</span><span><i style="--k:var(--c-lab)"></i>SYNLABi analüüs</span><span><i style="--k:var(--c-ms)"></i>meditsiiniseade</span><span><i style="--k:var(--c-soel)"></i>sõeluuring</span><span><i style="--k:var(--c-teema)"></i>igapäevatöö reegel</span>
      </div></section>
      <section class="section info"><h2>Kasutamine</h2>
        <p>Otsi nimetuse, koodi, lühendi või argisõnaga (nt „holter“, „TSH“, „6417“). Täpitähti pole vaja. Koodil klõpsates kopeerub see.</p>
        <p>Laborianalüüsi saab otsida SYNLABi nime või lühendiga (nt „IGRA“, „HCV“). Vastes on Tervisekassa kood ja see, kas analüüs kuulub perearsti fondi. Koodi avades on näha kõik selle koodi alla kuuluvad SYNLABi analüüsid.</p>
        <p>Sünniaasta otsing (nt „1966“) näitab, millise rinna-, emakakaela- või soolevähi sõeluuringu sihtrühma inimene sel aastal kuulub. Sünniaastad tulevad terviseportaalist ja neid kontrollitakse kord kuus.</p>
        <p>„Igapäevatöö reeglid“ koondavad haigus- ja hoolduslehe, P21, tervisetõendite, nakkushaiguse teatiste, vaktsineerimise, töökorralduse ja nimistu põhireeglid. Iga punkti juures on viide sättele; ⚠ märgib allikate omavahelisi erinevusi. Otsida võib ka küsimusena (nt „kui kaua makstakse haigushüvitist“).</p>
        <p>Linnuke „Ainult perearstiabi“ peidab teenused, mis ei kuulu perearsti fondidesse, kvaliteedisüsteemi ega perearstiabi peatükki (nt operatsioonid). Täpse koodi otsing näitab koodi alati.</p>
        <p>Rakendus töötab pärast esimest avamist ka võrguta. Telefonis lisa see avakuvale: iPhone'is Safari jagamismenüü → „Lisa avakuvale“, Androidis Chrome'i menüü → „Installi rakendus“.</p>
        <p>Andmed tulevad Riigi Teataja avalikust liidesest ja neid kontrollitakse automaatselt kord kuus. Õiguslikult kehtib alati Riigi Teatajas avaldatud tekst.</p>
        <p id="install-slot"></p>
      </section>`;
    renderStatus();
    renderInstall();
  }

  function renderStatus() {
    const box = $('#status');
    const d = state.data;
    if (!box || !d) return;
    const m = d.meta;
    let h = '';
    for (const [k, s] of Object.entries(m.sources)) {
      const fut = (s.tulevased || []).map((f) => ` <a class="future" href="https://www.riigiteataja.ee/akt/${esc(f.id)}" target="_blank" rel="noopener">uus redaktsioon alates ${fmtDate(f.alates)}</a>`).join('');
      h += `<div class="src"><span><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(srcName(k))}</a>${fut}</span><span>kehtib alates ${fmtDate(s.alates)}</span></div>`;
    }
    if (m.toru) h += `<div class="src"><span>Toru (${esc(m.toru.file)})</span><span>seis ${fmtDate(m.toru.seisuga)}</span></div>`;
    if (m.synlab) h += `<div class="src"><span><a href="${esc(m.synlab.page)}" target="_blank" rel="noopener">SYNLABi hinnakiri</a></span><span>kehtib alates ${esc(m.synlab.seisuga || '')}</span></div>`;
    const tm = m.teemad;
    if (tm) h += `<div class="src"><span>Igapäevatöö reeglite tekstikontroll</span><span>${(tm.warn || []).length ? (tm.warn.length + ' märkust') : 'korras'}</span></div>`;
    const sv = d.items.filter((x) => x.t === 'v' && x.aasta);
    if (sv.length && m.soel) h += `<div class="src"><span><a href="${esc(m.soel.page)}" target="_blank" rel="noopener">Vähi sõeluuringud (terviseportaal)</a></span><span>${Math.max(...sv.map((x) => x.aasta))}. aasta sihtrühmad</span></div>`;
    h += `<div class="src"><span>Viimati kontrollitud</span><span>${fmtDate(m.date)}</span></div>`;
    box.innerHTML = h;
  }

  function renderChips() {
    const d = state.data;
    const c = d.meta.counts;
    const cat = ([k, t, n]) => `<button class="chip" data-filter="${k}" aria-pressed="${!state.fund && state.filter === k}">${t}${n != null ? `<span class="n">${n}</span>` : ''}</button>`;
    const fund = (f) => `<button class="chip fchip" style="--stripe:var(--c-${f.k})" data-fund="${f.k}" aria-pressed="${state.fund === f.k}">${esc(FUND_SHORT[f.k])}<span class="n">${f.cnt}</span></button>`;
    const order = ['f37', 'lisaks', 'f13'];
    const funds = d.items.filter((x) => x.t === 'f').sort((a, b) => order.indexOf(a.k) - order.indexOf(b.k));
    el.chips.innerHTML = [['all', 'Kõik', null], ['s', 'Teenused', state.pa ? d.meta.countsPa || c.s : c.s]].map(cat).join('')
      + funds.map(fund).join('')
      + (c.q ? `<button class="chip kschip" data-filter="q" aria-pressed="${!state.fund && state.filter === 'q'}">Kvaliteedisüsteem<span class="n">${c.q - 1}</span></button>` : '')
      + (c.v ? `<button class="chip soelchip" data-filter="v" aria-pressed="${!state.fund && state.filter === 'v'}">Sõeluuringud<span class="n">${c.v}</span></button>` : '')
      + (c.j ? `<button class="chip teemachip" data-filter="j" aria-pressed="${!state.fund && state.filter === 'j'}">Igapäevatöö reeglid<span class="n">${c.j}</span></button>` : '')
      + (c.b ? `<button class="chip labchip" data-filter="b" aria-pressed="${!state.fund && state.filter === 'b'}">Labor (SYNLAB)<span class="n">${c.b}</span></button>` : '')
      + [['a', 'Abivahendid', c.a]].map(cat).join('')
      + (c.m ? `<button class="chip mschip" data-filter="m" aria-pressed="${!state.fund && state.filter === 'm'}">Meditsiiniseadmed<span class="n">${c.m}</span></button>` : '')
      + [['l', 'Sätted', c.l + c.f], ['k', 'Lingid', c.k]].map(cat).join('')
      + `<label class="chip pa-toggle" title="Väljas: kõik teenused, ka operatsioonid ja haiglateenused"><input type="checkbox" id="pa" ${state.pa ? 'checked' : ''}> Ainult perearstiabi</label>`;
  }

  // ------------------------------------------------------------ sündmused
  let deferredInstall = null;
  const isStandalone = () => {
    try { return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true; } catch (e) { return false; }
  };
  function installSteps() {
    const ua = navigator.userAgent || '';
    if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && 'ontouchend' in document)) {
      return 'iPhone/iPad: ava leht <b>Safaris</b>, vajuta jagamisnuppu (ruut noolega) ja vali <b>„Lisa avakuvale“</b> (Add to Home Screen).';
    }
    if (/Android/.test(ua)) {
      return 'Android: ava Chrome\'i menüü <b>⋮</b> (paremal üleval) ja vali <b>„Installi rakendus“</b> või <b>„Lisa avakuvale“</b>. Kui seda valikut pole, võib rakendus olla juba paigaldatud: otsi rakenduste loendist „Teatmik“.';
    }
    return 'Arvutis: Chrome\'is või Edge\'is vajuta aadressiriba paremas otsas paigaldusikooni või ava menüü ja vali <b>„Installi Perearsti teatmik“</b>.';
  }
  function renderInstall() {
    const btn = $('#install');
    if (btn) btn.hidden = isStandalone();
    const slot = $('#install-slot');
    if (slot) slot.innerHTML = isStandalone() ? 'Rakendus on sellesse seadmesse paigaldatud.' : `<button class="btn solid" data-act="install">Paigalda rakendusena</button>`;
  }
  async function doInstall() {
    const help = $('#install-help');
    if (deferredInstall) {
      deferredInstall.prompt();
      try { await deferredInstall.userChoice; } catch (e) { /* ignoreeri */ }
      deferredInstall = null;
      renderInstall();
      return;
    }
    help.innerHTML = `${installSteps()} <button class="clear-help" data-act="install-close" aria-label="Sulge">×</button>`;
    help.hidden = !help.hidden;
  }

  let toastTimer;
  function toast(msg) {
    let t = $('.toast');
    if (!t) { t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2200);
  }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast(`Kood ${text} kopeeritud`); }
    catch (e) {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); toast(`Kood ${text} kopeeritud`); } catch (e2) { toast(text); }
      ta.remove();
    }
  }

  function setQuery(q) {
    el.q.value = q; state.q = q; state.limit = 60; state.focus = null; state.open.clear();
    route(); syncUrl();
  }
  function goHome() {
    state.q = ''; el.q.value = ''; state.fund = null; state.filter = 'all'; state.focus = null; state.open.clear(); state.limit = 60;
    renderChips(); route(); syncUrl(); window.scrollTo(0, 0);
  }
  function syncUrl() {
    try {
      const u = new URL(location.href);
      if (state.q) u.searchParams.set('q', state.q); else u.searchParams.delete('q');
      history.replaceState(null, '', u);
    } catch (e) { /* ignoreeri */ }
  }

  function setPa(v) {
    state.pa = v;
    try { localStorage.setItem('teatmik-pa', v ? '1' : '0'); } catch (e) { /* ignoreeri */ }
    renderChips(); route();
  }

  function bind() {
    el.q = $('#q'); el.results = $('#results'); el.chips = $('#chips');
    let deb;
    el.q.addEventListener('input', () => {
      clearTimeout(deb);
      deb = setTimeout(() => { state.q = el.q.value; state.limit = 60; state.focus = null; state.open.clear(); route(); syncUrl(); }, 90);
    });
    el.q.addEventListener('keydown', (e) => { if (e.key === 'Escape') goHome(); });
    document.addEventListener('change', (e) => { if (e.target && e.target.id === 'pa') setPa(e.target.checked); });
    $('#clear').addEventListener('click', () => { goHome(); el.q.focus(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== el.q) { e.preventDefault(); el.q.focus(); el.q.select(); }
    });
    document.addEventListener('click', (e) => {
      const t = e.target.closest('[data-copy],[data-open],[data-fund],[data-filter],[data-q],[data-focus],[data-goto],[data-act],[data-labs-all],[data-ms-all]');
      if (!t || !state.data) return;
      if (t.dataset.copy) { e.stopPropagation(); e.preventDefault(); copy(t.dataset.copy); return; }
      if (t.dataset.open) {
        const id = +t.dataset.open;
        if (state.open.has(id)) state.open.delete(id); else state.open.add(id);
        const art = t.closest('article');
        const it = state.data.items[id];
        art.outerHTML = row(it, art.querySelector('.via') ? true : false);
        return;
      }
      if (t.dataset.fund) { state.fund = state.fund === t.dataset.fund ? null : t.dataset.fund; state.filter = 'all'; state.focus = null; state.open.clear(); state.limit = 200; renderChips(); route(); window.scrollTo(0, 0); return; }
      if (t.dataset.filter) { state.filter = t.dataset.filter; state.fund = null; state.focus = null; state.open.clear(); state.limit = 60; renderChips(); route(); return; }
      if (t.dataset.q) { setQuery(t.dataset.q); return; }
      if (t.dataset.focus) { state.focus = +t.dataset.focus; route(); window.scrollTo(0, 0); return; }
      if (t.dataset.goto) {
        const [src, par] = t.dataset.goto.split(':');
        const it = state.data.items.find((x) => x.t === 'l' && x.src === src && x.par === par);
        if (it) { state.focus = it._id; route(); window.scrollTo(0, 0); }
        return;
      }
      if (t.dataset.msAll) {
        state.msAll.add(+t.dataset.msAll);
        const art = t.closest('article');
        art.outerHTML = row(state.data.items[+t.dataset.msAll]);
        return;
      }
      if (t.dataset.labsAll) {
        state.labsAll.add(t.dataset.labsAll);
        const art = t.closest('article');
        const id = +art.querySelector('[data-open]').dataset.open;
        art.outerHTML = row(state.data.items[id]);
        return;
      }
      if (t.dataset.act === 'pa-off') { setPa(false); return; }
      if (t.dataset.act === 'home') { goHome(); return; }
      if (t.dataset.act === 'all') { state.fund = null; state.filter = 'all'; state.limit = 60; renderChips(); route(); return; }
      if (t.dataset.act === 'more') { state.limit += 60; route(); return; }
      if (t.dataset.act === 'install') { doInstall(); return; }
      if (t.dataset.act === 'install-close') { $('#install-help').hidden = true; return; }
    });
    const net = $('#net');
    const upd = () => { net.textContent = navigator.onLine ? 'võrgus' : 'võrguta'; net.classList.toggle('off', !navigator.onLine); };
    window.addEventListener('online', () => { upd(); checkUpdate(); });
    window.addEventListener('offline', upd);
    upd();
    window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredInstall = e; renderInstall(); });
    window.addEventListener('appinstalled', () => { deferredInstall = null; renderInstall(); toast('Rakendus paigaldati'); });
    $('#install').addEventListener('click', doInstall);
    renderInstall();
    try {
      const q0 = new URLSearchParams(location.search).get('q');
      if (q0) { el.q.value = q0; state.q = q0; }
    } catch (e) { /* ignoreeri */ }
  }

  // Avamiste loendur (Abacus, küpsisteta). Üks loendus brauseri seansi kohta; ainult avalikul lehel.
  async function countViews() {
    const el = $('#views');
    if (!el || !navigator.onLine || !/github\.io$/.test(location.hostname)) return;
    const base = 'https://abacus.jasoncameron.dev';
    const path = '/perearsti-teatmik-immot1/avamised';
    let counted = false;
    try { counted = sessionStorage.getItem('teatmik-counted') === '1'; } catch (e) { /* ignoreeri */ }
    try {
      const r = await fetch(base + (counted ? '/get' : '/hit') + path, { cache: 'no-store' });
      if (!r.ok) return;
      const j = await r.json();
      if (typeof j.value !== 'number' || j.value < 0) return;
      try { sessionStorage.setItem('teatmik-counted', '1'); } catch (e) { /* ignoreeri */ }
      el.textContent = `Lehte on avatud ${j.value.toLocaleString('et-EE')} korda (alates 15.10.2026).`;
      el.hidden = false;
    } catch (e) { /* võrguta või teenus maas: ei näita */ }
  }

  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  bind();
  load();
  countViews();
})();
