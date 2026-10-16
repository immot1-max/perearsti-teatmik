"""Metoodika lisad: teenuste standardkulu komponendid (lisa „Teenuste standardkulu
komponendid“) ja e-konsultatsiooni saatekirja nõuete lisad erialade kaupa.

Lisa PDF-id on metoodika XML-is base64-na. Parsimine on aeglane (standardkulu lisa
on üle 300 lehekülje), seega tulemus hoitakse vahemälus redaktsiooni ID järgi.
"""
import base64
import io
import json
import os
import re

import pdfplumber

VERSION = 2

# Standardkulu tabeli veergude vasakud piirid (pt). Päisest loetud: teenuse kood 20,
# ressursi kood 78, nimi 153, keskmine maht 267, ühiku maksumus 337, mõõtühik 396, optimaalne maht 466.
COLS = [("c", 0), ("r", 75), ("n", 150), ("m", 265), ("p", 335), ("u", 395), ("o", 460)]
NUM = re.compile(r"^\d[\d ]*,\d+$")


def _col(x0):
    k = COLS[0][0]
    for name, left in COLS:
        if x0 >= left - 0.5:
            k = name
    return k


def _join(chars):
    """Märgid sõnadeks: tühik, kui kahe märgi vahel on vahe."""
    out, prev = "", None
    for ch in sorted(chars, key=lambda c: c["x0"]):
        if prev is not None and ch["x0"] - prev["x1"] > 1.0:
            out += " "
        out += ch["text"]
        prev = ch
    return out.strip()


def parse_kulu_pdf(pdf):
    """Tagastab (read, vigased): read = [kood, ressursi kood, nimi, maht, ühikuhind, mõõtühik]."""
    rows, bad = [], []
    for page in pdf.pages:
        lines = {}
        for ch in page.chars:
            if not ch["text"].strip():
                continue
            lines.setdefault(round(ch["top"]), []).append(ch)
        # read, mille top erineb 1 pt võrra, liidetakse
        keys = sorted(lines)
        merged = []
        for k in keys:
            if merged and k - merged[-1][0] <= 1:
                merged[-1][1].extend(lines[k])
            else:
                merged.append([k, list(lines[k])])
        for _, chars in merged:
            cols = {k: [] for k, _ in COLS}
            for ch in chars:
                k = _col(ch["x0"])
                # Pikk nimi valgub üle mahu ja hinna veergu: sealsed tähed kuuluvad nimele.
                if k in ("m", "p") and not re.match(r"[\d,]", ch["text"]):
                    k = "n"
                cols[k].append(ch)
            # Mahu ja hinna veerus on väärtus parempoolseim arv; muud numbrid on nime osa (nt „70–150 TÜ“).
            for k in ("m", "p"):
                toks, cur, prev = [], [], None
                for ch in sorted(cols[k], key=lambda c: c["x0"]):
                    if prev is not None and ch["x0"] - prev["x1"] > 1.0:
                        toks.append(cur)
                        cur = []
                    cur.append(ch)
                    prev = ch
                if cur:
                    toks.append(cur)
                val = next((t for t in reversed(toks) if NUM.match("".join(c["text"] for c in t))), None)
                for t in toks:
                    if t is not val:
                        cols["n"].extend(t)
                cols[k] = val or []
            vals = {k: _join(v) for k, v in cols.items()}
            code, res = vals["c"], vals["r"]
            if not re.fullmatch(r"[0-9A-Z]{3,8}", code or "") or not res or not re.match(r"^[A-Za-z]", res):
                continue
            m, p = vals["m"].replace(" ", ""), vals["p"].replace(" ", "")
            if not (NUM.match(m) and NUM.match(p)):
                bad.append([code, res, vals["n"], vals["m"], vals["p"]])
                continue
            rows.append([code, res, vals["n"], float(m.replace(",", ".")), float(p.replace(",", ".")), vals["u"]])
    return rows, bad


def ekons_info(title):
    """E-konsultatsiooni lisa pealkirjast: (kellele, saatja, märkus)."""
    t = " ".join(title.split())
    if not re.search(r"E-?\s?konsultatsiooni saatekirja|E-saatekirja", t, re.I):
        return None
    who = re.search(r"nõuded\s+(\S+(?:\s\S+)?)\s+poolt", t)
    m = re.search(r"suunamisel\s+(.+?)\s+e-\s?konsult", t)
    if not m:
        return None
    to = m.group(1).replace("pea-ja", "pea- ja")
    sender = (who.group(1) if who else "").lower()
    sender = {"perearsti": "perearst", "arsti": "arst", "eriõe": "eriõde", "hambaarsti": "hambaarst"}.get(sender, sender)
    if to == "erialadevahelisele":
        return ("Erialadevaheline (eriarstilt eriarstile)", "eriarst", "")
    note = ""
    if re.search(r"lapse kuni 15", t):
        note = "laps kuni 15 a (k.a)"
    elif re.search(r"täiskasvanud \(alates 16", t):
        note = "täiskasvanu alates 16 a"
    return (to[0].upper() + to[1:] + " e-konsultatsioon", sender, note)


def lisad_info(xml, met_id, cache_dir, aktilisa_url):
    p = os.path.join(cache_dir, f"metlisad_{met_id}_v{VERSION}.json") if cache_dir else None
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    lisad, kulu, ekons, warn = [], None, [], []
    for name, b64 in re.findall(r'<fail[^>]*failNimi="([^"]+\.pdf)"[^>]*>([A-Za-z0-9+/=\s]+)</fail>', xml, re.I):
        mnr = re.search(r"lisa[_\s-]*(\d+)", name, re.I)
        nr = int(mnr.group(1)) if mnr else None
        try:
            pdf = pdfplumber.open(io.BytesIO(base64.b64decode(re.sub(r"\s", "", b64))))
            first = pdf.pages[0].extract_text() or ""
        except Exception as e:  # noqa: BLE001
            warn.append(f"Metoodika {name}: PDF-i ei saanud lugeda ({e})")
            continue
        flat = " ".join(first.split())
        son = re.search(r"\(([^()]*?määruse nr \d+ sõnastuses)\)", flat)
        url = aktilisa_url(met_id, name)
        lisad.append({"nr": nr, "f": name, "u": url, "son": son.group(1) if son else None})
        if re.search(r"Teenuste standardkulu komponendid", flat):
            rows, bad = parse_kulu_pdf(pdf)
            res, codes = {}, {}
            for code, rc, rn, m, pr, unit in rows:
                if rc not in res:
                    res[rc] = [rn, unit]
                codes.setdefault(code, []).append([rc, m, pr])
            badc = sorted({b[0] for b in bad})
            kulu = {"lisa": nr, "u": url, "son": son.group(1) if son else None, "res": res, "c": codes, "vigased": badc}
            if bad:
                warn.append(f"Standardkulu lisa: {len(bad)} rida ei õnnestunud lugeda (koodid {', '.join(badc[:15])}{'…' if len(badc) > 15 else ''}).")
            print(f"[kulu] {len(rows)} rida, {len(codes)} teenust, {len(bad)} vigast", flush=True)
        else:
            info = ekons_info(flat[:900])
            if info:
                ekons.append([info[0], info[1], info[2], nr, url])
    out = {"lisad": lisad, "kulu": kulu, "ekons": sorted(ekons, key=lambda x: x[0].lower()), "warn": warn}
    if p:
        os.makedirs(cache_dir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
    return out
