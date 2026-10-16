"""„Mis muutus“: kahe järjestikuse redaktsiooni vahe.

Iga jälgitava akti kohta võrreldakse viimase aasta jooksul jõustunud ja juba avaldatud
tulevasi redaktsioone eelmisega. Tulemus on loetelu kirjetest, mille rakendus näitab
vaates „Mis muutus“. Redaktsiooni ID on muutumatu, seega korra arvutatud kirje võetakse
järgmisel ehitusel eelmisest andmefailist üle (kui VERSION pole muutunud).

Võrreldakse:
- tervishoiuteenuste loetelu: koodid (uued, kadunud, hinna- ja nimemuutused) ning sätete tekst ilma tabeliteta;
- metoodika: fondide koodid (lisandunud, välja jäänud) ning sätete tekst;
- abivahendite ja meditsiiniseadmete loetelu: lisa read;
- muud aktid: jälgitavate paragrahvide tekst;
- kõigil aktidel: lisad (uus, kehtetu, sisu muutunud).
"""
import base64
import hashlib
import re

VERSION = 1
MAX_PARS = 40       # muutunud paragrahve ühe kirje kohta
MAX_LO = 6          # muutunud lõikeid paragrahvi kohta
TXT = 700           # lõike teksti pikkus
UNSUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ")).strip()


def cut(s):
    if s is None:
        return None
    return s if len(s) <= TXT else s[:TXT].rsplit(" ", 1)[0] + " …"


def par_key(nr):
    m = re.match(r"§\s*(\d+)(\S*)", nr or "")
    if not m:
        return (10 ** 6, nr or "")
    sup = m.group(2).translate(UNSUP)
    return (int(m.group(1)), int(sup) if sup.isdigit() else 0, nr)


def par_texts(pars, want=None, tables=False):
    """{paragrahv: {"n": pealkiri, "a": ankur, "lo": {lõige: tekst}}}"""
    out = {}
    for p in pars:
        if want and p["nr"] not in want:
            continue
        los = {}
        for lo in p["loiked"]:
            parts = []
            for b in lo["blocks"]:
                if b["t"] == "p":
                    parts.append(b["s"])
                elif tables:
                    parts.append(" | ".join(" / ".join(r) for r in b["rows"]))
            for pt in lo["punktid"]:
                parts.append(pt["nr"] + " " + " ".join(b.get("s", "") for b in pt["blocks"] if b["t"] == "p"))
                if tables:
                    parts += [" | ".join(" / ".join(r) for r in b["rows"]) for b in pt["blocks"] if b["t"] == "tbl"]
            t = re.sub(r"\[RT[^\]]*\]", "", norm(" ".join(parts))).strip()
            if t:
                los[lo["nr"] or "-"] = t
        if los:
            out[p["nr"]] = {"n": p["pealkiri"], "a": p["id"], "lo": los}
    return out


def diff_pars(a, b, url_new, url_old):
    out = []
    for nr in sorted(set(a) | set(b), key=par_key):
        pa, pb = a.get(nr), b.get(nr)
        if pa and pb and pa["lo"] == pb["lo"]:
            continue
        la, lb = (pa or {}).get("lo", {}), (pb or {}).get("lo", {})
        keys = list(dict.fromkeys(list(lb) + list(la)))
        los = [[("" if k == "-" else k), cut(la.get(k)), cut(lb.get(k))] for k in keys if la.get(k) != lb.get(k)]
        e = {"par": nr, "n": (pb or pa)["n"], "u": (url_new + "#" + pb["a"]) if pb else (url_old + "#" + pa["a"]),
             "lo": los[:MAX_LO]}
        if len(los) > MAX_LO:
            e["veel"] = len(los) - MAX_LO
        if pa is None:
            e["uus"] = True
        if pb is None:
            e["kehtetu"] = True
        out.append(e)
    return out


def lisa_key(name):
    m = re.search(r"lisa[_\s-]*(\d+)", name, re.I)
    return f"Lisa {int(m.group(1))}" if m else name


def lisa_hashes(xml):
    out = {}
    for name, b64 in re.findall(r'<fail[^>]*failNimi="([^"]+)"[^>]*>([A-Za-z0-9+/=\s]*)</fail>', xml):
        out[lisa_key(name)] = (name, hashlib.sha1(re.sub(r"\s", "", b64).encode()).hexdigest()[:12])
    return out


