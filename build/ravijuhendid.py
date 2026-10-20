"""Ravijuhendid (ravijuhend.ee): kõigi kinnitatud ravijuhendite ja käsitlusjuhendite otselingid,
lisad ning valitud lisade eelvaated, mida rakendus näitab juhendi kirjes.

Allikad: ravijuhend.ee loendi JSON (/ajax/guides, sama, mida kasutab leht /tervishoiuvarav/juhendid)
ja iga juhendi leht (kood, kinnitamise ja avaldamise kuupäev, erialad, võtmesõnad, lisad,
patsiendijuhend). Eelvaated tehakse lisa PDF-ist (leheküljed pildiks) või, kui lisal PDF-i pole,
juhendi lehe lisa piltidest. Pilt tehakse uuesti ainult siis, kui allika räsi muutus; vanad pildid
kustutatakse. Kui ravijuhend.ee pole kättesaadav, jääb alles eelmine seis ja aruandesse tuleb märkus.

Seadistus: build/ravijuhendid.json (millised lisad eelvaatena, lisasünonüümid, käsitsi lisatud tabelid).
"""
import hashlib
import html
import io
import json
import os
import re
import urllib.parse

import pdfplumber
from PIL import Image, ImageChops

BASE = "https://ravijuhend.ee"
LIST = BASE + "/ajax/guides"
AJAX_H = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
PV_DIR = "lisad"  # repo juures; GitHub Pages serveerib
DPI = 160
TXT_MAX = 8000
# Juhendi lehe võtmesõnad, mis ei sobi otsingu sünonüümiks (oleksid kõigil juhenditel).
VS_SKIP = {"ravijuhend", "ravijuhendid", "juhend", "käsitlusjuhend", "eesti ravijuhend"}


def gkey(kind, gid):
    """Ravijuhendi lehe tüübid on eraldi numeratsiooniga: /juhendid/{id} ja /juhendid-gp/{id}."""
    return ("gp" if kind == "gp-guide" else "rj") + str(gid)


def fetch_list(get, params):
    out, page = [], 1
    while page <= 30:
        q = dict(params, page=page)
        d = json.loads(get(LIST + "?" + urllib.parse.urlencode(q), timeout=60, tries=3, headers=AJAX_H))
        out += d.get("data") or []
        if page >= (d.get("last_page") or 1):
            break
        page += 1
    return out


def clean(s):
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def lisa_title(s):
    return clean(s).rstrip(" .")


def to_iso(s):
    m = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def lisa_nr(name):
    m = re.match(r"Lisa\s+(\d+)", name or "", re.I)
    return int(m.group(1)) if m else None


def parse_page(page, url):
    """Juhendi lehe külgpaneel (Lisainfo ja allalaadimine) ja lisad."""
    r = {"lisad": [], "acc": {}}
    i = page.find("Lisainfo ja allalaadimine")
    side = page[i:] if i >= 0 else ""
    m = re.search(r'<a href="([^"]+)"\s+class="button button--blue guide__download"', side)
    if m:
        r["pdf"] = urllib.parse.urljoin(BASE, html.unescape(m.group(1)))
    m = re.search(r'<a href="([^"]+)"\s+class="button button--green"[^>]*>\s*Vaata patsiendijuhendit', side)
    if m:
        r["pj"] = urllib.parse.urljoin(BASE, html.unescape(m.group(1)))
    m = re.search(r'class="guide__status[^"]*">\s*([^<]+?)\s*<', side)
    if m:
        r["staatus"] = clean(m.group(1))
    for lab, body in re.findall(r'guide__meta__label">\s*<strong>([^<]+)</strong>\s*</p>(.*?)</div>', side, re.S):
        lab = clean(lab).lower()
        if lab.startswith("kinnitatud"):
            r["kinnitatud"] = to_iso(clean(body))
        elif lab.startswith("avaldatud"):
            r["avaldatud"] = to_iso(clean(body))
        elif lab.startswith("juhendi kood"):
            r["kood"] = clean(body) or None
        elif lab.startswith("erialad"):
            r["er"] = [clean(x).lstrip("• ").strip() for x in re.findall(r"<li>(.*?)</li>", body, re.S) if clean(x).strip("• ")]
        elif "võtmesõnad" in lab:
            r["vs"] = [w.strip() for w in re.split(r"[,;]", clean(body)) if len(w.strip()) > 1 and w.strip().lower() not in VS_SKIP]
    j = side.find("Ravijuhendi lisad")
    if j >= 0:
        seg = side[j:]
        k = seg.find("<h2", 10)
        seg = seg[:k] if k > 0 else seg[:20000]
        for href, name in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', seg, re.S):
            r["lisad"].append([lisa_title(name), urllib.parse.urljoin(BASE, html.unescape(href))])
    # Lisad lehe sisus (vana tüüpi juhendid): pealkiri ja pildid; mõnel juhendil on lisad ainult nii.
    for m in re.finditer(r'<h3 class="guide-accordion__title">\s*(Lisa\s+\d+[^<]*)</h3>\s*<div class="guide-accordion__body">', page):
        start = m.end()
        nxt = [x for x in (page.find('<div class="guide-accordion__item">', start), page.find('<h2 class="guide-accordion__title">', start)) if x > 0]
        body = page[start:min(nxt)] if nxt else page[start:start + 50000]
        imgs = [urllib.parse.urljoin(BASE, html.unescape(s)) for s in re.findall(r'<img[^>]+src="([^"]+)"', body)]
        r["acc"][lisa_title(m.group(1))] = imgs
    have = {lisa_nr(n) for n, _ in r["lisad"]}
    for name in r["acc"]:
        if lisa_nr(name) not in have:
            r["lisad"].append([name, url])
    r["lisad"].sort(key=lambda x: (lisa_nr(x[0]) or 99, x[0]))
    return r


