"""Ehitaja ühiktestid: avaldamise värav, kontrolli kuupäev, kuupäevade teisendus ja tabelite parsimine.

Käivitamine repo juurkaustast:
    pip install -r build/requirements.txt pytest
    pytest tests
"""
import copy
import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))

import build as B  # noqa: E402


@pytest.fixture(scope="module")
def data():
    with open(os.path.join(ROOT, "data", "data.json"), encoding="utf-8") as f:
        return json.load(f)


def variant(data, fn):
    d = copy.deepcopy(data)
    fn(d)
    return d


# ----------------------------------------------------------------- avaldamise värav

def test_gate_passes_identical_data(data):
    assert B.publish_gate(data, data) == []


def test_gate_passes_without_previous_data(data):
    assert B.publish_gate(None, data) == []


def test_gate_passes_small_change(data):
    def f(d):
        s = [x for x in d["items"] if x["t"] == "s" and not x.get("pa")]
        drop = {id(x) for x in s[: len(s) // 40]}  # umbes 2% teenustest
        d["items"] = [x for x in d["items"] if id(x) not in drop]
    assert B.publish_gate(data, variant(data, f)) == []


def test_gate_blocks_lost_services(data):
    def f(d):
        n = 0
        keep = []
        for x in d["items"]:
            if x["t"] == "s" and n % 5 == 0:
                n += 1
                continue
            n += x["t"] == "s"
            keep.append(x)
        d["items"] = keep
    out = B.publish_gate(data, variant(data, f))
    assert any(p.startswith("teenuseid:") for p in out), out


def test_gate_blocks_empty_service_table(data):
    out = B.publish_gate(data, variant(data, lambda d: d.update(items=[x for x in d["items"] if x["t"] != "s"])))
    assert any(p.startswith("teenuseid:") for p in out)
    assert any(p.startswith("perearstiabi koode:") for p in out)


def test_gate_blocks_missing_fund(data):
    def f(d):
        first = next(x for x in d["items"] if x["t"] == "f")
        d["items"].remove(first)
    out = B.publish_gate(data, variant(data, f))
    assert any("fondide võtmed muutusid" in p for p in out), out
    assert any(p.startswith("fonde:") for p in out), out


def test_gate_blocks_changed_fund_key(data):
    def f(d):
        fund = next(x for x in d["items"] if x["t"] == "f" and x.get("pct"))
        fund["k"] = "f99"
    out = B.publish_gate(data, variant(data, f))
    assert len(out) == 1 and "fondide võtmed muutusid" in out[0], out


def test_gate_blocks_shrunk_fund(data):
    def f(d):
        fund = max((x for x in d["items"] if x["t"] == "f"), key=lambda x: x["cnt"])
        fund["cnt"] = fund["cnt"] // 2
    out = B.publish_gate(data, variant(data, f))
    assert len(out) == 1 and out[0].startswith("fondi „"), out


def test_gate_blocks_lost_prices(data):
    def f(d):
        for x in d["items"]:
            if x["t"] == "s":
                x["p"] = None
    out = B.publish_gate(data, variant(data, f))
    assert any(p.startswith("piirhinnaga teenuseid:") for p in out), out


@pytest.mark.parametrize("label,mutate", [
    ("meditsiiniseadmete tooteid", lambda d: [x.update(pr=[]) for x in d["items"] if x["t"] == "m"]),
    ("ravijuhendite lisasid", lambda d: [x.update(lisad=[]) for x in d["items"] if x["t"] == "g"]),
    ("sätete tekstiplokke", lambda d: [x.update(b=[]) for x in d["items"] if x["t"] == "l"]),
    ("teemakaartide ridu", lambda d: [x.update(r=[]) for x in d["items"] if x["t"] == "j"]),
    ("standardkuluga koode", lambda d: d.update(kulu=None)),
    ("koodidega seotud reegleid", lambda d: d.update(rules=[])),
    ("laborianalüüse", lambda d: d.update(items=[x for x in d["items"] if x["t"] != "b"])),
    ("abivahendeid", lambda d: d.update(items=[x for x in d["items"] if x["t"] != "a"])),
])
def test_gate_blocks_emptied_source(data, label, mutate):
    out = B.publish_gate(data, variant(data, mutate))
    assert any(p.startswith(label + ":") for p in out), out


def test_gate_note_written_and_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "HERE", str(tmp_path))
    B.write_gate_note(["teenuseid: enne 2644, nüüd 0 (lubatud langus kuni 10%)"])
    note = (tmp_path / "varav_viga.md").read_text(encoding="utf-8")
    assert "teenuseid: enne 2644, nüüd 0" in note and "--luba-kahanemine" in note
    B.write_gate_note([])
    assert not (tmp_path / "varav_viga.md").exists()
    B.write_gate_note(["x"], allowed=True)
    assert not (tmp_path / "varav_viga.md").exists()


# ----------------------------------------------------------------- kontrolli kuupäev

def test_write_version_checked_date(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "ROOT", str(tmp_path))
    monkeypatch.setattr(B, "TODAY", dt.date(2026, 11, 16))
    p = tmp_path / "data" / "version.json"
    assert B.write_version("2026-11-12T12:25:26Z", "fp1") is True
    assert json.loads(p.read_text()) == {"built": "2026-11-12T12:25:26Z", "fingerprint": "fp1", "checked": "2026-11-16"}
    # sama päeva teine kontroll ei muuda faili
    assert B.write_version("2026-11-12T12:25:26Z", "fp1") is False
    # järgmine kontroll: kuupäev liigub, andmete versioon jääb
    monkeypatch.setattr(B, "TODAY", dt.date(2026, 11, 19))
    assert B.write_version("2026-11-12T12:25:26Z", "fp1") is True
    assert json.loads(p.read_text())["checked"] == "2026-11-19"
    # poolik kontroll (Riigi Teataja ei vastanud): kuupäev jääb eelmiseks
    monkeypatch.setattr(B, "TODAY", dt.date(2026, 11, 23))
    assert B.write_version("2026-11-12T12:25:26Z", "fp1", complete=False) is False
    assert json.loads(p.read_text())["checked"] == "2026-11-19"


def test_write_version_keeps_working_without_previous_checked(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "ROOT", str(tmp_path))
    monkeypatch.setattr(B, "TODAY", dt.date(2026, 11, 16))
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "version.json").write_text(json.dumps({"built": "b", "fingerprint": "fp"}))
    assert B.write_version("b", "fp", complete=False) is False
    assert "checked" not in json.loads((tmp_path / "data" / "version.json").read_text())