def diff_lisad(xa, xb, B, id_b, id_a):
    ha, hb = lisa_hashes(xa), lisa_hashes(xb)
    out = []
    for k in sorted(set(ha) | set(hb), key=lambda s: (0, int(s.split()[1])) if re.fullmatch(r"Lisa \d+", s) else (1, s)):
        a, b = ha.get(k), hb.get(k)
        if a and b and a[1] == b[1]:
            continue
        if b:
            out.append([k, "uus" if not a else "muudetud", B.aktilisa_url(id_b, b[0])])
        else:
            out.append([k, "kehtetu", B.aktilisa_url(id_a, a[0])])
    return out


# ----------------------------------------------------------------- aktipõhised hetkeseisud

def ttl_codes(B, pars):
    out = {}
    for par in pars:
        for lo in par["loiked"]:
            for b in lo["blocks"]:
                if b["t"] != "tbl":
                    continue
                for e in B.table_entries(b["rows"]):
                    for c in e["codes"]:
                        if c not in out:
                            pr = list(e["prices"].values())
                            out[c] = [e["name"], pr[0] if pr else None]
    return out


def met_funds(B, pars):
    """Sama loogika nagu build.py fondide tuvastamisel."""
    funds = {}
    for par in pars:
        if not par["ptk"].startswith("2."):
            continue
        for lo in par["loiked"]:
            txt = B.loige_text(lo)
            tbls = [b for b in lo["blocks"] if b["t"] == "tbl"]
            if not tbls:
                continue
            mp = re.search(r"kuni (\d+)\s*% perearsti nimistule pearahadeks arvestatud summast", txt)
            if mp:
                key = f"f{mp.group(1)}"
            elif "raviarve" in txt and "täiendavalt" in txt:
                key = "lisaks"
            else:
                continue
            s = funds.setdefault(key, {})
            for b in tbls:
                for e in B.table_entries(b["rows"]):
                    for c in e["codes"]:
                        s.setdefault(c, e["name"])
    return funds


def ms_products(B, xml):
    _, pdf = B.lisa_pdf(xml)
    out = {}
    if not pdf:
        return out
    for page in pdf.pages:
        for tb in page.extract_tables():
            for r in tb:
                r = [re.sub(r"\s+", " ", (c or "")).strip() for c in r]
                if len(r) >= 7 and re.fullmatch(r"\d{7}", r[2]):
                    out[r[2]] = [r[3], r[0], B.parse_price(r[5]), int(r[6]) if r[6].isdigit() else None]
    return out


# ----------------------------------------------------------------- ühe paari vahe