def trim(im, pad=14):
    """Valge ääre eemaldamine, et väike eelvaade oleks loetav."""
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im, bg).convert("L").point(lambda p: 255 if p > 16 else 0)
    box = diff.getbbox()
    if not box:
        return im
    left, top, right, bottom = box
    return im.crop((max(0, left - pad), max(0, top - pad), min(im.width, right + pad), min(im.height, bottom + pad)))


def drop_footer(im, min_gap=60, max_block=110):
    """Juhendi PDF-i lehe jalus (lehekülje number ja joon) välja: kui lehe alumises 12%-s on väike plokk,
    mida eraldab muust sisust suur tühi vahe, lõigatakse see ära."""
    g = im.convert("L").point(lambda p: 255 if p < 235 else 0).resize((1, im.height), Image.BOX)
    rows = [v > 0 for v in g.getdata()]
    blocks, start = [], None
    for y, on in enumerate(rows + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            blocks.append([start, y])
            start = None
    foot = [b for b in blocks if b[0] > im.height * 0.86]
    body = [b for b in blocks if b[0] <= im.height * 0.86]
    if foot and body and foot[-1][1] - foot[0][0] <= max_block and foot[0][0] - body[-1][1] >= min_gap:
        return im.crop((0, 0, im.width, body[-1][1] + 1))
    return im


def flatten(im):
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return bg.convert("RGB")
    return im.convert("RGB")


def save_png(im, path, footer=False):
    im = flatten(im)
    if footer:
        im = drop_footer(im)
    im = trim(im)
    q = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q.save(path, optimize=True)
    return [im.width, im.height]


def pick_lisa(info, want):
    """Eelvaate lisa: number ja kontrollsõna. Kui number muutus, otsitakse sama sõnaga lisa."""
    nr, word = want.get("lisa"), (want.get("sisaldab") or "").lower()
    by_nr = [x for x in info["lisad"] if lisa_nr(x[0]) == nr]
    if by_nr and (not word or word in by_nr[0][0].lower()):
        return by_nr[0], None
    alt = [x for x in info["lisad"] if word and word in x[0].lower()]
    if alt:
        return alt[0], f"lisa {nr} asemel leiti sama sisuga „{alt[0][0]}“ (lisade numeratsioon muutus?)"
    return None, f"lisa {nr} („{word}“) ei leitud"


def lisa_pages(pdf, nr, max_lk=3):
    """Lisa leheküljed kogu juhendi PDF-is: alates lehest, kus on pealkiri „Lisa N.“ (sisukord välja arvatud),
    kuni järgmise lisa pealkirjani (kõige rohkem max_lk lehte)."""
    head = re.compile(rf"(^|\n)\s*Lisa\s+{nr}\s*\.")
    nxt = re.compile(rf"(^|\n)\s*(Lisa\s+{nr + 1}\s*\.|Kasutatud kirjandus)")
    start = None
    texts = [(p.extract_text() or "") for p in pdf.pages]
    for i, t in enumerate(texts):
        if "Sisukord" in t[:200] or re.search(r"\.{5,}", t):
            continue
        if head.search(t):
            start = i
            break
    if start is None:
        return []
    pages = [start]
    for i in range(start + 1, min(start + max_lk, len(texts))):
        if nxt.search(texts[i]):
            break
        pages.append(i)
    return pages


def make_preview(get, key, lisa, info, prev_pv, root, want):
    """Lisa eelvaade: lisa enda PDF, selle puudumisel lisa leheküljed kogu juhendi PDF-ist
    (vektorgraafika, terav) ja viimase võimalusena juhendi lehe pildid."""
    name, url = lisa
    nr = lisa_nr(name) or 0
    mode, pages = None, []
    if "/attachments/" in url:
        mode, parts = "pdf", [get(url, timeout=90, tries=3)]
    elif info.get("pdf"):
        raw = get(info["pdf"], timeout=180, tries=3)
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            pages = lisa_pages(pdf, nr, want.get("lk", 3))
        if pages:
            mode, parts = "juhend", [raw]
    if not mode:
        imgs = info["acc"].get(name) or []
        if not imgs:
            raise RuntimeError(f"{name}: lisal pole PDF-i ega pilte")
        mode, parts = "img", [get(urllib.parse.quote(u, safe=":/?=&%"), timeout=90, tries=3) for u in imgs]
    sha = hashlib.sha256(b"".join(parts) + json.dumps(pages).encode()).hexdigest()[:16]
    if prev_pv and prev_pv.get("sha") == sha and all(os.path.exists(os.path.join(root, p)) for p, _, _ in prev_pv.get("img", [])):
        return dict(prev_pv, n=name, u=url), False
    os.makedirs(os.path.join(root, PV_DIR), exist_ok=True)
    out, txt = [], ""
    if mode in ("pdf", "juhend"):
        with pdfplumber.open(io.BytesIO(parts[0])) as pdf:
            idx = pages if mode == "juhend" else list(range(min(len(pdf.pages), 12)))
            for i, pi in enumerate(idx, 1):
                page = pdf.pages[pi]
                im = page.to_image(resolution=DPI).original
                rel = f"{PV_DIR}/{key}-l{nr}-{sha[:8]}-{i}.png"
                out.append([rel] + save_png(im, os.path.join(root, rel), footer=mode == "juhend"))
                txt += " " + (page.extract_text() or "")
    else:
        for i, b in enumerate(parts, 1):
            im = Image.open(io.BytesIO(b))
            rel = f"{PV_DIR}/{key}-l{nr}-{sha[:8]}-{i}.png"
            out.append([rel] + save_png(im, os.path.join(root, rel)))
    pv = {"n": name, "u": url, "sha": sha, "img": out, "txt": re.sub(r"\s+", " ", txt).strip()[:TXT_MAX]}
    if mode == "juhend":
        pv["lk"] = [p + 1 for p in pages]  # juhendi PDF-i leheküljed
    return pv, True


def collect(get, cfg, prev_items, root, today):
    """Tagastab (kirjed, meta). Kirje liik 'g'."""
    warn, notes = [], []
    prev = {x["k"]: x for x in prev_items or []}
    conf = cfg.get("juhendid", {})
    manual = cfg.get("kasitsi", {})
    rows = []
    try:
        for t in cfg["tyybid"]:
            for x in fetch_list(get, {"types": t["types"], "status": t["status"], "subjects": "all", "order": "a-z"}):
                rows.append((t, x))
    except Exception as e:  # noqa: BLE001
        warn.append(f"Ravijuhendite loendit ei saanud ({str(e)[:120]}); kasutan eelmist seisu.")
        return list(prev.values()), {"warn": warn, "notes": notes, "ok": False}
    if not rows:
        warn.append("Ravijuhendite loend oli tühi; kasutan eelmist seisu.")
        return list(prev.values()), {"warn": warn, "notes": notes, "ok": False}
    skip = set(cfg.get("valja", []))
    items, seen = [], set()
    for t, x in rows:
        gid = x.get("id") or x.get("guide_id")
        k = gkey(x.get("kind"), gid)
        if k in seen or k in skip or re.match(r"(?i)arenduse test", x.get("title") or ""):
            continue
        seen.add(k)
        url = x.get("url")
        it = {"t": "g", "k": k, "liik": t["liik"], "n": re.sub(r"\s+", " ", x.get("title") or "").strip(), "u": url}
        try:
            info = parse_page(get(url, timeout=90, tries=3).decode("utf-8", "replace"), url)
        except Exception as e:  # noqa: BLE001
            old = prev.get(k)
            warn.append(f"{it['n']}: juhendi lehte ei saanud ({str(e)[:80]}); {'kasutan eelmist seisu' if old else 'ainult link'}.")
            items.append(old or it)
            continue
        for f in ("kood", "kinnitatud", "avaldatud", "staatus", "er", "pdf", "pj"):
            if info.get(f):
                it[f] = info[f]
        if not it.get("kood") and x.get("code"):
            it["kood"] = x["code"]
        it["lisad"] = info["lisad"]
        c = conf.get(k, {})
        syn = list(dict.fromkeys((info.get("vs") or []) + c.get("syn", [])))
        if syn:
            it["syn"] = syn
        for f in ("sn", "ks", "lingid", "seotud"):
            if c.get(f):
                it[f] = c[f]
        if c.get("kasitsi"):
            mk = manual.get(c["kasitsi"])
            if mk:
                it["mk"] = mk
            else:
                warn.append(f"{it['n']}: käsitsi sisu „{c['kasitsi']}“ puudub")
        old = prev.get(k) or {}
        if old and (old.get("kood"), old.get("kinnitatud")) != (it.get("kood"), it.get("kinnitatud")):
            notes.append(f"Uus versioon: {it['n']} ({old.get('kood') or '–'} → {it.get('kood') or '–'}, kinnitatud {it.get('kinnitatud') or '–'})")
            if it.get("mk"):
                warn.append(f"{it['n']}: juhend uuenes, käsitsi lisatud „{it['mk'].get('n')}“ vajab ülevaatust")
        if old and [x[0] for x in old.get("lisad", [])] != [x[0] for x in it["lisad"]]:
            notes.append(f"Lisad muutusid: {it['n']}")
        pvs = []
        old_pv = {lisa_nr(p["n"]): p for p in old.get("pv", [])}
        for want in c.get("eelvaade", []):
            lisa, w = pick_lisa(info, want)
            if w:
                warn.append(f"{it['n']}: eelvaade: {w}")
            if not lisa:
                continue
            try:
                pv, changed = make_preview(get, k, lisa, info, old_pv.get(lisa_nr(lisa[0])) or old_pv.get(want.get("lisa")), root, want)
            except Exception as e:  # noqa: BLE001
                p0 = old_pv.get(want.get("lisa"))
                warn.append(f"{it['n']}: {lisa[0]}: eelvaadet ei saanud ({str(e)[:80]}){'; jääb eelmine' if p0 else ''}.")
                if p0:
                    pvs.append(p0)
                continue
            if changed and old_pv:
                notes.append(f"Eelvaade uuenes: {it['n']}, {lisa[0]}")
            pvs.append(pv)
        if pvs:
            it["pv"] = pvs
        items.append(it)
    gone = [v["n"] for kk, v in prev.items() if kk not in seen]
    new = [x["n"] for x in items if prev and x["k"] not in prev]
    for n in new:
        notes.append(f"Uus juhend loendis: {n}")
    for n in gone:
        notes.append(f"Juhend kadus loendist: {n}")
    missing = [kk for kk in conf if kk not in seen]
    for kk in missing:
        warn.append(f"Seadistuses olevat juhendit {kk} loendis ei ole (build/ravijuhendid.json)")
    # vanad eelvaatepildid ära
    keep = {p for x in items for pv in x.get("pv", []) for p, _, _ in pv.get("img", [])}
    d = os.path.join(root, PV_DIR)
    if os.path.isdir(d):
        for fn in os.listdir(d):
            rel = f"{PV_DIR}/{fn}"
            if fn.endswith(".png") and rel not in keep:
                os.remove(os.path.join(d, fn))
    order = {t["liik"]: i for i, t in enumerate(cfg["tyybid"])}
    items.sort(key=lambda x: (order.get(x.get("liik"), 9), x["n"].lower()))
    return items, {"warn": warn, "notes": notes, "ok": True, "page": cfg["_meta"].get("loend"),
                   "pj": cfg["_meta"].get("patsiendijuhendid"), "date": today}


def fingerprint(items):
    return json.dumps([[x["k"], x["n"], x.get("kood"), x.get("kinnitatud"), x.get("avaldatud"), x.get("pdf"), x.get("pj"),
                        x.get("lisad"), [p.get("sha") for p in x.get("pv", [])], x.get("syn"), x.get("sn"), x.get("ks"), x.get("lingid"),
                        x.get("seotud"), x.get("mk")] for x in items], ensure_ascii=False, sort_keys=True)
