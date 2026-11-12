"""EHAS-i juhendi „Ravimite manustamine neelamisraskustega patsientidele ja sondi kaudu“ toimeainete register.

Loeb juhendi PDF-i (Wordist eksporditud, märgendatud PDF) tabeli struktuuripuust toimeaine, ATC-koodi,
ravimpreparaadid, ravimvormid, lehekülje ja ohtlikkuse märke (toimeaine lahtri värv) ning kirjutab need
käsitsi plokki `ehas-sond` failis build/ehas_register.json (ravijuhendid.json võti kasitsi_failid). Ettevalmistuse juhiseid (juhis, kommentaar,
imendumise koht, toit, märkused) ei kopeerita: need on juhendi PDF-is (lk viide).

Kasutus (käsitsi, kui juhendi PDF muutub ja kuukontroll annab kasitsi_sha hoiatuse):
    python build/ehas_register.py <juhend.pdf>
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict

import pdfplumber

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "ehas_register.json")  # ravijuhendid.json → kasitsi_failid
KEY = "ehas-sond"
ATC = re.compile(r"[A-Z]\d\d[A-Z]{2}\d\d")
YELLOW, LIGHT = (1.0, 1.0, 0.0), (1.0, 1.0, 0.82)


def norm(s):
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"(\w)- (\w)", r"\1\2", s)  # reavahetuse poolitus (Naatrium- valproaat)


def mcids(n):
    r = list(n.get("mcids") or [])
    for c in n.get("children", []):
        r += mcids(c)
    return r


def table_rows(n):
    if n.get("type") == "TR":
        yield n
    for c in n.get("children", []):
        yield from table_rows(c)


def cell_text(chs, rotated):
    if rotated:  # ATC-veerg on 90° pööratud
        return "".join(c["text"] for c in sorted(chs, key=lambda c: (round(c["x0"]), -c["top"])))
    out, last = "", None
    for c in sorted(chs, key=lambda c: (round(c["top"]), c["x0"])):
        if last and (abs(c["top"] - last["top"]) > 2 or c["x0"] - last["x1"] > 1.5):
            out += " "
        out += c["text"]
        last = c
    return out


def extract(pdf):
    rows = []
    for pi, p in enumerate(pdf.pages):
        tbs = p.find_tables()
        if not tbs or len(tbs[0].rows) < 2:
            continue
        hdr = tbs[0].rows[1].cells
        if len(hdr) < 11 or not all(hdr[1:5]):
            continue
        top = p.crop((0, 0, p.width, hdr[4][3] + 2)).extract_text() or ""
        if "Toimeaine" not in top or "Ravimpreparaadid" not in top:
            continue
        edges = [hdr[i][0] for i in range(1, 5)]
        bym = defaultdict(list)
        for ch in p.chars:
            if ch.get("mcid") is not None:
                bym[ch["mcid"]].append(ch)
        for root in p.structure_tree:
            for tr in table_rows(root):
                cells = defaultdict(list)
                for cell in tr.get("children", []):
                    if cell.get("type") not in ("TD", "TH"):
                        continue
                    chs = [c for m in mcids(cell) for c in bym.get(m, [])]
                    if not chs:
                        continue
                    col = sum(min(c["x0"] for c in chs) >= e - 1 for e in edges)
                    cells[col].append((norm(cell_text(chs, col == 0)), chs))
                if 1 in cells:
                    name, chs = cells[1][0]
                    if name == "Toimeaine":
                        continue
                    m = ATC.search(cells[0][0][0].replace(" ", "")) if 0 in cells else None
                    y0, y1 = min(c["top"] for c in chs), max(c["bottom"] for c in chs)
                    oht = None
                    for r in p.rects:
                        f = r.get("non_stroking_color")
                        if (r.get("fill") and isinstance(f, (list, tuple)) and r["x0"] <= edges[0] + 3
                                and r["x1"] >= edges[1] - 3 and r["top"] <= y0 and r["bottom"] >= y1):
                            f = tuple(f)
                            oht = "ohtlik" if f == YELLOW else (oht or ("rasedale ohtlik" if f == LIGHT else None))
                    rows.append({"n": name, "atc": m.group() if m else "", "prep": [], "vorm": [], "lk": [pi + 1], "oht": oht})
                elif 0 in cells and not any(k in cells for k in (2, 3)) and cells[0][0][0].isupper():
                    rows.append({"grp": cells[0][0][0]})
                    continue
                cur = next((r for r in reversed(rows) if "n" in r), None)
                if not cur:
                    continue
                if pi + 1 not in cur["lk"]:
                    cur["lk"].append(pi + 1)
                for col, key in ((2, "prep"), (3, "vorm")):
                    for t, _ in cells.get(col, []):
                        if t and t != "-" and t not in cur[key]:
                            cur[key].append(t)
    # Lehekülje vahetusel tekkinud nimeta read kuuluvad eelmise toimeaine juurde
    out = []
    for r in rows:
        if "n" in r and not r["n"]:
            prev = next((x for x in reversed(out) if "n" in x), None)
            if prev:
                prev["lk"] = sorted(set(prev["lk"] + r["lk"]))
                prev["prep"] += [x for x in r["prep"] if x not in prev["prep"]]
                prev["vorm"] += [x for x in r["vorm"] if x not in prev["vorm"]]
            continue
        if r.get("n") == "KÕIK TOIMEAINED":
            r["n"] = "Immunosupressandid (kõik toimeained)"
        out.append(r)
    # Valproaadi kombinatsiooni ATC-kood on PDF-is ühendatud lahtris
    for i, r in enumerate(out):
        if "n" in r and not r["atc"] and "valpro" in r["n"].lower():
            prev = next((x for x in reversed(out[:i]) if "n" in x and x["atc"]), None)
            if prev and "valpro" in prev["n"].lower():
                r["atc"] = prev["atc"]
    return out


def lk_txt(lk):
    return f"{lk[0]}–{lk[-1]}" if len(lk) > 1 else str(lk[0])


def block(rows, sha):
    read = []
    for r in rows:
        if "grp" in r:
            read.append([{"s": r["grp"].capitalize(), "c": 4, "h": 1, "k": "eg"}])
            continue
        nm = r["n"] + (f"\n{r['atc']}" if r["atc"] else "") + (f"\n⚠ {r['oht']} ravim" if r["oht"] else "")
        c0 = {"s": nm, "h": 1}
        if r["oht"]:
            c0["k"] = "eoy" if r["oht"] == "ohtlik" else "eol"
        read.append([c0, "\n".join(r["prep"]) or "–", "\n".join(r["vorm"]) or "–", lk_txt(r["lk"])])
    n_sub = sum(1 for r in rows if "n" in r)
    return {
        "n": "Toimeainete register ja põhimõtted",
        "lyh": "toimeainete register",
        "allikas": (f"Toimeainete register on loetud juhendi PDF-i tabelist (EHAS, versioon 02, veebruar 2022; PDF-i räsi {sha}): "
                    f"{n_sub} toimeainet või kombinatsiooni koos ATC-koodi, ravimpreparaatide, ravimvormide ja juhendi leheküljega. "
                    "Ettevalmistuse juhiseid (suu kaudu ja sondi kaudu), kommentaare, imendumise kohta, toidu mõju ja märkusi siin ei ole: "
                    "need on juhendi PDF-is näidatud leheküljel. Põhimõtted on teatmiku kokkuvõte juhendi üldosast. "
                    "Kui juhendi PDF muutub, tuleb aruandesse meeldetuletus (build/ehas_register.py)."),
        "plokid": [
            {"t": "def", "p": "Mis see on", "s": "Tööstusliku valmisravimi purustamine, dispergeerimine või kapsli avamine on enamasti ravimi omaduste kokkuvõttest väljas (off-label). Juhendi tabel annab iga toimeaine ja ravimvormi kohta eraldi juhise suu kaudu ja sondi kaudu manustamiseks; tabelit tuleb lugeda koos juhendi selgitava osaga (lk 1–6)."},
            {"t": "def", "p": "Enne ravimvormi muutmist", "s": "Mõtle, kas ravimi võib neelamishäire ajaks ära jätta, kas on olemas sobiv ravimvorm (vedelik, dispergeeruv tablett, muu manustamisviis) või sobivam toimeaine ja kas manustamiskordi saab vähendada. Tableti või kapsli sisu purustamine on viimane valik. Iga muudatuse korral vaata üle annus ja sagedus; ravimvormid ei pruugi olla bioekvivalentsed, vajadusel jälgi toimet (nt INR, TSH, ravimi kontsentratsioon)."},
            {"t": "def", "p": "„ÄRA PURUSTA!“", "s": "Juhendi märge: purustamine või närimine muudab ravimi toimet (nt prolongeeritud või gastroresistentne ravimvorm). Kui märget ei ole, võib dispergeerimiseks sobiva ravimi vajadusel ka purustada."},
            {"t": "def", "p": "Ettevalmistus ja sond", "s": "Valmista iga ravim eraldi ja vahetult enne manustamist; eelista dispergeerimist purustamisele. Sondi kaudu kasuta enteraalseid (ENFit) süstlaid, peata toitmine ja loputa sondi enne ja pärast ravimeid ning iga ravimi vahel (tavaliselt kahekordne sondi maht, 10–30 ml). Ravimit ei segata toitelahusesse. Sondi otsa asukoht (magu, duodeenum, jejunum) mõjutab imendumist."},
            {"t": "def", "p": "Käitleja ohutus", "s": "Kanna kindaid; purustamisel eelista kinnist tabletipurustajat. Kollase märkega (ohtlik) ravimite puhul FFP3 respiraator, nitriilkindad ja töökeskkonna saastumist vähendavad meetmed, muidu konsulteeri apteegiga; helekollase märkega (rasedale ohtlik) ravimeid rase või rasedust planeeriv töötaja ilma kaitsevahenditeta ei käitle. Nende ravimite jaoks ei kasutata uhmrit ega purustajat teistele ravimitele."},
            {"t": "tbl", "n": "Toimeainete register (juhendi järjekorras, ATC rühmade kaupa)", "filtr": True, "vasak": True,
             "pais": [["Toimeaine, ATC", "Ravimpreparaadid", "Ravimvormid", "Lk"]], "read": read},
        ],
    }


def main(path):
    raw = open(path, "rb").read()
    sha = hashlib.sha256(raw).hexdigest()[:16]
    with pdfplumber.open(path) as pdf:
        rows = extract(pdf)
    b = block(rows, sha)
    tbl = b["plokid"][-1]
    read, tbl["read"] = tbl["read"], "@READ@"
    txt = json.dumps({KEY: b}, ensure_ascii=False, indent=1)
    rows_txt = "[\n" + ",\n".join("     " + json.dumps(r, ensure_ascii=False) for r in read) + "\n    ]"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(txt.replace('"@READ@"', rows_txt) + "\n")
    print(f"{sum(1 for r in rows if 'n' in r)} toimeainet, {sum(1 for r in rows if 'grp' in r)} rühma; "
          f"pane build/ravijuhendid.json valised.x-ehas-sond.kasitsi_sha = \"{sha}\"")


if __name__ == "__main__":
    main(sys.argv[1])