# ----------------------------------------------------------------- kuupäevad

@pytest.mark.parametrize("stamp,expected", [
    ("2026-06-30T21:00:00Z", "2026-07-01"),   # suveaeg: Eesti südaöö on 21:00 UTC
    ("2026-12-31T22:00:00Z", "2027-01-01"),   # talveaeg: 22:00 UTC
    ("2026-12-30T22:00:00Z", "2026-12-31"),   # kehtivuse lõpp (viimane kehtivuspäev)
    ("2026-03-31T21:00:00Z", "2026-04-01"),
    (None, None),
    ("", None),
])
def test_utc_to_local_date(stamp, expected):
    assert B.utc_to_local_date(stamp) == expected


# ----------------------------------------------------------------- tabelid

@pytest.mark.parametrize("s,expected", [
    ("16,04", 16.04), ("2982,88", 2982.88), ("1 234,5", 1234.5), ("1 234,56", 1234.56), ("83", 83.0),
    ("", None), (None, None), ("–", None), ("16.04", None), ("kokkuleppel", None),
])
def test_parse_price(s, expected):
    assert B.parse_price(s) == expected


@pytest.mark.parametrize("s,expected", [
    ("6417", ["6417"]), ("7900, 7901 ja 7902", ["7900", "7901", "7902"]), ("9038 või 9048", ["9038", "9048"]),
    ("278R; 279R", ["278R", "279R"]), ("kood", []), ("", []), (None, []), ("12", []),
])
def test_split_codes(s, expected):
    assert B.split_codes(s) == expected


def test_table_entries_reads_codes_prices_and_subheadings():
    rows = [
        ["Tervishoiuteenuse nimetus", "Kood", "Piirhind eurodes"],
        ["Uuringud"],
        ["Tümpanomeetriline uuring", "6417", "16,04"],
        ["Peapiirkonna röntgen*", "7900, 7901", "23,5"],
        ["Rida ilma koodita", "", ""],
        ["Vigane rida", "x"],
    ]
    out = B.table_entries(rows)
    assert [e["codes"] for e in out] == [["6417"], ["7900", "7901"]]
    assert out[0]["prices"] == {"Piirhind eurodes": 16.04} and out[0]["sub"] == "Uuringud" and out[0]["star"] is False
    assert out[1]["name"] == "Peapiirkonna röntgen" and out[1]["star"] is True


def test_table_entries_without_code_header_is_empty():
    assert B.table_entries([["Nimetus", "Hind"], ["Midagi", "1,00"]]) == []


# ----------------------------------------------------------------- avaldatud andmefail

def test_published_data_has_expected_shape(data):
    counts = data["meta"]["counts"]
    assert counts["f"] == 3 and counts["s"] > 2000 and counts["j"] >= 30
    assert sorted(B.fund_keys(data)) == sorted(B.FUND_NAMES)
    assert all(x.get("cnt", 0) > 10 for x in data["items"] if x["t"] == "f")
