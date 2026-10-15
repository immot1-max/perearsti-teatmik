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
import urllib.request
import xml.etree.ElementTree as ET

import openpyxl
import pdfplumber
from lxml import html as lhtml

BUILD_VERSION = "1"
API = "https://www.riigiteataja.ee/public-api/api/v1"
RT = "https://www.riigiteataja.ee/akt/"
NS = "{maarus_1_10.02.2010}"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
TODAY = dt.date.today()
# Fondide argikeelsed nimed (määruse tekstis neid ei ole)
FUND_NAMES = {"f37": "Uuringufond", "lisaks": "Tegevusfond", "f13": "Teraapiafond"}


# ----------------------------------------------------------------- võrk

def http_get(url, timeout=300, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "perearsti-teatmik/1 (+github pages)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Päring ebaõnnestus: {url}: {last}")


def api_json(path):
    return json.loads(http_get(API + path, timeout=60))


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


def resolve_current(grupi_id, cache_dir, depth=0):
    """Leiab grupi kehtiva redaktsiooni. Kui akt on kehtetuks tunnistatud ja
    asendatud uue aktiga (nagu tervishoiuteenuste loeteluga juhtub), järgib
    kehtetuks tunnistamise märget uue aktini."""
    if depth > 4:
        raise RuntimeError("Liiga pikk asendusaktide ahel")
    red = api_json(f"/akt/{grupi_id}/redaktsioonid")
    kid = red["kehtivRedaktsioon"]
    meta = api_json(f"/akt/{kid}")
    xml = fetch_xml(kid, cache_dir)
    body = re.sub(r"<metaandmed>.*?</metaandmed>", "", xml, flags=re.S)
    m = re.search(r"<oigusakt[^>]*>\s*(?:<aktinimi>.*?</aktinimi>)?\s*<muutmismarge>(.*?)</muutmismarge>", body, flags=re.S)
    is_repealed = meta.get("aktiStaatus") == "KEHTETU" or (
        m and "Kehtetu" in m.group(1) and re.search(r"<sisu[^>]*/>", body))
    if is_repealed and m:
        new_id = re.search(r"<aktViide[^>]*>(\d+)</aktViide>", m.group(1)).group(1)
        new_meta = api_json(f"/akt/{new_id}")
        return resolve_current(new_meta["grupiId"], cache_dir, depth + 1)
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
        if tag in ("muutmismarge", "kuvatavNr", "loigeNr", "alampunktNr", "paragrahvNr"):
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
    return re.sub(r"\s+", " ", "".join(parts)).strip()


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
    sources, xmls = {}, {}
    for key, cfg in sources_cfg.items():
        info, xml = resolve_current(cfg["grupiId"], cache)
        info["nimi"] = cfg["nimi"]
        sources[key] = info
        xmls[key] = xml
        if str(info["grupiId"]) != str(cfg["grupiId"]):
            cfg["grupiId"] = info["grupiId"]
            print(f"[info] {key}: akt asendati, uus grupi ID {info['grupiId']}")

    toru_dir = os.path.join(HERE, "toru")
    aux_hash = hashlib.sha256()
    for fn in ["synonyms.json", "links.json", "build.py", "ks_notes.json", "ms_ryhmakoodid.json", "soeluuringud.json"]:
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
                    label = f"{FUND_NAMES[fund_key]} · kuni {mp.group(1)}% pearahast"
            elif tbls and "raviarve" in txt and "täiendavalt" in txt:
                fund_key = "lisaks"
                label = f"{FUND_NAMES['lisaks']} · raviarvega lisaks pearahale"
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
                })
            elif txt:
                text_rules.append(("metoodika", par, lo, txt))
    # tärni tingimus
    star_rule = next((t for (s, p, l, t) in text_rules if s == "metoodika" and "tärniga" in t), None)

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
        if it["t"] == "s" and (it.get("f") or it.get("ks") or (it.get("ptk") or "").startswith("2.")
                               or (it.get("tp") or {}).get("hk") == "PEREARSTIABI" or it.get("src") == "metoodika"):
            it["pa"] = True
    for lb in labs:
        for k in ("f", "ks", "miss"):
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
        "counts": {t: sum(1 for x in items if x["t"] == t) for t in ["s", "f", "l", "a", "k", "q", "b", "m", "v"]},
        "soel": soel_meta,
        "msUnmapped": ms_unmapped,
        "countsPa": sum(1 for x in items if x["t"] == "s" and x.get("pa")),
        "synlab": synlab_meta,
        "tk": tk,
        "ksNotes": ks_notes.get("_meta"),
    }
    data = {"meta": meta, "items": items, "rules": rules}
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
    lines.append(f"Kokku: {c['s']} teenust, {c.get('m', 0)} meditsiiniseadmete rühma, {c.get('b', 0)} SYNLABi analüüsi, {c['a']} abivahendit, {c['l']} sätet, {c['f']} fondi, {c.get('q', 0)} kvaliteedisüsteemi jaotist, {c.get('v', 0)} sõeluuringut, {c['k']} linki.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    build(ap.parse_args())
