#!/usr/bin/env python3
"""Perearsti teatmiku andmete ehitaja.

Laeb Riigi Teataja avalikust API-st kehtivad redaktsioonid, parsib need ja
kirjutab rakenduse jaoks faili data/data.json. Kui allikad pole eelmisest
korrast muutunud, ei tee midagi (vt --force).

Kasutus:
    python build/build.py            # kontrolli ja ehita vajadusel
    python build/build.py --force    # ehita igal juhul
"""
import argparse
import base64
import datetime as dt
import glob
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import openpyxl
import pdfplumber
from lxml import html as lhtml

import met_lisad
import muutused

BUILD_VERSION = "2"
API = "https://www.riigiteataja.ee/public-api/api/v1"
RT = "https://www.riigiteataja.ee/akt/"
NS = "{maarus_1_10.02.2010}"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
TODAY = dt.date.today()
# Fondide argikeelsed nimed (määruse tekstis neid ei ole)
FUND_NAMES = {"f37": "Uuringufond", "lisaks": "Tegevusfond", "f13": "Teraapiafond"}
# Kui fondil on täpsustus, asendab see pealkirjas protsendi (protsent on siis rakenduse selgitusreal).
FUND_SUB = {"f13": "keskuse enda füsioterapeut, psühholoog, logopeed"}


# ----------------------------------------------------------------- võrk

_last_call = {}