def diff_pair(B, key, cfg, a, b, xa, xb):
    """a, b: {"id", "alates"}; xa, xb: XML. Tagastab kirje või None, kui sisulist muutust ei leitud."""
    url_a, url_b = B.RT + a["id"], B.RT + b["id"]
    pa, _ = B.walk_act(xa)
    pb, _ = B.walk_act(xb)
    e = {"v": VERSION, "k": f'{key}:{a["id"]}:{b["id"]}', "src": key, "id": b["id"], "eid": a["id"],
         "alates": b["alates"], "ealates": a["alates"], "u": url_b, "eu": url_a}
    if key == "ttl":
        ca, cb = ttl_codes(B, pa), ttl_codes(B, pb)
        kood = {
            "uus": [[c, cb[c][0], cb[c][1]] for c in cb if c not in ca],
            "kadunud": [[c, ca[c][0], ca[c][1]] for c in ca if c not in cb],
            "hind": [[c, ca[c][1], cb[c][1]] for c in cb if c in ca and ca[c][1] != cb[c][1]],
            "nimi": [[c, ca[c][0], cb[c][0]] for c in cb if c in ca and norm(ca[c][0]) != norm(cb[c][0])],
        }
        if any(kood.values()):
            e["kood"] = kood
        e["pars"] = diff_pars(par_texts(pa), par_texts(pb), url_b, url_a)
    elif key == "metoodika":
        fa, fb = met_funds(B, pa), met_funds(B, pb)
        fond = []
        for fk in sorted(set(fa) | set(fb)):
            sa, sb = fa.get(fk, {}), fb.get(fk, {})
            fond += [[fk, "+", c, sb[c]] for c in sb if c not in sa]
            fond += [[fk, "-", c, sa[c]] for c in sa if c not in sb]
        if fond:
            e["fond"] = fond
        # § 8 (kvaliteedisüsteem) koos tabelitega, muu tekst ilma fonditabeliteta
        ta = par_texts(pa)
        tb = par_texts(pb)
        ka = par_texts([p for p in pa if p["nr"] == "§ 8"], tables=True)
        kb = par_texts([p for p in pb if p["nr"] == "§ 8"], tables=True)
        ta.update(ka)
        tb.update(kb)
        e["pars"] = diff_pars(ta, tb, url_b, url_a)
    elif key == "abivahendid":
        ia = {x["c"]: x for x in B.parse_abivahendid(xa)[0]}
        ib = {x["c"]: x for x in B.parse_abivahendid(xb)[0]}
        ch = []
        for c in ib:
            if c in ia and ia[c]["v"] != ib[c]["v"]:
                fields = sorted({k for k in set(ia[c]["v"]) | set(ib[c]["v"]) if ia[c]["v"].get(k) != ib[c]["v"].get(k)}, key=int)
                ch.append([c, ib[c]["n"], fields])
        abiv = {"uus": [[c, ib[c]["n"]] for c in ib if c not in ia],
                "kadunud": [[c, ia[c]["n"]] for c in ia if c not in ib], "muut": ch}
        if any(abiv.values()):
            e["abiv"] = abiv
        e["pars"] = diff_pars(par_texts(pa, tables=True), par_texts(pb, tables=True), url_b, url_a)
    elif key == "meditsiiniseadmed":
        ma, mb = ms_products(B, xa), ms_products(B, xb)
        ms = {"uus": [[c, mb[c][0], mb[c][1]] for c in mb if c not in ma],
              "kadunud": [[c, ma[c][0], ma[c][1]] for c in ma if c not in mb],
              "hind": [[c, mb[c][0], ma[c][2], mb[c][2]] for c in mb if c in ma and ma[c][2] != mb[c][2]],
              "pct": [[c, mb[c][0], ma[c][3], mb[c][3]] for c in mb if c in ma and ma[c][3] != mb[c][3]]}
        if any(ms.values()):
            e["ms"] = ms
        e["pars"] = diff_pars(par_texts(pa, tables=True), par_texts(pb, tables=True), url_b, url_a)
    else:
        want = cfg.get("par")
        e["pars"] = diff_pars(par_texts(pa, want, tables=True), par_texts(pb, want, tables=True), url_b, url_a)
    if len(e["pars"]) > MAX_PARS:
        e["parsVeel"] = len(e["pars"]) - MAX_PARS
        e["pars"] = e["pars"][:MAX_PARS]
    if not e["pars"]:
        del e["pars"]
    lis = diff_lisad(xa, xb, B, b["id"], a["id"])
    if lis:
        e["lisad"] = lis
    if not any(k in e for k in ("kood", "fond", "abiv", "ms", "pars", "lisad")):
        return None
    return e


def compute(B, sources_cfg, sources, chains, cache, prev_list, today, days=365):
    """Arvutab kõik kirjed. chains[key] = sisuga redaktsioonid kuupäeva järgi (ka tulevased)."""
    import datetime as dt
    cutoff = (today - dt.timedelta(days=days)).isoformat()
    prev = {x["k"]: x for x in (prev_list or []) if x.get("v") == VERSION}
    out, warn = [], []
    for key, cfg in sources_cfg.items():
        chain = chains.get(key) or []
        for i in range(1, len(chain)):
            a, b = chain[i - 1], chain[i]
            if not b["alates"] or b["alates"] < cutoff:
                continue
            k = f'{key}:{a["id"]}:{b["id"]}'
            if k in prev:
                out.append(prev[k])
                continue
            try:
                xa, xb = B.fetch_xml(a["id"], cache), B.fetch_xml(b["id"], cache)
                e = diff_pair(B, key, cfg, a, b, xa, xb)
            except Exception as ex:  # noqa: BLE001
                warn.append(f'{sources[key].get("lyh") or key} {a["id"]}→{b["id"]}: võrdlus ebaõnnestus ({str(ex)[:120]})')
                continue
            if e is None:
                e = {"v": VERSION, "k": k, "src": key, "id": b["id"], "eid": a["id"], "alates": b["alates"], "ealates": a["alates"],
                     "u": B.RT + b["id"], "eu": B.RT + a["id"], "tyhi": True}
            out.append(e)
            print(f"[muutus] {key} {a['alates']} → {b['alates']}", flush=True)
    for e in out:
        s = sources.get(e["src"]) or {}
        e["n"] = s.get("nimi") or e["src"]
        e["lyh"] = s.get("lyh") or e["n"]
        e["tul"] = e["alates"] > today.isoformat()
    out.sort(key=lambda x: x["alates"], reverse=True)
    return out, warn
