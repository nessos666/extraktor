"""memory_kandidaten.py — Variante A des Extraktors (20.09.2026, David).

Zweck: VOR jedem Living-Memory-Write die Kandidaten aufbereiten, damit im Chat eine
Ja/Nein-Auswahl (clarify) gezeigt werden kann. Dieses Skript schreibt NIEMALS selbst
ins Living Memory — es schlaegt nur vor und prueft Laenge + Duplikate.

Aufruf (stdin = Nugget-JSON wie bei upsert.py):
    python memory_kandidaten.py [--kategorien REGELN,DAVID] [--max-len 150] [--json]

WICHTIG (gemessen 20.09.2026): Das AKTIVE Living Memory sind die Dateien
    ~/.hermes/memories/MEMORY.md  (Budget 3500 Zeichen)
    ~/.hermes/memories/USER.md    (Budget 2000 Zeichen)
Eintraege sind mit "§" getrennt. Die SQLite-DB ~/.hermes/memory_store.db (519 Fakten)
ist der FACT-STORE, NICHT das injizierte Memory — sie wird nur als Zusatz-Abgleich genutzt.

Ausgabe: Klartextliste + (--json) JSON mit kandidaten / verworfen / duplikate /
memory_auslastung. Exit-Code immer 0 — der Aufrufer (Chat) entscheidet.
"""

import argparse
import glob
import json
import os
import re
import sqlite3
import sys

MEM_DIR = os.path.expanduser("~/.hermes/memories")
AKTIVE_DATEIEN = [("MEMORY.md", 3500), ("USER.md", 2000)]
FACT_DB = os.path.expanduser("~/.hermes/memory_store.db")


def lade_aktive():
    """Aktive Memory-Eintraege (Dateien), je Datei (name, datei, eintraege, zeichen, budget)."""
    bloecke = []
    for name, budget in AKTIVE_DATEIEN:
        pfad = os.path.join(MEM_DIR, name)
        if not os.path.exists(pfad):
            continue
        roh = open(pfad, encoding="utf-8", errors="replace").read()
        teile = [t.strip() for t in re.split(r"\n?§\n?", roh) if t.strip()]
        bloecke.append((name, pfad, teile, len(roh.strip()), budget))
    return bloecke


def lade_fact_db():
    if not os.path.exists(FACT_DB):
        return []
    try:
        con = sqlite3.connect(f"file:{FACT_DB}?mode=ro", uri=True)
        rows = con.execute("select fact_id, content from facts").fetchall()
        con.close()
        return rows
    except Exception as e:
        print(f"[warn] fact-store nicht lesbar: {e}", file=sys.stderr)
        return []


def woerter(text):
    return set(re.findall(r"[a-z0-9äöüß]+", text.lower()))


def jaccard(a, b):
    return 0.0 if not a or not b else len(a & b) / len(a | b)


def naechster_satz(satz, eintraege, schwelle=0.55):
    """(index, eintrag, score) des aehnlichsten aktiven Eintrags oder None."""
    w = woerter(satz)
    best = None
    for i, e in enumerate(eintraege):
        if satz.lower() in e.lower() or e.lower() in satz.lower():
            return (i, e, 1.0)
        s = jaccard(w, woerter(e))
        if s >= schwelle and (best is None or s > best[2]):
            best = (i, e, round(s, 3))
    return best


def auswerten(nuggets, kategorien, max_len):
    bloecke = lade_aktive()
    aktive = [e for _n, _p, teile, _z, _b in bloecke for e in teile]
    cand, verworfen, duplikate = [], [], []
    for n in nuggets:
        kat = str(n.get("category", "")).strip().upper()
        if kat not in kategorien:
            continue
        roh = str(n.get("text", "")).strip()
        satz = re.sub(r"^[^:]{0,60}:\s*", "", roh).strip()   # "Topic: Regel" -> Regel
        satz = " ".join(satz.split())
        if len(satz) < 20:
            verworfen.append({"text": satz, "grund": "zu kurz (<20 Zeichen)"})
            continue
        if len(satz) > max_len:
            verworfen.append({"text": satz, "grund": f"zu lang ({len(satz)} > {max_len} Zeichen)"})
            continue
        treffer = naechster_satz(satz, aktive)
        if treffer:
            duplikate.append({"text": satz, "bereich": "aktiv", "aehnlich_zu": treffer[1][:120], "score": treffer[2]})
            continue
        cand.append({"text": satz, "kategorie": kat, "zeichen": len(satz), "source": n.get("source", "")})
    return cand, verworfen, duplikate, bloecke, aktive


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kategorien", default="REGELN,DAVID")
    ap.add_argument("--max-len", type=int, default=150)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fact-db", action="store_true", help="zusaetzlich gegen fact-store pruefen")
    a = ap.parse_args()
    kats = {k.strip().upper() for k in a.kategorien.split(",") if k.strip()}
    roh = sys.stdin.read().strip()
    if not roh:
        print("kein Input auf stdin", file=sys.stderr)
        return 1
    try:
        data = json.loads(roh)
    except json.JSONDecodeError as e:
        print(f"ungueltiges JSON: {e}", file=sys.stderr)
        return 1
    nuggets = data if isinstance(data, list) else data.get("nuggets", [])
    cand, verworfen, duplikate, bloecke, aktive = auswerten(nuggets, kats, a.max_len)
    db_dup = []
    if a.fact_db:
        fakten = lade_fact_db()
        for c in list(cand):
            for fid, content in fakten:
                if jaccard(woerter(c["text"]), woerter(content)) >= 0.6:
                    db_dup.append({"text": c["text"], "fact_id": fid, "aehnlich_zu": content[:120]})
                    break
    auslastung = [{"datei": n, "zeichen": z, "budget": b, "prozent": round(100 * z / b, 1),
                   "eintraege": len(teile)} for n, _p, teile, z, b in bloecke]
    ergebnis = {"kandidaten": cand, "verworfen": verworfen, "duplikate": duplikate,
                "duplikate_fact_store": db_dup, "memory_auslastung": auslastung}
    if a.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
        return 0
    print(f"=== Living-Memory-KANDIDATEN ({len(cand)}) — noch NICHT geschrieben ===")
    for i, c in enumerate(cand, 1):
        print(f"  {i}. [{c['kategorie']}] ({c['zeichen']} Zeichen) {c['text']}")
    if duplikate:
        print(f"\n--- bereits im aktiven Memory ({len(duplikate)}) ---")
        for d in duplikate:
            print(f"  ~ sim {d['score']}: {d['text'][:80]}")
    if db_dup:
        print(f"\n--- bereits im fact-store ({len(db_dup)}) ---")
        for d in db_dup:
            print(f"  ~ fact_id {d['fact_id']}: {d['text'][:80]}")
    if verworfen:
        print(f"\n--- verworfen ({len(verworfen)}) ---")
        for v in verworfen:
            print(f"  x {v['grund']}: {v['text'][:80]}")
    print("\nAuslastung aktives Memory:")
    for x in auslastung:
        print(f"  {x['datei']}: {x['zeichen']}/{x['budget']} Zeichen ({x['prozent']} %), {x['eintraege']} Eintraege")
    if any(x["prozent"] >= 90 for x in auslastung):
        print("HINWEIS: Memory fast voll — vor dem Schreiben konsolidieren (Skill hermes-memory-pflege).")
    print("\nNAECHSTER SCHRITT (Pflicht, Skill Schritt 3b): diese Liste als Ja/Nein-Auswahl im Chat "
          "zeigen; nur bestaetigte Saetze mit dem memory-Tool schreiben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