def http_get(url, timeout=300, tries=6):
    """GET koos ettevaatliku tempoga: sama hosti päringute vahel vähemalt 0,6 s;
    vastuse 429 (liiga palju päringuid) korral oodatakse Retry-After või kasvava pausi võrra."""
    host = urllib.parse.urlsplit(url).netloc
    last = None
    for i in range(tries):
        wait = (1.5 if "riigiteataja" in host else 0.6) - (time.time() - _last_call.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "perearsti-teatmik/1 (+github pages)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                break
            ra = e.headers.get("Retry-After") if e.headers else None
            pause = int(ra) if ra and ra.isdigit() else (20 * (i + 1) if e.code == 429 else 3 * (i + 1))
            time.sleep(min(pause, 120))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Päring ebaõnnestus: {url}: {last}")


def api_json(path):
    return json.loads(http_get(API + path, timeout=60))


def api_meta(akt_id, cache_dir):
    """Redaktsiooni metaandmed. Kehtiva akti andmed hoitakse vahemälus kuni 20 päeva
    (kehtetuks tunnistamisel tekib uus redaktsioon uue ID-ga), et Riigi Teatajat mitte koormata."""
    p = os.path.join(cache_dir, f"{akt_id}.meta.json") if cache_dir else None
    if p and os.path.exists(p) and time.time() - os.path.getmtime(p) < 20 * 86400:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    meta = api_json(f"/akt/{akt_id}")
    if p:
        os.makedirs(cache_dir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
    return meta


def fetch_xml(akt_id, cache_dir):
    """Redaktsiooni ID on muutumatu, seega võib vahemälu kasutada."""
    p = os.path.join(cache_dir, f"{akt_id}.xml") if cache_dir else None
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read()
    data = http_get(f"{API}/akt/{akt_id}/xml").decode("utf-8")
    if p:
        os.makedirs(cache_dir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(data)
    return data


def utc_to_local_date(s):
    if not s:
        return None
    d = dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + dt.timedelta(hours=12)
    return d.date().isoformat()


def content_chain(red):
    """Grupi sisuga redaktsioonid (mitte kehtetuks tunnistamise märge) jõustumise järjekorras."""
    out = [{"id": str(r["id"]), "alates": utc_to_local_date(r["kehtivuseAlgus"])} for r in red["redaktsioonid"]
           if not r.get("kehtivKehtetus")]
    return sorted(out, key=lambda x: x["alates"] or "")


def resolve_current(grupi_id, cache_dir, depth=0, pre=None):
    """Leiab grupi kehtiva redaktsiooni. Kui akt on kehtetuks tunnistatud ja
    asendatud uue aktiga (nagu tervishoiuteenuste loeteluga juhtub), järgib
    kehtetuks tunnistamise märget uue aktini. info["_chain"] on sisuga redaktsioonide
    ahel koos asendatud akti(de) redaktsioonidega (muudatuste vaate jaoks)."""
    if depth > 4:
        raise RuntimeError("Liiga pikk asendusaktide ahel")
    red = api_json(f"/akt/{grupi_id}/redaktsioonid")
    chain = (pre or []) + content_chain(red)
    kid = red["kehtivRedaktsioon"]
    meta = api_meta(kid, cache_dir)
    xml = fetch_xml(kid, cache_dir)
    body = re.sub(r"<metaandmed>.*?</metaandmed>", "", xml, flags=re.S)
    m = re.search(r"<oigusakt[^>]*>\s*(?:<aktinimi>.*?</aktinimi>)?\s*<muutmismarge>(.*?)</muutmismarge>", body, flags=re.S)
    is_repealed = meta.get("aktiStaatus") == "KEHTETU" or (
        m and "Kehtetu" in m.group(1) and re.search(r"<sisu[^>]*/>", body))
    if is_repealed and m:
        new_id = re.search(r"<aktViide[^>]*>(\d+)</aktViide>", m.group(1)).group(1)
        new_meta = api_meta(new_id, cache_dir)
        return resolve_current(new_meta["grupiId"], cache_dir, depth + 1, pre=chain)
    future = []
    for r in red["redaktsioonid"]:
        alg = utc_to_local_date(r["kehtivuseAlgus"])
        if alg and alg > TODAY.isoformat():
            future.append({"id": str(r["id"]), "alates": alg})
    ap = meta["aktiParameetrid"]
    return {
        "grupiId": grupi_id,
        "id": str(kid),
        "pealkiri": ap["pealkiri"],
        "alates": utc_to_local_date(ap.get("kehtivuseAlgus")),
        "kuni": utc_to_local_date(ap.get("kehtivuseLopp")),
        "tulevased": sorted(future, key=lambda x: x["alates"]),
        "url": RT + str(kid),
        "_chain": chain,
    }, xml


# ----------------------------------------------------------------- XML tekst

def strip_files(xml):
    return re.sub(r"(<fail[^>]*>)[A-Za-z0-9+/=\s]{200,}(</fail>)", r"\1\2", xml)


def kuvatav(el):
    s = el.findtext(NS + "kuvatavNr") or ""
    s = re.sub(r"<sup>(\d+)</sup>", lambda m: m.group(1).translate(SUP), s)
    return re.sub(r"<[^>]+>", "", s).strip()


def text_of(el):
    parts = []

    def rec(e):
        tag = e.tag.replace(NS, "")
        if tag in ("muutmismarge", "kuvatavNr", "loigeNr", "alampunktNr", "paragrahvNr", "viideURID", "viideURI"):
            return
        if tag == "sup":
            parts.append((e.text or "").translate(SUP))
        elif tag == "HTMLKonteiner":
            return
        else:
            parts.append(e.text or "")
        for c in e:
            rec(c)
            parts.append(c.tail or "")

    rec(el)
    # Riigi Teataja tekstis esineb vahel tühiku asemel märgikood „(160)“ (NBSP).
    return re.sub(r"\s+", " ", "".join(parts).replace("(160)", " ")).strip()


def parse_html_table(s):
    try:
        doc = lhtml.fromstring(s)
    except Exception:  # noqa: BLE001
        return []
    rows = []
    for tr in doc.iter("tr"):
        cells = []
        for td in tr:
            if td.tag not in ("td", "th"):
                continue
            for br in td.iter("br"):
                br.tail = " " + (br.tail or "")
            for sup in td.iter("sup"):
                sup.text = (sup.text or "").translate(SUP)
            cells.append(re.sub(r"\s+", " ", td.text_content()).strip())
        if any(cells):
            rows.append(cells)
    return rows


def block_list(container):
    """Lõike, alampunkti või paragrahvi sisu plokkideks: tekst ja tabelid."""
    blocks = []
    for st in container.findall(NS + "sisuTekst"):
        hk = st.find(NS + "HTMLKonteiner")
        if hk is not None:
            pre = text_of(st)
            if pre:
                blocks.append({"t": "p", "s": pre})
        if hk is not None and hk.text:
            rows = parse_html_table(hk.text)
            if rows:
                blocks.append({"t": "tbl", "rows": rows, "html": hk.text})
            else:
                txt = re.sub(r"\s+", " ", lhtml.fromstring(hk.text).text_content()).strip() if hk.text.strip() else ""
                if txt:
                    blocks.append({"t": "p", "s": txt})
        else:
            txt = text_of(st)
            if txt:
                blocks.append({"t": "p", "s": txt})
    return blocks


def walk_act(xml):
    """Tagastab paragrahvide loendi koos peatükkide ja lõigetega."""
    # Seaduste skeem (tyviseadus) kasutab samu elementide nimesid teises nimeruumis.
    xml = re.sub(r'xmlns="tyviseadus_1_10\.02\.2010"', 'xmlns="maarus_1_10.02.2010"', xml, count=1)
    root = ET.fromstring(strip_files(xml).encode("utf-8"))
    out = []

    def visit(el, ctx):
        tag = el.tag.replace(NS, "")
        if tag == "peatykk":
            ctx = dict(ctx, ptk=f'{el.findtext(NS + "peatykkNr")}. ptk {el.findtext(NS + "peatykkPealkiri") or ""}'.strip())
        if tag == "jagu":
            ctx = dict(ctx, jagu=f'{el.findtext(NS + "jaguNr")}. jagu {el.findtext(NS + "jaguPealkiri") or ""}'.strip())
        if tag == "paragrahv":
            par = {
                "id": el.get("id"),
                "nr": kuvatav(el).rstrip("."),
                "pealkiri": el.findtext(NS + "paragrahvPealkiri") or "",
                "ptk": ctx.get("ptk", ""),
                "loiked": [],
            }
            direct = block_list(el)
            if direct:
                par["loiked"].append({"id": el.get("id"), "nr": "", "blocks": direct, "punktid": []})
            for lg in el.findall(NS + "loige"):
                lo = {"id": lg.get("id") or el.get("id"), "nr": kuvatav(lg), "blocks": block_list(lg), "punktid": []}
                for ap in lg.findall(NS + "alampunkt"):
                    b = block_list(ap)
                    if b:
                        lo["punktid"].append({"nr": kuvatav(ap), "blocks": b})
                if lo["blocks"] or lo["punktid"]:
                    out_txt = " ".join(x.get("s", "") for x in lo["blocks"])
                    if re.fullmatch(r"\s*[Kk]ehtetu.*", out_txt or "") and not lo["punktid"]:
                        continue
                    par["loiked"].append(lo)
            if par["loiked"]:
                out.append(par)
            return
        for c in el:
            visit(c, ctx)

    visit(root, {})
    meta = {
        "valjaandja": root.findtext(f"{NS}metaandmed/{NS}valjaandja"),
        "aktikuupaev": root.findtext(f"{NS}metaandmed/{NS}vastuvoetud/{NS}aktikuupaev"),
        "aktiNr": root.findtext(f"{NS}metaandmed/{NS}vastuvoetud/{NS}aktiNr"),
    }
    return out, meta


def loige_text(lo):
    parts = []
    for b in lo["blocks"]:
        if b["t"] == "p":
            parts.append(b["s"])
    for p in lo["punktid"]:
        parts.append(p["nr"] + " " + " ".join(b.get("s", "") for b in p["blocks"]))
    return " ".join(parts)


# ----------------------------------------------------------------- tabelid

CODE_RE = re.compile(r"^(?=[0-9A-Z]*\d)[0-9A-Z]{3,8}$")


def parse_price(s):
    s = (s or "").replace(" ", " ").strip()
    m = re.fullmatch(r"(\d{1,3}(?: \d{3})*|\d+)(?:,(\d+))?", s)
    if not m:
        return None
    return float(m.group(1).replace(" ", "") + "." + (m.group(2) or "0"))


def split_codes(s):
    codes = [c.strip() for c in re.split(r"[,;]|\s+ja\s+|\s+või\s+|\s+", s or "") if c.strip()]
    return [c for c in codes if CODE_RE.match(c)]


def table_entries(rows):
    """Leiab tabelist (nimetus, koodid, hinnad, alapealkiri, tärn)."""
    hdr_i = None
    for i, r in enumerate(rows[:4]):
        if any(re.search(r"\bkood\b", c, re.I) for c in r):
            hdr_i = i
            break
    if hdr_i is None:
        return []
    hdr = rows[hdr_i]
    code_col = next(i for i, c in enumerate(hdr) if re.search(r"\bkood\b", c, re.I))
    price_cols = [i for i, c in enumerate(hdr) if i != code_col and re.search(r"piirhind|eurodes|hind", c, re.I)]
    name_col = next((i for i in range(len(hdr)) if i != code_col and i not in price_cols), 0)
    out, sub = [], ""
    for r in rows[hdr_i + 1:]:
        if len(r) != len(hdr):
            if len(r) == 1 or (r and not any(r[1:])):
                sub = r[0]
            continue
        codes = split_codes(r[code_col])
        if not codes:
            if r[name_col] and not any(r[i] for i in range(len(r)) if i != name_col):
                sub = r[name_col]
            continue
        name = r[name_col]
        star = name.endswith("*")
        prices = {}
        for pc in price_cols:
            pv = parse_price(r[pc])
            if pv is not None:
                prices[hdr[pc]] = pv
        out.append({"name": name.rstrip("*").strip(), "codes": codes, "prices": prices, "sub": sub, "star": star})
    return out


# ----------------------------------------------------------------- kvaliteedisüsteem

TK_KS_PAGE = "https://tervisekassa.ee/partnerile/raviasutusele/perearstile/perearsti-kvaliteedisusteem"
KS_KEYS = [
    (r"0.18|laste", "laste"), (r"diabeet", "diabeet"), (r"hüpertoon", "hypertoonia"), (r"infarkt", "infarkt"),
    (r"^indikaator", "jalgimine"), (r"erialane pädevus", "padevus"), (r"günekol", "gunekoloogia"),
    (r"kirurg", "kirurgia"), (r"e-konsult", "ekons"), (r"jämesoole", "jvs"),
]
KS_CAT = {"ennetus": "Ennetus", "krooniline": "Kroonilised haiged", "jalgimine": "Jälgimisindikaatorid",
          "lisapadevus": "Erialane lisapädevus", "soeluuring": "Sõeluuringud", "ylevaade": "Ülevaade"}


def html_grid(s):
    """HTML-tabel ruudustikuks; rowspan'i jätkulahtrid on None, colspan'i täited ''."""
    doc = lhtml.fromstring(s)
    rows, pending = [], {}
    for tr in doc.iter("tr"):
        cells = [td for td in tr if td.tag in ("td", "th")]
        row, col, ci = [], 0, 0
        while ci < len(cells) or col in pending:
            if col in pending:
                rem = pending[col]
                row.append(None)
                if rem <= 1:
                    del pending[col]
                else:
                    pending[col] = rem - 1
                col += 1
                continue
            td = cells[ci]
            ci += 1
            txt = re.sub(r"\s+", " ", td.text_content().replace("\u00a0", " ")).strip()
            rs, cs = int(td.get("rowspan", 1) or 1), int(td.get("colspan", 1) or 1)
            row.append(txt)
            for k in range(1, cs):
                row.append("")
            if rs > 1:
                for k in range(cs):
                    pending[col + k] = rs - 1
            col += cs
        rows.append(row)
    return rows


def is_code_cell(c):
    if not c:
        return False
    codes = split_codes(c)
    rest = re.sub(r"[0-9A-Z]{3,8}|ja/või|ja|või|,|\s", "", c)
    return bool(codes) and rest == ""


def parse_ks(met_pars, met, ks_notes):
    par = next((p for p in met_pars if p["pealkiri"].startswith("Lisatasu tasumine perearstile")), None)
    if not par:
        return [], None
    kinds = [("Haigusi ennetava", "ennetus"), ("Krooniliste haigete", "krooniline"), ("Jälgimise indikaatorid", "jalgimine"),
             ("Erialase lisapädevuse", "lisapadevus"), ("Sõeluuringutega", "soeluuring")]
    sections = []
    for lo in par["loiked"]:
        intro = next((b["s"] for b in lo["blocks"] if b["t"] == "p"), "")
        kind = next((k for t, k in kinds if intro.startswith(t)), None)
        tbls = [b for b in lo["blocks"] if b["t"] == "tbl"]
        if not kind or not tbls:
            continue
        cur, total = None, None
        for tb in tbls:
            for row in html_grid(tb["html"]):
                vals = [c for c in row if c]
                if not vals:
                    continue
                if any((c or "").strip().upper() == "KOOD" for c in row):
                    cur = {"title": vals[0], "vl": vals[-1].capitalize(), "kind": kind, "lg": lo["nr"], "a": lo["id"], "rows": [], "sub": "", "last": ""}
                    sections.append(cur)
                    continue
                if re.match(r"^kokku$", vals[0], re.I):
                    total = vals[-1]
                    continue
                if cur is None:
                    continue
                ci = next((i for i, c in enumerate(row) if is_code_cell(c)), None)
                v = row[-1] if row[-1] and re.fullmatch(r"\d+(,\d+)?", row[-1]) else ""
                end = ci if ci is not None else (len(row) - 1 if v else len(row))
                texts = [(i, c) for i, c in enumerate(row[:end]) if c]
                lead_cont = row[0] is None or row[0] == ""
                if len(texts) >= 2:
                    cur["sub"] = texts[0][1]
                    desc = " ".join(c for _, c in texts[1:])
                elif texts:
                    desc = texts[0][1]
                    if not lead_cont or texts[0][0] == 0:
                        cur["sub"] = ""
                else:
                    desc = cur["last"]
                codes = list(dict.fromkeys(split_codes(row[ci]))) if ci is not None else []
                cur["rows"].append({"s": cur["sub"] or None, "d": desc, "c": codes, "v": v or None})
                cur["last"] = desc
        if total:
            for sec in sections:
                if sec["kind"] == kind and sec["lg"] == lo["nr"]:
                    sec["kokku"] = total
    out = []
    for sec in sections:
        key = next((k for pat, k in KS_KEYS if re.search(pat, sec["title"], re.I)), None) or re.sub(r"[^a-z0-9]+", "-", norm_ascii(sec["title"])).strip("-")
        note = ks_notes.get(key, {})
        tot = next((r["v"] for r in sec["rows"] if r["v"] and r["v"] != "0"), None)
        out.append({
            "t": "q", "k": key, "cat": sec["kind"], "n": note.get("n", sec["title"]), "sn": note.get("sn", sec["title"]),
            "title": sec["title"], "vl": sec["vl"], "par": f'{par["nr"]} {sec["lg"]}', "url": met["url"] + "#" + sec["a"],
            "rows": sec["rows"], "kokku": sec.get("kokku"), "notes": note.get("notes"), "syn": list(note.get("syn", [])),
            "known": key in ks_notes,
        })
    ov = ks_notes.get("ylevaade", {})
    overview = {"t": "q", "k": "ylevaade", "cat": "ylevaade", "n": ov.get("n", "Perearsti kvaliteedisüsteem"), "sn": ov.get("sn", "Kvaliteedisüsteem"),
                "par": par["nr"], "url": met["url"] + "#" + par["id"], "notes": ov.get("notes"), "syn": list(ov.get("syn", [])), "rows": []}
    return out, overview


def norm_ascii(s):
    import unicodedata
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def tk_ks_docs(prev_meta):
    """Tervisekassa kvaliteedisüsteemi lehelt iga dokumendiliigi uusim aasta."""
    cats = [("ind", r"indikaatorite kirjeldused", "Indikaatorite kirjeldused"),
            ("juhis", r"rakendusjuhis|krooniliste haigete jälgimise tulemusliku töö ja erialase", "Lisatasude rakendusjuhis"),
            ("atc", r"atc koodide", "ATC koodide loendid"),
            ("audit", r"auditeerimise indikaatorid", "Auditeerimise indikaatorid (keskuse juhtimine)"),
            ("tulemused", r"kvaliteedisüsteemis saavutatud tulemused", "Saavutatud tulemused ja lisatasud"),
            ("kkk", r"^kkk$", "Kvaliteedisüsteemi KKK")]
    try:
        page = http_get(TK_KS_PAGE, timeout=60, tries=2).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"[hoiatus] Tervisekassa KS lehte ei saanud: {e}")
        return (prev_meta or {}).get("tk")
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", page, flags=re.S)
    best = {}
    for href, inner in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner)).strip()
        txt = lhtml.fromstring(f"<span>{txt}</span>").text_content() if txt else txt
        if not re.search(r"\.(pdf|xlsx|docx|xls)$", href, re.I):
            continue
        for k, pat, name in cats:
            if re.search(pat, txt, re.I):
                ym = re.search(r"(20\d\d)", txt) or re.search(r"(20\d\d)", href)
                year = int(ym.group(1)) if ym else 0
                url = href if href.startswith("http") else "https://tervisekassa.ee" + href
                if k not in best or year > best[k]["aasta"]:
                    best[k] = {"k": k, "n": name, "u": url, "aasta": year}
                break
    docs = [best[k] for k, _, _ in cats if k in best]
    return {"page": TK_KS_PAGE, "docs": docs}


