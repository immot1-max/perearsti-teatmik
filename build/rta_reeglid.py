"""Tervisekassa raviarvete automaatkontrolli reeglid perearstiabi koodide juures.

Allikas on Tervisekassa IT-juhendite lehe fail „Raviarvete reeglid“ (xlsx, leht „Reeglid“). Faili nimes
on kuupäev, seepärast loetakse link igal ehitusel lehelt. Teatmikus näidatav sõnastus on käsitsi
kirjutatud failis rta_reeglid.json (Tervisekassa kirjeldused on sisemises lühikeeles ja sisaldavad
töötajate nimesid); siin kontrollitakse, et iga kasutatud reegel on failis alles ja muutmata, ning
antakse aruandesse märku uutest perearstiabi mainivatest reeglitest.

Võrgutõrke korral jääb eelmine seis: reeglid tulevad seadistusest, kontroll jääb selleks korraks tegemata.
"""
import datetime as dt
import hashlib
import io
import json
import re
import urllib.parse

import openpyxl

PAGE = "https://tervisekassa.ee/partnerile/it-juhendid"
ANCHOR = PAGE + "#tab-raviarvete-saatmine"
LINK_RE = re.compile(r'href="([^"]*raviarve[_-]?reeglid[^"]*\.xlsx)"', re.I)
# Reeglid, mis nimetavad perearstiabi: rahastamise allikas PA, perearst, pereõde, üldarstiabi leping.
PA_RE = re.compile(r"\bPA\b|perearst|pereõ|üldarst|ÜRL|\bZYL\b", re.I)
COLS = ["id", "n", "alates", "kuni", "staatus", "k", "s", "v"]


