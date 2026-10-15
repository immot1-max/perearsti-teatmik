/* Perearsti teatmik – otsing ja vaated. Andmed: data/data.json (ehitab build/build.py). */
(() => {
  'use strict';

  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const eur = new Intl.NumberFormat('et-EE', { style: 'currency', currency: 'EUR' });
  const fmtEur = (v) => (v == null ? '' : eur.format(v));
  const fmtDate = (iso) => (iso ? iso.split('-').reverse().join('.') : '');
  const norm = (s) => (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9%.]+/g, ' ').replace(/(^|\s)\.+|\.+(\s|$)/g, ' ').trim();

  const SRC = {
    ttl: 'Tervishoiuteenuste loetelu',
    metoodika: 'Metoodika',
    abivahendid: 'Abivahendite määrus',
    mootorsoidukijuht: 'Mootorsõidukijuhi tervisenõuded',
    toru: 'Toru',
  };
  const FUND_SHORT = { f37: 'Uuringufond 37%', f13: 'Teraapiafond 13%', lisaks: 'Tegevusfond' };
  const FUND_HELP = {
    f37: 'Tasutakse kuni 37% ulatuses nimistu pearahadeks arvestatud summast aastas.',
    f13: 'Tasutakse kuni 13% ulatuses nimistu pearahadeks arvestatud summast aastas.',
    lisaks: 'Tasutakse raviarvega lisaks pearahale, tervishoiuteenuste loetelu piirhinna alusel. Protsendilist piirmäära sellel lõikel ei ole.',
  };
  const AB_LABEL = {
    2: 'Täpsustus', 3: 'Kasutusaeg', 4: 'Tehingu liik', 5: 'Koguseline piirlimiit', 6: 'Individuaalne', 7: 'Seotud hooldusteenusega',
    8: 'Soodustus', 9: 'Piirhind (üür/kuu)', 10: 'Piirhind (müük)', 11: 'Ühik', 12: 'Kellele ja millal', 13: 'Eelduskood',
    14: 'Välistav kood', 15: 'Hoolduse min sagedus', 16: 'Vajaduse tuvastaja', 17: 'Müüja kvalifikatsioon',
  };
  const AB_ORDER = [16, 12, 8, 10, 9, 11, 3, 4, 5, 2, 6, 7, 13, 14, 15, 17];

  const state = { data: null, idx: [], filter: 'all', fund: null, q: '', open: new Set(), limit: 60, focus: null };
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
    state.idx = items.map((it, i) => {
      it._id = i;
      let cls = 'teenus';
      if (it.t === 's') cls = it.f ? it.f[0] : 'teenus';
      else if (it.t === 'a') cls = 'abiv';
      else if (it.t === 'l') cls = it.src === 'mootorsoidukijuht' ? 'juhi' : 'sate';
      else if (it.t === 'k') cls = 'link';
      else if (it.t === 'f') cls = it.k;
      it._cls = cls;
      let name = it.n || '';
      let ctx = '', txt = '', code = '';
      let boost = 0;
      if (it.t === 's') {
        code = norm(it.c);
        ctx = [it.pt, it.sub, it.par].join(' ');
        const rt = (it.r || []).map((ri) => rules[ri]).filter((r) => (r.s.match(/\b[0-9A-Z]{3,8}\b/g) || []).length <= 4);
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
        ctx = SRC[it.src] + ' ' + (it.ptk || '');
        txt = it.b.map((b) => (b.t === 'tbl' ? b.rows.map((r) => r.join(' ')).join(' ') : b.s)).join(' ');
        boost += 8;
      } else if (it.t === 'f') {
        ctx = it.par + ' ' + (it.s || '');
        boost += 40;
      } else if (it.t === 'k') {
        txt = it.d || '';
      }
      return {
        it, code, name: ' ' + norm(name) + ' ', ctx: ' ' + norm(ctx) + ' ', txt: ' ' + norm(txt) + ' ',
        syn: (it.syn || []).map(norm), boost,
      };
    });
    renderChips();
    renderStatus();
    route();
  }

  // ------------------------------------------------------------ otsing
  function passFilter(e) {
    const t = e.it.t;
    if (state.fund) return t === 's' && (e.it.f || []).includes(state.fund);
    if (state.filter === 'all') return true;
    if (state.filter === 'l') return t === 'l' || t === 'f';
    return t === state.filter;
  }

  function search(q) {
    const qn = norm(q);
    const toks = qn.split(' ').filter(Boolean);
    const out = [];
    for (const e of state.idx) {
      if (!passFilter(e)) continue;
      let score = 0, via = false, ok = true;
      for (const t of toks) {
        let s = 0;
        if (e.code) {
          if (e.code === t) s = 400;
          else if (t.length >= 2 && e.code.startsWith(t)) s = 150;
        }
        if (e.name.includes(' ' + t + ' ')) s = Math.max(s, 60);
        else if (e.name.includes(' ' + t)) s = Math.max(s, 45);
        else if (t.length >= 3 && e.name.includes(t)) s = Math.max(s, 20);
        for (const sy of e.syn) {
          if (sy === t) s = Math.max(s, 90);
          else if ((' ' + sy).includes(' ' + t)) s = Math.max(s, 40);
        }
        if (!s && t.length >= 6) {
          for (const cut of [t.slice(0, -1), t.slice(0, -2)]) {
            if (e.name.includes(' ' + cut)) { s = 30; break; }
            if (e.syn.some((sy) => (' ' + sy).includes(' ' + cut))) { s = 30; break; }
          }
        }
        if (!s && e.ctx.includes(' ' + t)) s = 12;
        if (!s && e.txt.includes(' ' + t)) { s = 6; via = true; }
        if (!s) { ok = false; break; }
        score += s;
      }
      if (!ok) continue;
      if (toks.length > 1) for (const sy of e.syn) if (sy === qn) score += 200;
      if (e.code && e.code === qn) score += 600;
      out.push({ e, score: score + e.boost, via });
    }
    out.sort((a, b) => b.score - a.score || a.e.name.length - b.e.name.length);
    return { list: out, toks };
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
      r.innerHTML = `<div class="summary"><span>${esc(SRC[it.src] || '')}</span><button class="btn" data-act="home">← Avaleht</button></div><div class="list">${row(it)}</div>`;
      return;
    }
    if (!q && !state.fund && (state.filter === 'all' || state.filter === 's')) { renderHome(); return; }
    let list;
    if (q) {
      list = search(q).list.map((x) => ({ it: x.e.it, via: x.via }));
    } else {
      list = state.idx.filter(passFilter).map((e) => ({ it: e.it }));
      if (state.fund || state.filter === 's') {
        list.sort((a, b) => (a.it.pt || '').localeCompare(b.it.pt || '', 'et') || a.it.n.localeCompare(b.it.n, 'et'));
      }
    }
    const total = list.length;
    const shown = list.slice(0, state.limit);
    let html = '';
    const fundItem = state.fund ? state.data.items.find((x) => x.t === 'f' && x.k === state.fund) : null;
    if (fundItem) {
      html += `<div class="row ${fundItem.k}"><div class="detail" style="border-top:0"><div class="text"><p><strong>${esc(fundItem.n)}</strong> · metoodika ${esc(fundItem.par)}</p><p>${esc(FUND_HELP[fundItem.k] || '')}</p>${state.data.meta.starRule && fundItem.k === 'f37' ? `<p>* ${esc(state.data.meta.starRule)}</p>` : ''}</div><div class="actions"><a href="${esc(fundItem.url)}" target="_blank" rel="noopener">Säte Riigi Teatajas ↗</a></div></div></div>`;
    }
    html += `<div class="summary"><span>${total ? `${total} vastet` : ''}${q && total > state.limit ? `, näitan ${state.limit}` : ''}</span>${q || state.fund || state.filter !== 'all' ? '<button class="btn" data-act="home">Tühjenda</button>' : ''}</div>`;
    if (!total) {
      html += `<p class="empty">Midagi ei leitud. Proovi lühemat sõna või koodi algust.</p>`;
      if (q && (state.fund || state.filter !== 'all')) html += '<button class="btn solid" data-act="all">Otsi kõigist kategooriatest</button>';
    } else {
      html += '<div class="list">';
      const grouped = !q && (state.fund || state.filter === 'a' || state.filter === 'l');
      let lastG = null;
      for (const x of shown) {
        if (grouped) {
          const g = x.it.t === 'a' ? (x.it.g || [])[0] || x.it.n : x.it.t === 'l' ? SRC[x.it.src] : x.it.t === 'f' ? 'Fondid' : x.it.pt || SRC[x.it.src];
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
    if (it.t === 's') {
      const fund = (it.f || []).map((f) => `<span class="badge ${f}">${esc(FUND_SHORT[f] || f)}</span>`).join('');
      const price = it.p != null ? fmtEur(it.p) : '';
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${price}</span>
        <span class="meta"><span class="code" data-copy="${esc(it.c)}" title="Kopeeri kood">${esc(it.c)}</span>${fund}${it.fn ? '<span class="badge f37">* ainult S00–S09</span>' : ''}<span>${esc(it.par ? it.par + ' ' + (it.pt || '') : SRC[it.src])}</span>${via ? '<span class="via">· vaste tingimustes</span>' : ''}</span>`;
    } else if (it.t === 'a') {
      const v = it.v;
      const price = v['10'] ? `${esc(v['10'])} €` : v['9'] ? `${esc(v['9'])} € <small>/kuu</small>` : '';
      const pe = /perearst/i.test(v['16'] || '') ? '<span class="badge abiv">perearst võib tuvastada</span>' : '';
      head = `<span class="name">${hl(it.n, re)}</span><span class="price">${price}</span>
        <span class="meta"><span class="code" data-copy="${esc(it.c)}" title="Kopeeri kood">${esc(it.c)}</span>${v['8'] ? `<span class="badge plain">${esc(v['8'])}</span>` : ''}${pe}${it.grp ? '<span class="badge plain">rühm</span>' : ''}<span>${esc((it.g || []).slice(-1)[0] || '')}</span>${via ? '<span class="via">· vaste kirjelduses</span>' : ''}</span>`;
    } else if (it.t === 'l') {
      head = `<span class="name">${esc(it.par)} ${hl(it.n, re)}</span><span></span><span class="meta"><span>${esc(SRC[it.src])}</span>${via ? '<span class="via">· vaste tekstis</span>' : ''}</span>`;
    }
    return `<article class="row ${it._cls}"><button class="head" data-open="${it._id}" aria-expanded="${open}">${head}</button>${open ? `<div class="detail">${detail(it)}</div>` : ''}</article>`;
  }

  function detail(it) {
    const d = state.data;
    const re = state.hl;
    if (it.t === 's') {
      let h = '<dl class="kv">';
      if (it.p != null) {
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
      if (it.r && it.r.length) {
        h += '<div class="rules"><h4>Tingimused ja seotud sätted</h4>';
        for (const ri of it.r) {
          const rr = d.rules[ri];
          h += `<div class="rule"><span class="ref">${esc(SRC[rr.src])} ${esc(rr.par)}</span>${hl(rr.s, re)} <a href="${esc(rr.url)}" target="_blank" rel="noopener">↗</a></div>`;
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
    ].map(([cls, src, par, t, sub]) => {
      const it = q(src, par);
      return it ? `<button class="qbtn ${cls}" data-focus="${it._id}"><b>${esc(t)}</b><small>${esc(SRC[src])} ${esc(par)} · ${esc(sub)}</small></button>` : '';
    }).join('');
    const ex = ['holter', 'tümpanomeeter', 'TSH', 'spiraal', 'kopsu röntgen', 'ratastool', 'juhiload', 'uuringufond'];
    el.results.innerHTML = `
      <section class="section"><h2>Rahastus (metoodika § 6)</h2><div class="funds">
        ${funds.map((f) => `<button class="fund ${f.k}" data-fund="${f.k}"><strong>${esc(f.n)}</strong><span>${esc(FUND_HELP[f.k] || '')}</span><span class="cnt">${f.cnt} teenust · ${esc(f.par)}</span></button>`).join('')}
      </div></section>
      <section class="section"><h2>Kiirvalikud</h2><div class="quick">${quick}</div></section>
      <section class="section"><h2>Proovi otsida</h2><div class="examples">${ex.map((w) => `<button class="chip" data-q="${esc(w)}">${esc(w)}</button>`).join('')}</div></section>
      <section class="section"><h2>Andmete seis</h2><div class="status" id="status"></div></section>
      <section class="section"><h2>Värvid</h2><div class="legend">
        <span><i style="--k:var(--c-f37)"></i>uuringufond 37%</span><span><i style="--k:var(--c-lisaks)"></i>tegevusfond</span><span><i style="--k:var(--c-f13)"></i>teraapiafond 13%</span>
        <span><i style="--k:var(--c-teenus)"></i>muu teenus</span><span><i style="--k:var(--c-abiv)"></i>abivahend</span><span><i style="--k:var(--c-sate)"></i>säte</span><span><i style="--k:var(--c-juhi)"></i>juhi tervisenõuded</span>
      </div></section>
      <section class="section info"><h2>Kasutamine</h2>
        <p>Otsi nimetuse, koodi, lühendi või argisõnaga (nt „holter“, „TSH“, „6417“). Täpitähti pole vaja. Koodil klõpsates kopeerub see.</p>
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
      h += `<div class="src"><span><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(SRC[k])}</a>${fut}</span><span>kehtib alates ${fmtDate(s.alates)}</span></div>`;
    }
    if (m.toru) h += `<div class="src"><span>Toru (${esc(m.toru.file)})</span><span>seis ${fmtDate(m.toru.seisuga)}</span></div>`;
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
    el.chips.innerHTML = [['all', 'Kõik', null], ['s', 'Teenused', c.s]].map(cat).join('')
      + funds.map(fund).join('')
      + [['a', 'Abivahendid', c.a], ['l', 'Sätted', c.l + c.f], ['k', 'Lingid', c.k]].map(cat).join('');
  }

  // ------------------------------------------------------------ sündmused
  let deferredInstall = null;
  function renderInstall() {
    const slot = $('#install-slot');
    if (slot && deferredInstall) slot.innerHTML = '<button class="btn solid" data-act="install">Paigalda rakendusena</button>';
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

  function bind() {
    el.q = $('#q'); el.results = $('#results'); el.chips = $('#chips');
    let deb;
    el.q.addEventListener('input', () => {
      clearTimeout(deb);
      deb = setTimeout(() => { state.q = el.q.value; state.limit = 60; state.focus = null; state.open.clear(); route(); syncUrl(); }, 90);
    });
    el.q.addEventListener('keydown', (e) => { if (e.key === 'Escape') goHome(); });
    $('#clear').addEventListener('click', () => { goHome(); el.q.focus(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== el.q) { e.preventDefault(); el.q.focus(); el.q.select(); }
    });
    document.addEventListener('click', (e) => {
      const t = e.target.closest('[data-copy],[data-open],[data-fund],[data-filter],[data-q],[data-focus],[data-goto],[data-act]');
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
      if (t.dataset.act === 'home') { goHome(); return; }
      if (t.dataset.act === 'all') { state.fund = null; state.filter = 'all'; state.limit = 60; renderChips(); route(); return; }
      if (t.dataset.act === 'more') { state.limit += 60; route(); return; }
      if (t.dataset.act === 'install' && deferredInstall) { deferredInstall.prompt(); deferredInstall = null; renderInstall(); }
    });
    const net = $('#net');
    const upd = () => { net.textContent = navigator.onLine ? 'võrgus' : 'võrguta'; net.classList.toggle('off', !navigator.onLine); };
    window.addEventListener('online', () => { upd(); checkUpdate(); });
    window.addEventListener('offline', upd);
    upd();
    window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredInstall = e; renderInstall(); });
    try {
      const q0 = new URLSearchParams(location.search).get('q');
      if (q0) { el.q.value = q0; state.q = q0; }
    } catch (e) { /* ignoreeri */ }
  }

  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  bind();
  load();
})();