# ----------------------------------------------------------------- SYNLAB

SYNLAB_URL = "https://synlab.ee/arstile/hinnakiri/?show=all"
SYNLAB_PAGE = "https://synlab.ee/arstile/hinnakiri/"


def synlab_labs(prev):
    """SYNLABi tervishoiuteenuse pakkuja hinnakiri: analüüs, lühend, TK kood, hind."""
    try:
        page = http_get(SYNLAB_URL, timeout=120, tries=2).decode("utf-8", "replace")
        doc = lhtml.fromstring(page)
        tbl = doc.xpath("//table")[0]
    except Exception as e:  # noqa: BLE001
        print(f"[hoiatus] SYNLABi hinnakirja ei saanud: {e}")
        if prev:
            return [x for x in prev["items"] if x["t"] == "b"], (prev["meta"].get("synlab") or {})
        return [], None
    title = (doc.findtext(".//title") or "").strip()
    m = re.search(r"\(al ([\d.]+)\)", title)
    cat, out = None, []
    for tr in tbl.iter("tr"):
        tds = [re.sub(r"\s+", " ", td.text_content().replace("\u00a0", " ")).strip().replace("ő", "õ").replace("Ő", "Õ") for td in tr if td.tag in ("td", "th")]
        if "table-heading" in (tr.get("class") or ""):
            cat = tds[0].strip(" *")
            continue
        if len(tds) < 6 or not tds[0] or (cat or "").upper().startswith("VETERINAARIA"):
            continue
        codes = [[c, int(x) if x else 1] for c, x in re.findall(r"\b(\d{4,5}[A-Z]?)\b(?:\s*x\s*(\d+))?", tds[4])]
        price = parse_price(tds[5].replace(".", ",")) if tds[5] else None
        out.append({"t": "b", "n": tds[0], "ab": tds[1] or None, "cat": cat, "mat": tds[3] or None, "tk": tds[4] or None,
                    "c": codes, "p": price, "aeg": (tds[6] if len(tds) > 6 else "") or None,
                    "vah": (tds[8] if len(tds) > 8 else "") or None})
    if len(out) < 200 and prev:
        print(f"[hoiatus] SYNLABi hinnakirjast leiti ainult {len(out)} rida; jätan eelmised andmed alles")
        return [x for x in prev["items"] if x["t"] == "b"], (prev["meta"].get("synlab") or {})
    return out, {"page": SYNLAB_PAGE, "seisuga": m.group(1) if m else None, "title": title, "count": len(out)}


# ----------------------------------------------------------------- sõeluuringud

SOEL_PAGE = "https://www.terviseportaal.ee/haiguste-ennetus/soeluuringud"
KVSU_PAGE = "https://tervisekassa.ee/kopsuvahi-soeluuring"
NUM_WORDS = {"ühe": 1, "kahe": 2, "kolme": 3, "nelja": 4, "viie": 5, "kuue": 6, "kümne": 10}
YEARS_RE = r"((?:(?:19|20)\d\d(?:\s*,\s*|\s+ja\s+)?)+)"


def page_text(url):
    raw = http_get(url, timeout=60, tries=2).decode("utf-8", "replace")
    doc = lhtml.fromstring(raw)
    for s in doc.xpath("//script|//style|//noscript"):
        s.drop_tree()
    return doc, re.sub(r"\s+", " ", doc.text_content().replace(" ", " "))


def years_of(s):
    return [int(y) for y in re.findall(r"(?:19|20)\d\d", s)]


def soeluuringud(prev, cfg):
    """Vähi sõeluuringute sihtrühmad terviseportaalist (vanus, intervall, kutsutavad sünniaastad)
    ja püsiv lisainfo failist soeluuringud.json. Kui lehte ei saa või see ei parsi, jääb eelmine seis."""
    prev_v = {x["k"]: x for x in (prev or {}).get("items", []) if x["t"] == "v"}
    warn, items = [], []
    try:
        _, txt = page_text(SOEL_PAGE)
    except Exception as e:  # noqa: BLE001
        txt = None
        warn.append(f"Terviseportaali sõeluuringute lehte ei saanud ({e}); kasutan eelmist seisu.")
    for p in cfg["programmid"]:
        it = {"t": "v", "k": p["k"], "n": p["n"], "sn": p["sn"], "codes": p["codes"], "notes": p.get("notes", []),
              "syn": ["sõeluuring", "vähi sõeluuring", "skriining"] + p.get("syn", [])}
        for key in ("dg", "dgAllikas", "ks"):
            if p.get(key):
                it[key] = p[key]
        if p.get("staatiline"):
            it.update({"kes": p["kes"], "vanus": p["vanus"], "int": p.get("intervall"), "lyh": p.get("luhike"), "url": p["leht"], "src": "tervisekassa"})
            try:
                doc, ktxt = page_text(p["leht"])
                pdf = next((h for h in doc.xpath("//a/@href") if re.search(r"kopsuvahi.*juhend.*\.pdf$", h, re.I)), None)
                if pdf:
                    it["juhend"] = pdf if pdf.startswith("http") else "https://tervisekassa.ee" + pdf
                mu = re.search(r"Viimati uuendatud:\s*(\d\d)\.(\d\d)\.(\d\d)", ktxt)
                if mu:
                    it["uuendatud"] = f"20{mu.group(3)}-{mu.group(2)}-{mu.group(1)}"
            except Exception as e:  # noqa: BLE001
                old = prev_v.get(p["k"], {})
                for key in ("juhend", "uuendatud"):
                    if old.get(key):
                        it[key] = old[key]
                warn.append(f"Tervisekassa kopsuvähi sõeluuringu lehte ei saanud ({e}).")
            items.append(it)
            continue
        it.update({"url": p["alamleht"], "src": "terviseportaal"})
        stem = p["tyvi"]
        m_age = re.search(stem + r" sõeluuringule oodatakse kõiki (\d+)\s*[-–]\s*(\d+)[\s-]*aastaseid (.+?) iga (\S+) aasta järel", txt or "", re.I)
        m_yrs = re.search(r"(20\d\d)\. aastal on " + stem + r" sõeluuringule kutsutud (.+?) sünniaastatega\s*" + YEARS_RE, txt or "", re.I)
        if not (m_age and m_yrs):
            old = prev_v.get(p["k"])
            if txt is not None:
                warn.append(f"{p['n']}: terviseportaali tekst ei vastanud oodatud mustrile; kasutan eelmist seisu.")
            if old:
                for key in ("kes", "vanus", "int", "aasta", "sy", "osale", "kontroll"):
                    if key in old:
                        it[key] = old[key]
            items.append(it)
            continue
        lo, hi = int(m_age.group(1)), int(m_age.group(2))
        iw = m_age.group(4).lower()
        interval = NUM_WORDS.get(iw) or (int(iw) if iw.isdigit() else None)
        year = int(m_yrs.group(1))
        sy = sorted(set(years_of(m_yrs.group(3))))
        rest = (txt or "")[m_yrs.end():m_yrs.end() + 400]
        m_os = re.match(r"\s*\.?\s*([A-ZÕÄÖÜ][^.!?]*[.!?])", rest)
        it.update({"kes": m_yrs.group(2).strip(), "vanus": [lo, hi], "int": interval, "aasta": year, "sy": sy,
                   "osale": m_os.group(1).strip() if m_os else None, "kontroll": TODAY.isoformat()})
        ages = [year - y for y in sy]
        if ages and (min(ages) != lo or max(ages) != hi):
            warn.append(f"{p['n']}: {year}. aasta sünniaastate vanused ({min(ages)}–{max(ages)}) ei klapi lehel nimetatud vanusega {lo}–{hi}.")
        steps = {b - a for a, b in zip(sy, sy[1:])}
        if interval and steps and steps != {interval}:
            warn.append(f"{p['n']}: sünniaastate vahe {sorted(steps)} ei vasta intervallile {interval} a.")
        try:
            _, st = page_text(p["alamleht"])
            ms = re.search(r"(20\d\d)\. aastal [^.]*?sõeluuringule [^.]*?sünniaasta\w*\s*" + YEARS_RE, st)
            if ms and (int(ms.group(1)) != year or sorted(set(years_of(ms.group(2)))) != sy):
                warn.append(f"{p['n']}: alamlehe sünniaastad ({ms.group(1)}: {ms.group(2).strip()}) erinevad koondlehest.")
        except Exception:  # noqa: BLE001
            pass
        er = p.get("erinevus")
        if er and er.get("aasta") == year:
            it["erinevus"] = er["s"]
        items.append(it)
    meta = {"page": SOEL_PAGE, "yld": cfg["_meta"].get("yld", []), "warn": warn}
    return items, meta


# ----------------------------------------------------------------- teemakaardid

BASE_SOURCES = {"ttl", "metoodika", "abivahendid", "mootorsoidukijuht", "meditsiiniseadmed"}
TK_HUVITIS = "https://tervisekassa.ee/inimesele/huvitised/haigushuvitis"