def _date(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", str(v or ""))
    return m.group(0) if m else None


def _txt(v):
    return re.sub(r"[ \t]+", " ", str(v)).strip() if v is not None else ""


def load_rows(raw):
    """xlsx → {reegli ID: {n, alates, kuni, staatus, k, s, v}}."""
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb["Reeglid"] if "Reeglid" in wb.sheetnames else wb.worksheets[0]
    out = {}
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or not r or r[0] is None:
            continue
        r = list(r) + [None] * (len(COLS) - len(r))
        rid = _txt(r[0])
        out[rid] = {"n": _txt(r[1]), "alates": _date(r[2]), "kuni": _date(r[3]), "staatus": _txt(r[4]),
                    "k": _txt(r[5]), "s": _txt(r[6]), "v": _txt(r[7])}
    return out


def rule_sha(row):
    """Reegli sõrmejälg: nimetus, kehtivus, kirjeldus ja tingimused. Muutus tähendab, et käsitsi sõnastus tuleb üle vaadata."""
    key = "|".join([row["n"], row["alates"] or "", row["kuni"] or "", row["k"], row["s"]])
    return hashlib.sha1(re.sub(r"\s+", " ", key).encode()).hexdigest()[:12]


def codes_of(row):
    """Reegli tingimustes nimetatud teenuse koodid (vahemikud jäävad kujule algus:lõpp)."""
    out = []
    for line in row["s"].splitlines():
        m = re.match(r"\s*(?:Tervishoiuteenuse kood|Teenuse koefitsient|EMO)\s+(?:Ei\s+)?(?:Sisaldab(?: ainult| kõiki)?|sisalda(?: ainult| kõiki)?|Võrdub|võrdu)\s+(.+)", line)
        if not m:
            continue
        for tok in m.group(1).split(";"):
            tok = re.sub(r"\(.*?\)", "", tok).strip()
            if tok and tok not in out:
                out.append(tok)
    return out


def fetch(http_get):
    page = http_get(PAGE, timeout=60, tries=2).decode("utf-8", "replace")
    m = LINK_RE.search(page)
    if not m:
        raise RuntimeError("IT-juhendite lehelt ei leitud faili „Raviarvete reeglid“ linki")
    url = urllib.parse.urljoin(PAGE, m.group(1).replace("&amp;", "&"))
    raw = http_get(url, timeout=120, tries=2)
    return url, raw


def check(http_get, cfg, prev_meta, today):
    """Laeb faili ja võrdleb seadistusega. Tagastab meta (aruande ja rakenduse jaoks)."""
    prev_meta = prev_meta or {}
    rules = cfg.get("reeglid", {})
    try:
        url, raw = fetch(http_get)
        rows = load_rows(raw)
        if len(rows) < 100:
            raise RuntimeError(f"failist loeti ainult {len(rows)} reeglit")
    except Exception as e:  # noqa: BLE001
        print(f"[hoiatus] raviarvete reegleid ei saanud: {e}")
        meta = {k: prev_meta.get(k) for k in ("u", "fail", "seisuga", "count", "sha", "kontrollitud")}
        meta.update({"page": ANCHOR, "pa": len(rules), "warn": list(prev_meta.get("warn") or []),
                     "notes": list(prev_meta.get("notes") or []), "kontrollimata": today})
        return meta
    fail = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    md = re.search(r"(20\d\d)(\d\d)(\d\d)", fail)
    warn, notes = [], []
    for rid, c in rules.items():
        row = rows.get(rid)
        if row is None:
            warn.append(f"reeglit {rid} failis enam ei ole; eemalda see või vaata sõnastus üle („{c['s'][:70]}…“)")
            continue
        if row["kuni"] and row["kuni"] < today:
            warn.append(f"reegel {rid} „{row['n']}“ lõppes {row['kuni']}")
        if c.get("sha") and c["sha"] != rule_sha(row):
            warn.append(f"reegel {rid} „{row['n']}“ on failis muutunud; vaata teatmiku sõnastus üle ja uuenda sha ({rule_sha(row)})")
    # Reeglid, millele tugineb teemakaart „Raviarve“: sama kontroll, hoiatus viitab kaardile.
    for rid, c in cfg.get("kaart", {}).items():
        row = rows.get(rid)
        if row is None:
            warn.append(f"kaart „Raviarve“: reeglit {rid} ({c.get('m')}) failis enam ei ole; vaata kaardi rida üle")
        elif row["kuni"] and row["kuni"] < today:
            warn.append(f"kaart „Raviarve“: reegel {rid} ({c.get('m')}) lõppes {row['kuni']}")
        elif c.get("sha") and c["sha"] != rule_sha(row):
            warn.append(f"kaart „Raviarve“: reegel {rid} ({c.get('m')}) on failis muutunud; vaata kaardi rida üle ja uuenda sha ({rule_sha(row)})")
    known = set(rules) | set(cfg.get("kaart", {})) | set(cfg.get("valja", []))
    for rid, row in rows.items():
        if rid in known or (row["kuni"] and row["kuni"] < today):
            continue
        if PA_RE.search(" ".join([row["n"], row["k"], row["s"]])):
            notes.append(f"uus perearstiabi mainiv reegel {rid} „{row['n']}“ (alates {row['alates'] or '?'}); "
                         "lisa see faili rta_reeglid.json (reeglid või valja)")
    if prev_meta.get("fail") and prev_meta["fail"] != fail:
        notes.append(f"uus fail {fail} (eelmine {prev_meta['fail']})")
    return {"page": ANCHOR, "u": url, "fail": fail, "seisuga": f"{md.group(1)}-{md.group(2)}-{md.group(3)}" if md else None,
            "count": len(rows), "pa": len(rules), "sha": hashlib.sha1(raw).hexdigest()[:16], "kontrollitud": today,
            "warn": warn, "notes": notes}


def attach(cfg, by_code):
    """Seob seadistuse reeglid koodikirjetega (väli „ra“: indeksid loendisse data.rta).
    Koodid, mida loetelus ega Torus ei ole, jäetakse vahele ja tagastatakse teadmiseks."""
    out, missing = [], []
    for rid, c in cfg.get("reeglid", {}).items():
        idx = len(out)
        out.append({"id": rid, "s": c["s"], "al": c.get("alates")})
        for code in c.get("koodid", []):
            it = by_code.get(code)
            if it is None:
                if code not in c.get("puudub", []):
                    missing.append(f"reegel {rid}: koodi {code} ei ole loetelus ega Torus")
                continue
            ra = it.setdefault("ra", [])
            if idx not in ra:
                ra.append(idx)
    return out, missing


def fingerprint(cfg, meta):
    return json.dumps([cfg.get("reeglid"), cfg.get("kaart"), cfg.get("valja"), meta.get("sha"), meta.get("warn"), meta.get("notes")],
                      ensure_ascii=False, sort_keys=True)