def norm_ws(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip().lower()


def act_lisad(xml, akt_id):
    """Akti XML-is olevad lisad (PDF jm) koos Riigi Teataja aadressiga."""
    out = []
    for name in dict.fromkeys(re.findall(r'<fail[^>]*failNimi="([^"]+)"', xml)):
        out.append({"n": name, "u": aktilisa_url(akt_id, name)})
    return out


def tk_huvitised(prev):
    """Tervisekassa hüvitiste võrdlustabel (põhjus, lehe liik, kes ja kui palju maksab, kestus) ja päevane ülempiir."""
    old = ((prev or {}).get("meta") or {}).get("huvitised")
    try:
        raw = http_get(TK_HUVITIS, timeout=60, tries=2).decode("utf-8", "replace")
        doc = lhtml.fromstring(raw)
    except Exception as e:  # noqa: BLE001
        print(f"[hoiatus] Tervisekassa hüvitiste lehte ei saanud: {e}")
        return old, [f"Tervisekassa hüvitiste lehte ei saanud ({e}); kasutan eelmist seisu."] if old else []

    def cell(td):
        ps = [norm_space(p.text_content()) for p in td.xpath(".//p")]
        ps = [p for p in ps if p]
        return ps or [norm_space(td.text_content())]

    rows = []
    for tr in doc.xpath("//table//tbody/tr"):
        tds = tr.xpath("./td")
        if len(tds) < 5:
            continue
        c = [cell(td) for td in tds[:5]]
        rows.append({"pohjus": c[0], "nr": [x for x in c[1] if x], "liik": " ".join(c[2]), "kord": c[3], "kestus": " ".join(c[4])})
    text = norm_space(doc.text_content())
    m = re.search(r"ülempiir ühes kalendripäevas (\d{4})\. aastal on ([\d\s]+,\d\d) eurot", text)
    upd = re.findall(r"Viimati uuendatud:\s*(\d\d)\.(\d\d)\.(\d\d)", text)
    if len(rows) < 8:
        return old, ["Tervisekassa hüvitiste võrdlustabelist leiti liiga vähe ridu; kasutan eelmist seisu."] if old else []
    return {"page": TK_HUVITIS, "rows": rows,
            "ylempiir": {"aasta": int(m.group(1)), "eur": m.group(2).replace(" ", "")} if m else (old or {}).get("ylempiir"),
            "uuendatud": [f"20{y}-{mo}-{d}" for d, mo, y in upd]}, []


def norm_space(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()


def tvl_pohjused(par_text):
    """Tööst vabastamise põhjuste koodid töövõimetuslehe määruse § 2 tekstist."""
    m = re.search(r"tööst vabastamise põhjus numbri ja sõnadega \((.*?)\);", par_text)
    if not m:
        return []
    out = []
    for part in m.group(1).split("; "):
        mm = re.match(r"(\d+)\.\s*(.+)", part.strip())
        if mm:
            out.append([mm.group(1), mm.group(2).strip()])
    return out


def imm_lisad(xml):
    """Immuniseerimiskava lisa 1 (laste ajakava) ja lisa 2 (gripi ja COVID-19 riskiseisundid) PDF-ist."""
    res, warn = {}, []
    name1, pdf1 = lisa_pdf(xml, "lisa1")
    if pdf1:
        txt = "\n".join((p.extract_text() or "") for p in pdf1.pages)
        body = txt.split("Vaktsiini tähis", 1)[-1].split("Tähiste seletused", 1)
        rows = []
        for line in body[0].split("\n"):
            line = line.strip()
            mm = re.match(r"^(.*(?:tundi|päeva|kuud|aasta|aastat|\(k\.a\)))\s+(\S.*)$", line)
            if mm:
                rows.append([mm.group(1), mm.group(2)])
        legend, notes = [], []
        if len(body) > 1:
            for line in body[1].split("\n"):
                line = line.strip()
                if not line:
                    continue
                if re.match(r"^[¹²³⁴⁵]", line):
                    notes.append(line)
                elif notes:
                    notes[-1] += " " + line
                elif " – " in line:
                    legend.append(line)
                elif legend:
                    legend[-1] += " " + line
        if len(rows) < 8:
            warn.append(f"Immuniseerimiskava lisa 1 ({name1}) ajakavast leiti ainult {len(rows)} rida.")
        res["imm1"] = {"lisa": name1, "rows": rows, "legend": legend, "notes": notes, "text": txt}
    name2, pdf2 = lisa_pdf(xml, "lisa2")
    if pdf2:
        txt = "\n".join((p.extract_text() or "") for p in pdf2.pages)
        parts = re.split(r"\n(?=Tabel \d+\.)", txt)
        tabs = []
        for p in parts[1:]:
            head, _, rest = p.partition("\n")
            # pealkiri võib jätkuda järgmisel real
            while rest and not re.match(r"Terviseseisund", rest) and len(head) < 400:
                nxt, _, rest = rest.partition("\n")
                head += " " + nxt
            tabs.append({"n": head.strip(), "s": rest.strip()})
        if len(tabs) < 3:
            warn.append(f"Immuniseerimiskava lisa 2 ({name2}) tabeleid leiti {len(tabs)}.")
        res["imm2"] = {"lisa": name2, "tabelid": tabs, "text": txt}
    return res, warn


def watch_sources(allikad, prev):
    """Jälgib teemakaartide allikaid: veebilehe „Viimati uuendatud“ kuupäev, PDF-i räsi ja kättesaadavus."""
    pw = ((prev or {}).get("meta") or {}).get("jalgimine") or {}
    out = {}
    for key, a in allikad.items():
        url = a["u"]
        old = pw.get(key) or {}
        try:
            raw = http_get(url, timeout=45, tries=2)
            if url.lower().endswith(".pdf") or raw[:4] == b"%PDF":
                out[key] = {"ok": True, "sha": hashlib.sha256(raw).hexdigest()[:16]}
            else:
                t = raw.decode("utf-8", "replace")
                d = re.findall(r"(?:Viimati uuendatud|Uuendatud)[^0-9]{0,40}(\d\d)\.(\d\d)\.(\d{2,4})", re.sub(r"<[^>]+>", " ", t))
                dates = sorted({(y if len(y) == 4 else "20" + y) + f"-{mo}-{dd}" for dd, mo, y in d})
                out[key] = {"ok": True, "uuendatud": dates[-1] if dates else None}
        except Exception as e:  # noqa: BLE001
            out[key] = dict(old, ok=False, viga=str(e)[:120], vigu=(old.get("vigu") or 0) + 1)
    return out


def build_teemad(cfg, sources, par_text, dyn, lisad):
    """Teemakaardid: read koos viidetega, tekstikontroll ja dünaamilised tabelid."""
    items, warn = [], []
    allikad = cfg.get("allikad", {})

    def ref(a):
        if isinstance(a, str):
            x = allikad.get(a)
            if not x:
                warn.append(f"Tundmatu allikas „{a}“")
                return None
            return {"n": x["n"], "u": x["u"], "k": a}
        src, par = a
        s = sources.get(src)
        if not s:
            warn.append(f"Tundmatu akt „{src}“")
            return None
        if par.startswith("lisa"):
            li = next((x for x in lisad.get(src, []) if par.replace(" ", "") in x["n"].lower()), None)
            return {"src": src, "par": par, "n": f'{s.get("lyh") or s["nimi"]} {par}', "u": li["u"] if li else s["url"]}
        pid = (par_text.get(src) or {}).get(par, {}).get("id")
        if not pid:
            warn.append(f"Viidatud säte puudub: {s.get('lyh')} {par}")
        return {"src": src, "par": par, "n": f'{s.get("lyh") or s["nimi"]} {par}', "u": s["url"] + ("#" + pid if pid else "")}

    def check(row, where):
        bad = []
        for src, par, needle in row.get("kontroll", []):
            if par.startswith("lisa"):
                hay = (dyn.get("imm1" if "1" in par else "imm2") or {}).get("text", "") if src == "immkava" else ""
            else:
                hay = (par_text.get(src) or {}).get(par, {}).get("t", "")
            if norm_ws(needle) not in norm_ws(hay):
                bad.append(f'{(sources.get(src) or {}).get("lyh", src)} {par}: „{needle}“')
        if bad:
            warn.append(f"{where}: allika tekst on muutunud, vaata üle → " + "; ".join(bad))
        return bad

    hu = dyn.get("huvitised") or {}
    yl = hu.get("ylempiir")
    for t in cfg["teemad"]:
        it = {"t": "j", "k": t["k"], "n": t["n"], "sn": t.get("sn") or t["n"], "g": t["grupp"], "syn": t.get("syn", [])}
        if t.get("boost"):
            it["boost"] = t["boost"]
        # Ülevaatuse meeldetuletus (nt tähtajaline kollektiivleping): alates kuupäevast läheb hoiatus aruandesse.
        if t.get("ule") and TODAY.isoformat() >= t["ule"]["alates"]:
            warn.append(f'{t.get("sn") or t["n"]}: {t["ule"]["s"]}')
        for key in ("read", "erinevused"):
            out = []
            for r in t.get(key, []):
                s = r["s"]
                if "{ylempiir}" in s:
                    s = s.replace("{ylempiir}", f'{yl["aasta"]}. aastal on {yl["eur"]} eurot' if yl else "(vt Tervisekassa lehte)")
                row = {"s": s, "a": [x for x in (ref(a) for a in r.get("allikas", [])) if x]}
                if r.get("p"):
                    row["p"] = r["p"]
                if check(r, f'{t["sn"]} ({s[:50]}…)'):
                    row["muutus"] = True
                out.append(row)
            if out:
                it["r" if key == "read" else "e"] = out
        fut = [dict(f, a=[x for x in (ref(a) for a in f.get("allikas", [])) if x]) for f in t.get("tulevik", []) if f["alates"] > TODAY.isoformat()]
        if fut:
            it["tul"] = [{"alates": f["alates"], "s": f["s"], "a": f["a"]} for f in fut]
        tabs = [dict(tb, a=[x for x in (ref(a) for a in tb.get("allikas", [])) if x]) for tb in t.get("tabelid", [])]
        for d in t.get("dyn", []):
            if d == "huvitised" and hu.get("rows"):
                tabs.insert(0, {"n": "Tervisekassa hüvitiste võrdlustabel: kõik põhjuse koodid, kes maksab ja kui kaua", "dyn": "huvitised", "rows": hu["rows"],
                                "a": [{"n": "Tervisekassa: haigushüvitis", "u": hu["page"]}], "uuendatud": hu.get("uuendatud"),
                                "kinni": d in (t.get("dyn_kinni") or [])})
            elif d == "pohjused":
                pr = tvl_pohjused((par_text.get("tvl") or {}).get("§ 2", {}).get("t", ""))
                if pr:
                    tabs.append({"n": "Tööst vabastamise põhjuse koodid", "pais": ["Kood", "Põhjus"], "read": pr, "a": [ref(["tvl", "§ 2"])]})
                else:
                    warn.append("Töövõimetuslehe põhjuse koode ei õnnestunud § 2-st lugeda.")
            elif d == "imm1" and dyn.get("imm1"):
                x = dyn["imm1"]
                tabs.insert(0, {"n": "Laste immuniseerimiskava (määruse lisa 1)", "pais": ["Vanus", "Vaktsiin"], "read": x["rows"],
                                "markus": "\n".join(x["notes"]), "legend": x["legend"], "a": [ref(["immkava", "lisa 1"])]})
            elif d == "imm2" and dyn.get("imm2"):
                for tb in dyn["imm2"]["tabelid"]:
                    tabs.append({"n": tb["n"], "tekst": tb["s"], "a": [ref(["immkava", "lisa 2"])]})
            elif d == "ekons":
                ek = dyn.get("ekons") or []
                if ek:
                    tabs.append({"n": "Saatekirja ja vastuse nõuded erialade kaupa (metoodika lisad)",
                                 "pais": ["E-konsultatsioon", "Saatja", "Nõuded"],
                                 "read": [[n + (f", {note}" if note else ""), saatja, [f"Lisa {nr}", u]] for n, saatja, note, nr, u in ek],
                                 "markus": "Saatja on lisa pealkirjas nimetatud suunaja. Lisad loetakse kehtivast metoodikast igal andmekontrollil.",
                                 "a": [ref(["metoodika", "§ 6"])]})
                else:
                    warn.append("E-konsultatsiooni lisasid metoodikast ei leitud.")
        if tabs:
            it["tab"] = tabs
        if t.get("lisad"):
            it["lisad"] = lisad.get(t["lisad"], [])
        if t.get("lingid"):
            it["l"] = [x for x in (ref(a) for a in t["lingid"]) if x]
        if t.get("tabelid_lopus"):
            it["tl"] = True
        if t.get("seotud"):
            known = {x["k"] for x in cfg["teemad"]}
            bad = [k for k in t["seotud"] if k not in known]
            if bad:
                warn.append(f'{t["sn"]}: tundmatu seotud kaart {", ".join(bad)}')
            it["seotud"] = [k for k in t["seotud"] if k in known]
        items.append(it)
    return items, warn


# ----------------------------------------------------------------- meditsiiniseadmed

def lisa_pdf(xml, pattern=r"lisa"):
    m = re.search(r'<fail[^>]*failNimi="([^"]*' + pattern + r'[^"]*\.pdf)"[^>]*>([A-Za-z0-9+/=\s]+)</fail>', xml, re.I)
    if not m:
        return None, None
    return m.group(1), pdfplumber.open(io.BytesIO(base64.b64decode(re.sub(r"\s", "", m.group(2)))))


def parse_meditsiiniseadmed(xml, src, codes_map):
    pars, _ = walk_act(xml)
    lisa_name, pdf = lisa_pdf(xml)
    products = []
    if pdf:
        for page in pdf.pages:
            for tb in page.extract_tables():
                for r in tb:
                    r = [re.sub(r"\s+", " ", (c or "")).strip() for c in r]
                    if len(r) >= 7 and re.fullmatch(r"\d{7}", r[2]):
                        products.append(r[:7])
    nmap = {norm_ascii(k): v for k, v in codes_map.items() if not k.startswith("_")}
    groups = {}
    for r in products:
        groups.setdefault(r[0], []).append(r)
    items, unmapped = [], []
    group_pars = [p for p in pars if p["pealkiri"].strip() and not re.match(r"(Üldsätted|Tervisekassa poolt tasu|Kindlustatud isiku omaosaluse|Tasu maksmise kohustuse ülevõtmise kord|Määruse)", p["pealkiri"])]
    for gname, rows in groups.items():
        gn = norm_ascii(gname)
        par = next((p for p in group_pars if norm_ascii(p["pealkiri"].strip()) == gn), None) or \
            next((p for p in group_pars if gn.startswith(norm_ascii(p["pealkiri"].strip()))), None)
        code = nmap.get(gn)
        if not code:
            unmapped.append(gname)
        subs, pr = [], []
        for r in rows:
            if r[1] not in subs:
                subs.append(r[1])
            pr.append([r[2], r[3], subs.index(r[1]), parse_price(r[4]), parse_price(r[5]), int(r[6]) if r[6].isdigit() else None])
        sub_info = []
        for i, sname in enumerate(subs):
            sp = [x for x in pr if x[2] == i]
            tkp = [x[4] for x in sp if x[4] is not None]
            sub_info.append([sname, len(sp), min(tkp) if tkp else None, max(tkp) if tkp else None, sorted({x[5] for x in sp if x[5] is not None})])
        pcts = sorted({x[5] for x in pr if x[5] is not None})
        item = {"t": "m", "n": gname, "c": code, "subs": sub_info, "pr": pr, "pct": pcts}
        if par:
            sate = make_sate("meditsiiniseadmed", src, par)
            item.update({"par": par["nr"], "url": sate["url"], "b": sate["b"]})
        items.append(item)
    general = [make_sate("meditsiiniseadmed", src, p) for p in pars if p not in group_pars]
    return items, general, lisa_name, unmapped


# ----------------------------------------------------------------- ehitus

def make_sate(src_key, src, par, kind="säte"):
    blocks = []
    for lo in par["loiked"]:
        first = True
        for b in lo["blocks"]:
            if b["t"] == "p":
                blocks.append({"t": "p", "s": (lo["nr"] + " " if first and lo["nr"] else "") + b["s"]})
                first = False
            else:
                blocks.append({"t": "tbl", "rows": b["rows"]})
        for p in lo["punktid"]:
            txt = " ".join(b.get("s", "") for b in p["blocks"] if b["t"] == "p")
            blocks.append({"t": "li", "s": f'{p["nr"]} {txt}'.strip()})
            for b in p["blocks"]:
                if b["t"] == "tbl":
                    blocks.append({"t": "tbl", "rows": b["rows"]})
    return {
        "t": "l",
        "src": src_key,
        "par": par["nr"],
        "n": par["pealkiri"],
        "ptk": par["ptk"],
        "a": par["id"],
        "url": src["url"] + "#" + par["id"],
        "b": blocks,
    }


def build(args):
    cache = os.path.join(HERE, "cache")
    with open(os.path.join(HERE, "sources.json"), encoding="utf-8") as f:
        sources_cfg = json.load(f)

    # 1. kehtivad redaktsioonid
    sources, xmls, chains = {}, {}, {}
    for key, cfg in sources_cfg.items():
        print(f"[RT] {key}", flush=True)
        old_gid = cfg["grupiId"]
        info, xml = resolve_current(cfg["grupiId"], cache)
        chain = info.pop("_chain")
        info["nimi"] = cfg["nimi"]
        if cfg.get("lyh"):
            info["lyh"] = cfg["lyh"]
        sources[key] = info
        xmls[key] = xml
        if str(info["grupiId"]) != str(old_gid):
            cfg["grupiId"] = info["grupiId"]
            # asendatud akti grupp jääb muudatuste vaate jaoks meelde
            cfg["eelmised"] = list(dict.fromkeys((cfg.get("eelmised") or []) + [old_gid]))
            print(f"[info] {key}: akt asendati, uus grupi ID {info['grupiId']}")
        else:
            # varem asendatud aktide redaktsioonid ahela algusesse
            pre = []
            for g in cfg.get("eelmised") or []:
                try:
                    pre += content_chain(api_json(f"/akt/{g}/redaktsioonid"))
                except Exception as e:  # noqa: BLE001
                    print(f"[hoiatus] {key}: eelmise grupi {g} redaktsioone ei saanud: {e}")
            known = {x["id"] for x in chain}
            chain = sorted([x for x in pre if x["id"] not in known], key=lambda x: x["alates"] or "") + chain
        chains[key] = chain

    toru_dir = os.path.join(HERE, "toru")
    aux_hash = hashlib.sha256()
    for fn in ["synonyms.json", "links.json", "build.py", "muutused.py", "met_lisad.py", "ks_notes.json", "ms_ryhmakoodid.json", "soeluuringud.json", "teemad.json"]:
        with open(os.path.join(HERE, fn), "rb") as f:
            aux_hash.update(f.read())
    toru_loaded = load_toru_rows(toru_dir)  # xlsx olemasolul uuendab väljavõtet
    ex_path = os.path.join(toru_dir, "toru_valjavote.json")
    if os.path.exists(ex_path):
        with open(ex_path, "rb") as f:
            aux_hash.update(f.read())

    out_path = os.path.join(ROOT, "data", "data.json")
    prev = None
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            prev = json.load(f)
    tk = tk_ks_docs(prev["meta"] if prev else None)
    if tk:
        aux_hash.update(json.dumps(tk["docs"], sort_keys=True).encode())
    labs, synlab_meta = synlab_labs(prev)
    aux_hash.update(json.dumps([[x["n"], x["ab"], x["tk"], x["p"]] for x in labs], ensure_ascii=False).encode())
    with open(os.path.join(HERE, "soeluuringud.json"), encoding="utf-8") as f:
        soel_cfg = json.load(f)
    soel_items, soel_meta = soeluuringud(prev, soel_cfg)
    aux_hash.update(json.dumps([[x["k"], x.get("aasta"), x.get("sy"), x.get("vanus"), x.get("int"), x.get("kes"), x.get("osale"), x.get("juhend")]
                                for x in soel_items] + [soel_meta["warn"]], ensure_ascii=False).encode())
    with open(os.path.join(HERE, "teemad.json"), encoding="utf-8") as f:
        teemad_cfg = json.load(f)
    huvitised, hu_warn = tk_huvitised(prev)
    if huvitised:
        aux_hash.update(json.dumps([huvitised["rows"], huvitised.get("ylempiir")], ensure_ascii=False, sort_keys=True).encode())
    jalgimine = watch_sources(teemad_cfg.get("allikad", {}), prev)
    # Ülevaatuse kuupäeva saabumine (teemakaardi väli „ule“) käivitab ehituse, et hoiatus jõuaks aruandesse.
    aux_hash.update(json.dumps(sorted(t["k"] for t in teemad_cfg["teemad"] if t.get("ule") and TODAY.isoformat() >= t["ule"]["alates"])).encode())
    # Sõrmejälge mõjutab sisu muutus ja püsiv (vähemalt kaks järjestikust) kättesaamatus, mitte ühekordne võrgutõrge.
    aux_hash.update(json.dumps({k: [v.get("uuendatud"), v.get("sha"), (v.get("vigu") or 0) >= 2] for k, v in sorted(jalgimine.items())},
                               ensure_ascii=False).encode())
    fingerprint = "|".join([BUILD_VERSION] + [f"{k}:{v['id']}:{','.join(x['id'] for x in v['tulevased'])}" for k, v in sorted(sources.items())] + [aux_hash.hexdigest()[:16]])
    if prev and prev["meta"].get("fingerprint") == fingerprint and not args.force:
        print("Muudatusi ei ole.")
        write_output(args, changed=False)
        return

    with open(os.path.join(HERE, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sources_cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")

    items, rules = [], []
    by_code = {}

    # 2. tervishoiuteenuste loetelu
    ttl = sources["ttl"]
    ttl_pars, _ = walk_act(xmls["ttl"])
    text_rules = []  # (src, par, lõige, tekst)
    for par in ttl_pars:
        for lo in par["loiked"]:
            has_tbl = False
            for b in lo["blocks"]:
                if b["t"] != "tbl":
                    continue
                for e in table_entries(b["rows"]):
                    has_tbl = True
                    for code in e["codes"]:
                        if code in by_code:
                            by_code[code].setdefault("muud", []).append({"par": par["nr"], "a": lo["id"]})
                            continue
                        price_items = list(e["prices"].items())
                        it = {
                            "t": "s",
                            "c": code,
                            "n": e["name"],
                            "p": price_items[0][1] if price_items else None,
                            "pl": [[k, v] for k, v in price_items[1:]] or None,
                            "par": par["nr"],
                            "pt": par["pealkiri"],
                            "ptk": par["ptk"],
                            "sub": e["sub"] or None,
                            "url": ttl["url"] + "#" + lo["id"],
                            "src": "ttl",
                        }
                        by_code[code] = it
                        items.append(it)
            txt = loige_text(lo)
            if txt and not has_tbl:
                text_rules.append(("ttl", par, lo, txt))
            elif txt and has_tbl:
                # tabeliga lõike tekst on tavaliselt sissejuhatus; reeglid tulevad eraldi lõigetes
                pass
    # perearstiabi peatükk ja üldsätted ka sätetena
    for par in ttl_pars:
        if par["ptk"].startswith(("1.", "2.")):
            items.append(make_sate("ttl", ttl, par))

    # 3. metoodika (perearstiabi peatükk) + fondid
    met = sources["metoodika"]
    met_pars, _ = walk_act(xmls["metoodika"])
    funds = []
    for par in met_pars:
        if not par["ptk"].startswith("2."):
            continue
        items.append(make_sate("metoodika", met, par))
        for lo in par["loiked"]:
            txt = loige_text(lo)
            tbls = [b for b in lo["blocks"] if b["t"] == "tbl"]
            fund_key = None
            mp = re.search(r"kuni (\d+)\s*% perearsti nimistule pearahadeks arvestatud summast", txt)
            if mp and tbls:
                fund_key = f"f{mp.group(1)}"
                label = f"Kuni {mp.group(1)}% pearahast"
                if fund_key in FUND_NAMES:
                    label = f"{FUND_NAMES[fund_key]} · {FUND_SUB.get(fund_key) or f'kuni {mp.group(1)}% pearahast'}"
            elif tbls and "raviarve" in txt and "täiendavalt" in txt:
                fund_key = "lisaks"
                label = f"{FUND_NAMES['lisaks']} · raviarvega lisaks pearahale"
            # Pearaha arvel tasutavad laboriuuringud (metoodika § 5 lg 3, nt glükoos 66101): mitte fond, vaid pearaha sees.
            if not fund_key and tbls and re.search(r"\bpearaha arvel\b", txt):
                ph = {"par": f'{par["nr"]} {lo["nr"]}'.strip(), "url": met["url"] + "#" + lo["id"]}
                for b in tbls:
                    for e in table_entries(b["rows"]):
                        for c in e["codes"]:
                            if c in by_code:
                                by_code[c]["ph"] = ph
            if fund_key:
                codes = []
                for b in tbls:
                    for e in table_entries(b["rows"]):
                        for c in e["codes"]:
                            codes.append(c)
                            it = by_code.get(c)
                            if it is None:
                                it = {"t": "s", "c": c, "n": e["name"], "p": None, "src": "metoodika", "url": met["url"] + "#" + lo["id"]}
                                by_code[c] = it
                                items.append(it)
                            fl = it.setdefault("f", [])
                            if fund_key not in fl:
                                fl.append(fund_key)
                            if e["star"]:
                                it["fn"] = "tärn"
                funds.append({
                    "t": "f",
                    "k": fund_key,
                    "n": label,
                    "par": f'{par["nr"]} {lo["nr"]}'.strip(),
                    "s": re.sub(r"\s*RT I \d{4}-\d\d-\d\d.*$", "", lo["blocks"][0]["s"]) if lo["blocks"] and lo["blocks"][0]["t"] == "p" else txt[:400],
                    "url": met["url"] + "#" + lo["id"],
                    "cnt": len(codes),
                    "pct": int(mp.group(1)) if fund_key != "lisaks" else None,
                })
            elif txt:
                text_rules.append(("metoodika", par, lo, txt))
    # tärni tingimus
    star_rule = next((t for (s, p, l, t) in text_rules if s == "metoodika" and "tärniga" in t), None)
    # Fondi tasumise tingimus (praegu § 6 lg 9): teenust peab osutama perearstiabi osutaja ise, mille kaudu perearst tegutseb.
    fund_warn = []
    for (s, p, lo, t) in text_rules:
        mc = re.search(r"lõike(?:s|tes) (\S+?) nimetatud", t) if s == "metoodika" and "mille kaudu perearst tegutseb" in t else None
        if mc:
            for fd in funds:
                if fd["par"] == f'{p["nr"]} ({mc.group(1)})':
                    fd["cond"] = {"par": f'{p["nr"]} {lo["nr"]}'.strip(), "url": met["url"] + "#" + lo["id"]}
    for fd in funds:
        if fd["k"] in FUND_SUB and not fd.get("cond"):
            fund_warn.append(f'{fd["n"]}: metoodikast ei leitud enam tingimust, et teenust osutab perearstiabi osutaja ise (oli § 6 lg 9). Vaata fondi pealkiri ja selgitus üle.')

    # 4. reeglid koodide juurde
    for (src_key, par, lo, txt) in text_rules:
        if not re.search(r"kood", txt, re.I):
            continue
        cand = re.findall(r"\b[0-9A-Z]{3,8}\b", txt)
        for a, b in re.findall(r"\b(\d{4,5})\s*[–-]\s*(\d{4,5})\b", txt):
            if 0 < int(b) - int(a) <= 60 and len(a) == len(b):
                cand += [str(n) for n in range(int(a), int(b) + 1)]
        found = [c for c in dict.fromkeys(cand) if c in by_code and CODE_RE.match(c)]
        if not found or len(found) > 15:
            continue
        ri = len(rules)
        rules.append({
            "src": src_key,
            "par": f'{par["nr"]} {lo["nr"]}'.strip(),
            "s": txt,
            "url": sources[src_key]["url"] + "#" + lo["id"],
        })
        for c in found:
            by_code[c].setdefault("r", []).append(ri)

    # 5. Toru
    toru_meta = merge_toru(toru_loaded, by_code, items)

    # 5b. kvaliteedisüsteem (metoodika § 8) ja lisapädevused
    with open(os.path.join(HERE, "ks_notes.json"), encoding="utf-8") as f:
        ks_notes = json.load(f)
    ks_items, ks_overview = parse_ks(met_pars, met, ks_notes)
    for q in ks_items:
        for r in q["rows"]:
            for c in r["c"] + [c + suf for c in r["c"] for suf in ("K", "V") if c + suf in by_code]:
                it = by_code.get(c)
                if it is None:
                    it = {"t": "s", "c": c, "n": r["d"], "p": None, "src": "metoodika", "url": q["url"]}
                    by_code[c] = it
                    items.append(it)
                kl = it.setdefault("ks", [])
                if q["k"] not in kl:
                    kl.append(q["k"])
    if ks_overview:
        ks_overview["lisatasud"] = [[c, by_code[c]["n"], by_code[c].get("p")] for c in ["3061", "3069", "3062", "3083"] if c in by_code]
        ks_overview["docs"] = (tk or {}).get("docs", [])
        ks_overview["tkPage"] = TK_KS_PAGE
        items.append(ks_overview)
    items.extend(ks_items)

    # 5c. perearstiabi tunnus ja SYNLABi analüüsid
    for it in items:
        if it["t"] == "s" and (it.get("f") or it.get("ph") or it.get("ks") or (it.get("ptk") or "").startswith("2.")
                               or (it.get("tp") or {}).get("hk") == "PEREARSTIABI" or it.get("src") == "metoodika"):
            it["pa"] = True
    for lb in labs:
        for k in ("f", "ks", "miss", "ph"):
            lb.pop(k, None)
        fl, kl, miss = [], [], []
        for c, _x in lb["c"]:
            it = by_code.get(c)
            if it is None:
                miss.append(c)
                continue
            for f in it.get("f") or []:
                if f not in fl:
                    fl.append(f)
            for k in it.get("ks") or []:
                if k not in kl:
                    kl.append(k)
            if it.get("ph"):
                lb["ph"] = it["ph"]
        if fl:
            lb["f"] = fl
        if kl:
            lb["ks"] = kl
        if miss:
            lb["miss"] = miss
        items.append(lb)

    # 6. abivahendid
    abiv = sources["abivahendid"]
    ab_pars, _ = walk_act(xmls["abivahendid"])
    for par in ab_pars:
        items.append(make_sate("abivahendid", abiv, par))
    ab_items, ab_cols, lisa_name = parse_abivahendid(xmls["abivahendid"])
    abiv["lisa"] = lisa_name
    abiv["lisaUrl"] = aktilisa_url(abiv["id"], lisa_name) if lisa_name else None
    items.extend(ab_items)

    # 6b. meditsiiniseadmed
    ms_unmapped = []
    if "meditsiiniseadmed" in sources:
        msrc = sources["meditsiiniseadmed"]
        with open(os.path.join(HERE, "ms_ryhmakoodid.json"), encoding="utf-8") as f:
            ms_codes = json.load(f)
        ms_items, ms_general, ms_lisa, ms_unmapped = parse_meditsiiniseadmed(xmls["meditsiiniseadmed"], msrc, ms_codes)
        msrc["lisa"] = ms_lisa
        msrc["lisaUrl"] = aktilisa_url(msrc["id"], ms_lisa) if ms_lisa else None
        items.extend(ms_items)
        items.extend(ms_general)

    # 7. mootorsõidukijuht
    mj = sources["mootorsoidukijuht"]
    mj_pars, _ = walk_act(xmls["mootorsoidukijuht"])
    for par in mj_pars:
        items.append(make_sate("mootorsoidukijuht", mj, par))

    # 7b. sõeluuringud
    items.extend(soel_items)

    # 7c. igapäevatöö teemade õigusaktid (sätted) ja teemakaardid
    par_text, lisad = {}, {}
    for key, cfg in sources_cfg.items():
        s = sources[key]
        pars, _ = walk_act(xmls[key])
        want = cfg.get("par")
        par_text[key] = {}
        for p in pars:
            if want and p["nr"] not in want:
                continue
            sate = make_sate(key, s, p)
            par_text[key][p["nr"]] = {"id": p["id"], "t": " ".join(b.get("s", "") or " ".join(" ".join(r) for r in b.get("rows", [])) for b in sate["b"])}
            if key not in BASE_SOURCES:
                items.append(sate)
        if want:
            missing_pars = [x for x in want if x not in par_text[key]]
            if missing_pars:
                print(f"[hoiatus] {key}: sätteid ei leitud: {missing_pars}")
        lisad[key] = act_lisad(xmls[key], s["id"])
        if key not in BASE_SOURCES and lisad[key]:
            s["lisad"] = lisad[key]
    dyn = {"huvitised": huvitised}
    imm, imm_warn = imm_lisad(xmls["immkava"]) if "immkava" in xmls else ({}, [])
    dyn.update(imm)
    # metoodika lisad: teenuste standardkulu komponendid ja e-konsultatsiooni nõuded erialade kaupa
    ml = met_lisad.lisad_info(xmls["metoodika"], met["id"], cache, aktilisa_url)
    dyn["ekons"] = ml.get("ekons")
    teema_items, teema_warn = build_teemad(teemad_cfg, sources, par_text, dyn, lisad)
    teema_warn = hu_warn + imm_warn + ml.get("warn", []) + fund_warn + teema_warn
    items.extend(teema_items)

    # 7d. mis muutus: jõustunud (viimase aasta) ja avaldatud tulevaste redaktsioonide vahe
    muut, muut_warn = muutused.compute(sys.modules[__name__], sources_cfg, sources, chains, cache,
                                       (prev or {}).get("muutused"), TODAY)
    teema_warn += muut_warn

    # 8. fondid, lingid, sünonüümid
    items.extend(funds)
    with open(os.path.join(HERE, "links.json"), encoding="utf-8") as f:
        links = json.load(f)
    for ln in links:
        items.append(dict(ln, t="k"))
    for key, s in sources.items():
        items.append({"t": "k", "n": s["pealkiri"], "u": s["url"], "d": f'Riigi Teataja, kehtiv redaktsioon alates {fmt_date(s["alates"])}', "src": key})

    with open(os.path.join(HERE, "synonyms.json"), encoding="utf-8") as f:
        syn = json.load(f)
    missing = []
    for k, words in syn.items():
        if k.startswith("_"):
            continue
        if k.startswith("fond:"):
            targets = [x for x in items if x["t"] == "f" and x["k"] == k[5:]]
        elif k.startswith("sate:"):
            src_key, nr = k[5:].split(":", 1)
            targets = [x for x in items if x["t"] == "l" and x["src"] == src_key and x["par"] == nr]
        elif k.startswith("ms:"):
            key = norm_ascii(k[3:])
            targets = [x for x in items if x["t"] == "m" and (norm_ascii(x["n"]) == key or (x.get("c") or "").lower() == key)]
        elif k.startswith("lab:"):
            targets = [x for x in items if x["t"] == "b" and (x.get("ab") or "").lower() == k[4:].lower()]
        elif k.startswith("link:"):
            targets = [x for x in items if x["t"] == "k" and x.get("id") == k[5:]]
        else:
            targets = [by_code[k]] if k in by_code else [x for x in items if x["t"] == "a" and x["c"] == k]
        if not targets:
            missing.append(k)
        for x in targets:
            x.setdefault("syn", []).extend(words)

    meta = {
        "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": TODAY.isoformat(),
        "fingerprint": fingerprint,
        "sources": sources,
        "toru": toru_meta,
        "abivCols": ab_cols,
        "starRule": star_rule,
        "counts": {t: sum(1 for x in items if x["t"] == t) for t in ["s", "f", "l", "a", "k", "q", "b", "m", "v", "j"]},
        "soel": soel_meta,
        "huvitised": huvitised,
        "jalgimine": jalgimine,
        "teemad": {"kontrollitud": teemad_cfg["_meta"].get("kontrollitud"), "warn": teema_warn,
                   "allikad": {k: v["n"] for k, v in teemad_cfg.get("allikad", {}).items()}},
        "msUnmapped": ms_unmapped,
        "countsPa": sum(1 for x in items if x["t"] == "s" and x.get("pa")),
        "synlab": synlab_meta,
        "tk": tk,
        "ksNotes": ks_notes.get("_meta"),
    }
    kulu = ml.get("kulu")
    if kulu:
        meta["kulu"] = {"lisa": kulu["lisa"], "u": kulu["u"], "son": kulu["son"], "vigased": kulu["vigased"]}
    data = {"meta": meta, "items": items, "rules": rules, "muutused": muut,
            "kulu": {"res": kulu["res"], "c": kulu["c"]} if kulu else None}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(ROOT, "data", "version.json"), "w", encoding="utf-8") as f:
        json.dump({"built": meta["built"], "fingerprint": fingerprint}, f)

    report = make_report(prev, data, missing)
    with open(os.path.join(HERE, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    write_output(args, changed=True)


def write_output(args, changed):
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")


def fmt_date(iso):
    if not iso:
        return ""
    y, m, d = iso.split("-")
    return f"{d}.{m}.{y}"


def aktilisa_url(akt_id, fname):
    s = str(akt_id)
    return f"https://www.riigiteataja.ee/aktilisa/{s[0:4]}/{s[4:8]}/{s[8:12]}/{fname}"


# ----------------------------------------------------------------- Toru

def to_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str) and v.strip():
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S"):
            try:
                return dt.datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
    return None


def load_toru_rows(toru_dir):
    """Toru read: xlsx-failist (kui olemas) või sellest tehtud väljavõttest.
    Toru toorfaili ei hoita avalikus repos; väljavõte sisaldab ainult koodi,
    nimetust, hinda, kehtivust ja liiki kolme viimase perioodi kohta."""
    xlsxs = sorted(glob.glob(os.path.join(toru_dir, "*.xlsx")))
    extract_path = os.path.join(toru_dir, "toru_valjavote.json")
    if xlsxs:
        best, best_max, best_hist = None, None, None
        for path in xlsxs:
            wb = openpyxl.load_workbook(path, read_only=True)
            hist, mx = {}, None
            for i, r in enumerate(wb["Teenused"].iter_rows(values_only=True)):
                if i == 0 or r[0] is None:
                    continue
                alg, kuni = to_date(r[5]), to_date(r[6])
                if alg and (mx is None or alg > mx):
                    mx = alg
                price = float(r[3]) if isinstance(r[3], (int, float)) else None
                hist.setdefault(str(r[0]).strip(), []).append((alg, kuni, price, (r[2] or "").strip(), r[8] or None))
            if best_max is None or (mx and mx > best_max):
                best, best_max, best_hist = path, mx, hist
        out = {"file": os.path.basename(best), "seisuga": best_max.isoformat() if best_max else None, "rows": {}}
        for code, rows in best_hist.items():
            rows = sorted(rows, key=lambda x: x[0] or dt.date.min)
            if rows[-1][1] is not None and rows[-1][1] < TODAY - dt.timedelta(days=400):
                continue
            out["rows"][code] = [[a.isoformat() if a else None, k.isoformat() if k else None, p, n, h] for a, k, p, n, h in rows[-3:]]
        with open(extract_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    if not os.path.exists(extract_path):
        return None, None, {}
    with open(extract_path, encoding="utf-8") as f:
        ex = json.load(f)
    hist = {c: [(to_date(a), to_date(k), p, n, h) for a, k, p, n, h in rows] for c, rows in ex["rows"].items()}
    return ex["file"], ex["seisuga"], hist


def merge_toru(loaded, by_code, items):
    fname, seisuga, hist = loaded
    if not hist:
        return None
    added = mism = 0
    for code, rows in hist.items():
        rows.sort(key=lambda x: x[0] or dt.date.min)
        cur = [x for x in rows if x[0] and x[0] <= TODAY and (x[1] is None or x[1] >= TODAY)]
        if not cur:
            continue
        alg, kuni, price, name, hk = cur[-1]
        prev = [x for x in rows if x[0] and x[0] < alg]
        tp = {"p": price, "from": alg.isoformat(), "hk": hk}
        if prev:
            pa, pk, pp, pn, ph = prev[-1]
            if pp is not None and price is not None and pp != price:
                tp["prev"] = [pp, pa.isoformat()]
        it = by_code.get(code)
        if it is None:
            it = {"t": "s", "c": code, "n": name, "p": price, "src": "toru"}
            by_code[code] = it
            items.append(it)
            added += 1
        else:
            if it.get("p") is not None and tp["p"] is not None and abs(it["p"] - tp["p"]) > 0.001:
                it["tmis"] = True
                mism += 1
            if it.get("p") is None:
                it["p"] = tp["p"]
        it["tp"] = tp
    return {"file": fname, "seisuga": seisuga, "ainultToru": added, "hinnaErinevusi": mism}


# ----------------------------------------------------------------- abivahendid

def clean_cell(s):
    s = (s or "").replace(" ", " ")
    s = re.sub(r"([a-zõäöü])-\n([a-zõäöü])", r"\1\2", s)
    s = re.sub(r"\n\s*•", "\n•", s)
    s = re.sub(r"(?<!\n)\n(?!•)", " ", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def parse_abivahendid(xml):
    m = re.search(r'<fail[^>]*failNimi="([^"]*lisa[^"]*\.pdf)"[^>]*>([A-Za-z0-9+/=\s]+)</fail>', xml, re.I)
    if not m:
        return [], [], None
    name = m.group(1)
    pdf = pdfplumber.open(io.BytesIO(base64.b64decode(re.sub(r"\s", "", m.group(2)))))
    header, rows = None, []
    for p in pdf.pages:
        for tb in p.extract_tables():
            for r in tb:
                r = [clean_cell(c) for c in r][:18]
                if header is None and r and "ISO" in r[0]:
                    header = r
                    continue
                if not r or not r[0]:
                    if rows and any(r[1:]):
                        for i, c in enumerate(r):
                            if c and i > 0:
                                rows[-1][i] = (rows[-1][i] + " " + c).strip()
                    continue
                if re.match(r"^\d\d(\.\d\d)*$", r[0]):
                    rows.append(r)
    codes = [r[0] for r in rows]
    by = {r[0]: r for r in rows}

    def parent(c):
        parts = c.split(".")
        for k in range(len(parts) - 1, 0, -1):
            pc = ".".join(parts[:k])
            if pc in by:
                return pc
        return None

    items = []
    has_child = {parent(c) for c in codes if parent(c)}
    for r in rows:
        c = r[0]
        chain, pc = [], parent(c)
        while pc:
            chain.append(pc)
            pc = parent(pc)
        vals, inh = {}, []
        for i in range(2, 18):
            v = r[i]
            if not v:
                for a in chain:
                    if by[a][i]:
                        v = by[a][i]
                        inh.append(i)
                        break
            if v:
                vals[str(i)] = v
        items.append({
            "t": "a",
            "c": c,
            "n": r[1],
            "g": [by[a][1] for a in reversed(chain)],
            "v": vals,
            "inh": inh or None,
            "grp": c in has_child or None,
        })
    cols = header[:18] if header else []
    return items, cols, name


# ----------------------------------------------------------------- aruanne

def make_report(prev, data, missing):
    lines = [f"# Andmete uuendus {fmt_date(data['meta']['date'])}", ""]
    ns = data["meta"]["sources"]
    lines.append("## Allikad")
    for k, s in ns.items():
        old = prev["meta"]["sources"].get(k, {}).get("id") if prev else None
        mark = "" if old == s["id"] else (" **(uus redaktsioon)**" if old else "")
        fut = ""
        if s["tulevased"]:
            fut = "; tulevikus jõustub: " + ", ".join(f'[{x["id"]}]({RT}{x["id"]}) alates {fmt_date(x["alates"])}' for x in s["tulevased"])
        lines.append(f'- {s["nimi"]}: [{s["id"]}]({s["url"]}) kehtib alates {fmt_date(s["alates"])}{mark}{fut}')
    sm = data["meta"].get("synlab")
    if sm:
        lines.append(f'- SYNLABi hinnakiri: {sm.get("count")} analüüsi, {sm.get("title") or ""}')
    t = data["meta"].get("toru")
    if t:
        lines.append(f'- Toru: {t["file"]} (viimane muudatus {fmt_date(t["seisuga"])}), hinnaerinevusi loeteluga: {t["hinnaErinevusi"]}')
    lines.append("")
    pk = {x["k"] for x in (prev or {}).get("muutused") or []}
    newm = [x for x in data.get("muutused") or [] if x["k"] not in pk]
    if newm:
        lines.append("## Mis muutus: uued kirjed")
        for x in newm:
            parts = []
            k = x.get("kood") or {}
            for lab, key in (("uut koodi", "uus"), ("kadunud koodi", "kadunud"), ("hinnamuutust", "hind")):
                if k.get(key):
                    parts.append(f"{len(k[key])} {lab}")
            if x.get("fondPct"):
                parts.append("fondi protsent: " + ", ".join(f"{k} {v[0]}% → {v[1]}%" for k, v in x["fondPct"].items()))
            if x.get("fond"):
                parts.append(f'{len(x["fond"])} fondimuutust')
            if x.get("abiv"):
                parts.append(f'{sum(len(v) for v in x["abiv"].values())} abivahendi muutust')
            if x.get("ms"):
                parts.append(f'{sum(len(v) for v in x["ms"].values())} meditsiiniseadme toote muutust')
            if x.get("pars"):
                parts.append(f'{len(x["pars"])} sätet')
            if x.get("lisad"):
                parts.append(f'{len(x["lisad"])} lisa')
            lines.append(f'- {x["lyh"]} {"jõustub" if x.get("tul") else "jõustus"} {fmt_date(x["alates"])}: {", ".join(parts) or "sisulist muutust ei leitud"}')
        lines.append("")
    if prev:
        po = {x["c"]: x for x in prev["items"] if x["t"] == "s"}
        no = {x["c"]: x for x in data["items"] if x["t"] == "s"}
        ch = [(c, po[c].get("p"), no[c].get("p"), no[c]["n"]) for c in no if c in po and po[c].get("p") != no[c].get("p")]
        add = [c for c in no if c not in po]
        rem = [c for c in po if c not in no]
        fch = [(c, po[c].get("f"), no[c].get("f")) for c in no if c in po and po[c].get("f") != no[c].get("f")]
        lines.append(f"## Teenused: {len(ch)} hinnamuutust, {len(add)} uut, {len(rem)} eemaldatud, {len(fch)} fondimuutust")
        for c, a, b, n in ch[:60]:
            lines.append(f"- {c} {n}: {a} → {b}")
        if len(ch) > 60:
            lines.append(f"- … ja veel {len(ch) - 60}")
        for c in add[:40]:
            lines.append(f"- uus: {c} {no[c]['n']}")
        for c in rem[:40]:
            lines.append(f"- eemaldatud: {c} {po[c]['n']}")
        for c, a, b in fch[:40]:
            lines.append(f"- fond {c} {no[c]['n']}: {a} → {b}")
        pa = {x["c"]: x for x in prev["items"] if x["t"] == "a"}
        na = {x["c"]: x for x in data["items"] if x["t"] == "a"}
        ach = [c for c in na if c in pa and pa[c]["v"] != na[c]["v"]]
        lines.append(f"## Abivahendid: {len(ach)} muudetud, {len(set(na) - set(pa))} uut, {len(set(pa) - set(na))} eemaldatud")
        lines.append("")
    kn = data["meta"].get("ksNotes") or {}
    tkd = (data["meta"].get("tk") or {}).get("docs", [])
    newest = max([d["aasta"] for d in tkd if d["k"] in ("ind", "juhis")] or [0])
    unknown = [q["title"] for q in data["items"] if q["t"] == "q" and q.get("known") is False]
    if newest and kn.get("aasta") and newest > kn["aasta"]:
        lines.append(f"## NB: Tervisekassa on avaldanud kvaliteedisüsteemi {newest}. aasta juhendid")
        lines.append(f"Märkused failis build/ks_notes.json põhinevad {kn['aasta']}. aasta juhenditel; vaata need üle.")
        lines.append("")
    sv = [x for x in data["items"] if x["t"] == "v"]
    if sv:
        pv = {x["k"]: x for x in (prev or {}).get("items", []) if x["t"] == "v"}
        lines.append("## Vähi sõeluuringud (terviseportaal)")
        for x in sv:
            if x.get("sy"):
                old = pv.get(x["k"])
                mark = " **(muutus)**" if old and (old.get("aasta"), old.get("sy")) != (x.get("aasta"), x.get("sy")) else ""
                lines.append(f'- {x["n"]} {x.get("aasta")}: {x["vanus"][0]}–{x["vanus"][1]} a, iga {x.get("int")} a; sünniaastad {", ".join(map(str, x["sy"]))}{mark}')
            elif x.get("juhend"):
                old = pv.get(x["k"]) or {}
                mark = " **(uus juhend)**" if old.get("juhend") and old.get("juhend") != x["juhend"] else ""
                lines.append(f'- {x["n"]}: [tegevusjuhend]({x["juhend"]}){mark}')
        for w in (data["meta"].get("soel") or {}).get("warn", []):
            lines.append(f"- NB: {w}")
        lines.append("")
    tm = data["meta"].get("teemad") or {}
    jw = data["meta"].get("jalgimine") or {}
    pj = ((prev or {}).get("meta") or {}).get("jalgimine") or {}
    hu = data["meta"].get("huvitised") or {}
    tlines = [f"- NB: {w}" for w in tm.get("warn", [])]
    for k, v in jw.items():
        o = pj.get(k)
        name = tm.get("allikad", {}).get(k, k)
        if not v.get("ok") and (v.get("vigu") or 0) >= 2:
            tlines.append(f"- Allikas pole juba mitu kontrolli kättesaadav: {name} ({v.get('viga', '')})")
        elif o and v.get("ok") and o.get("ok") and (o.get("uuendatud"), o.get("sha")) != (v.get("uuendatud"), v.get("sha")):
            tlines.append(f"- Allikas muutus: {name} (uuendatud {v.get('uuendatud') or 'PDF sisu'}); vaata teemakaart üle (build/teemad.json)")
    po = ((prev or {}).get("meta") or {}).get("huvitised") or {}
    if po and po.get("rows") != hu.get("rows"):
        tlines.append("- Tervisekassa hüvitiste võrdlustabel muutus")
    if po and po.get("ylempiir") != hu.get("ylempiir"):
        tlines.append(f"- Hüvitise päevane ülempiir: {hu.get('ylempiir')}")
    lines.append("## Igapäevatöö teemakaardid")
    lines.extend(tlines or ["- Kõik teemakaartide tekstikontrollid läbitud."])
    lines.append("")
    if data["meta"].get("msUnmapped"):
        lines.append("## Meditsiiniseadme rühmad, millel puudub 9MS kood")
        lines.append(", ".join(data["meta"]["msUnmapped"]) + " (lisa kood faili build/ms_ryhmakoodid.json)")
        lines.append("")
    if unknown:
        lines.append("## Uued kvaliteedisüsteemi jaotised metoodika § 8-s (märkused puuduvad)")
        lines.append(", ".join(unknown))
        lines.append("")
    if prev:
        pq = {q["k"]: q for q in prev["items"] if q["t"] == "q"}
        for q in data["items"]:
            if q["t"] == "q" and q["k"] in pq and pq[q["k"]].get("rows") != q.get("rows"):
                lines.append(f"- Kvaliteedisüsteem muutus: {q['n']}")
        pdocs = {d["u"] for d in ((prev["meta"].get("tk") or {}).get("docs", []))}
        for d in tkd:
            if pdocs and d["u"] not in pdocs:
                lines.append(f"- Tervisekassa uus dokument: [{d['n']} {d['aasta']}]({d['u']})")
    if missing:
        lines.append("## Sünonüümide sihid, mida ei leitud")
        lines.append(", ".join(missing))
    c = data["meta"]["counts"]
    lines.append("")
    lines.append(f"Kokku: {c['s']} teenust, {c.get('m', 0)} meditsiiniseadmete rühma, {c.get('b', 0)} SYNLABi analüüsi, {c['a']} abivahendit, {c['l']} sätet, {c['f']} fondi, {c.get('q', 0)} kvaliteedisüsteemi jaotist, {c.get('v', 0)} sõeluuringut, {c.get('j', 0)} teemakaarti, {c['k']} linki.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    build(ap.parse_args())
