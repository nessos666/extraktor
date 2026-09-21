#!/usr/bin/env python3
"""Extractor Gate — Qualitaetspruefung fuer extrahierte Erkenntnisse.

Jeder Nugget MUSS hier durch, bevor er in Qdrant landet. Das Gate entscheidet:

    discard     -> nichts wert, verwerfen (kein Speichern)
    session_db  -> zu schwach fuer Qdrant, nur temporaer halten
    qdrant      -> speichern (mit Kategorie)

Historischer Hinweis: Diese Datei wurde aus dem Bytecode einer verlorenen
Fassung rekonstruiert (die .pyc ueberlebte ein Update, die Quelle nicht).
Die urspruengliche Fassung importierte TypePriorScorer und MemoryGate aus
hermes_brain; hier sind beide als eigenstaendige, abhaengigkeitsfreie
Klassen enthalten, damit das Tool ohne das grosse System laeuft.

Nutzung:
    from extractor_gate import ExtractorGate
    gate = ExtractorGate()
    result = gate.process("Text der Erkenntnis", topic="...", domain="...")
    if result["store"] == "qdrant":
        # in Qdrant schreiben, result["category"] als Kategorie
        ...
"""
from __future__ import annotations

import re

# Typen, die ein Nugget haben kann (Type-Prior: manche Typen sind wertvoller)
TYPEN = ("strategy", "system", "model", "tool", "paper", "concept")

# Wie stark jeder Typ grundsaetzlich gewichtet wird
TYPE_PRIOR = {
    "strategy": 1.00,   # Entscheidungen und Vorgehensweisen: hoechster Wert
    "system": 0.95,     # Architektur, Konfiguration
    "model": 0.90,      # Modell-Eigenschaften, Metriken
    "tool": 0.85,       # Werkzeuge, APIs, Befehle
    "paper": 0.80,      # Literaturerkenntnisse
    "concept": 0.60,    # allgemeine Begriffe
}

# Formulierungen, die auf Weichmacher hindeuten (senken die Confidence)
WEICHMACHER = (
    "vielleicht", "moeglicherweise", "könnte", "koennte", "eventuell",
    "irgendwie", "so ungefaehr", "ich glaube", "man sagt", "soll wohl",
)

# Formulierungen, die auf harte Fakten hindeuten (heben die Confidence)
HARTE_SIGNALE = (
    "immer", "nie", "niemals", "muss", "genau", "exakt", "gemessen",
    "getestet", "verifiziert", "fehler", "fix", "regel",
)


class TypePriorScorer:
    """Bewertet einen Nugget nach Typ, Laenge und Signalwoertern."""

    def __init__(self, typ: str = "concept") -> None:
        self.typ = typ if typ in TYPE_PRIOR else "concept"

    def score(self, text: str) -> float:
        basis = TYPE_PRIOR[self.typ]
        t = (text or "").lower()

        # Substanz: zu kurze oder zu lange Texte sind selten brauchbar
        n = len(t.split())
        if n < 4:
            basis *= 0.5
        elif n > 120:
            basis *= 0.8

        # Weichmacher senken, harte Signale heben
        if any(w in t for w in WEICHMACHER):
            basis *= 0.6
        if any(w in t for w in HARTE_SIGNALE):
            basis = min(1.0, basis * 1.15)

        # Konkrete Zahlen sind ein starkes Signal
        if re.search(r"\d", t):
            basis = min(1.0, basis * 1.1)

        return round(basis, 3)


class MemoryGate:
    """Fuenf Gates, die ein Nugget passieren muss.

    Jedes Gate liefert (name, passed, confidence). Das Gesamtergebnis ist die
    Anzahl bestandener Gates; erst ab einer Schwelle wird gespeichert.
    """

    # Ab wie vielen bestandenen Gates gespeichert wird
    SCHWELLE_QDRANT = 3
    SCHWELLE_SESSION = 2

    def __init__(self, min_laenge: int = 20) -> None:
        self.min_laenge = min_laenge

    def pruefen(self, text: str, topic: str = "", domain: str = "") -> list[dict]:
        t = (text or "").strip()
        tl = t.lower()
        gates = []

        # Gate 1: Substanz — lang genug, um ueberhaupt Inhalt zu haben
        gates.append({
            "name": "substanz",
            "passed": len(t) >= self.min_laenge,
            "confidence": min(1.0, len(t) / max(self.min_laenge, 1) / 2),
        })

        # Gate 2: Konkretheit — Zahlen, Pfade, Code-Muster oder Fachbegriff
        konkret = bool(
            re.search(r"\d", t)                                   # Zahlen
            or re.search(r"[\w/]+\.(py|json|md|sh|yml|yaml|db)\b", tl)  # Dateien
            or re.search(r"\b\w+[./]\w+\b", t)                     # Pfade/Module
            or re.search(r"\b[A-Z]{2,}\b", t)                      # Akronyme
        )
        gates.append({
            "name": "konkretheit",
            "passed": konkret,
            "confidence": 0.9 if konkret else 0.2,
        })

        # Gate 3: Kein Weichmacher — vage Aussagen sind keine Fakten
        weich = any(w in tl for w in WEICHMACHER)
        gates.append({
            "name": "kein_weichmacher",
            "passed": not weich,
            "confidence": 0.2 if weich else 0.9,
        })

        # Gate 4: nicht zu lang — Nuggets sind Chunks, keine Aufsaetze
        gates.append({
            "name": "laenge_ok",
            "passed": len(t) <= 1200,
            "confidence": 0.9 if len(t) <= 1200 else 0.3,
        })

        # Gate 5: Neuheits-Anmutung — Fragezeichen und Fuellwoerter meiden
        fuell = tl.startswith(("hier ist", "ich habe", "wie du", "das ist ein beispiel"))
        gates.append({
            "name": "keine_fuellphrase",
            "passed": not fuell,
            "confidence": 0.3 if fuell else 0.9,
        })

        return gates


class ExtractorGate:
    """Fuehrt Typprior und Gates zusammen und entscheidet den Zielort."""

    def __init__(self, typ: str = "concept") -> None:
        self.scorer = TypePriorScorer(typ)
        self.memory_gate = MemoryGate()

    def process(self, fact_text: str, topic: str = "", domain: str = "") -> dict:
        """Bewertet einen Nugget. Liefert dict mit 'store', 'category', 'gates'."""
        typ_score = self.scorer.score(fact_text)
        gates = self.memory_gate.pruefen(fact_text, topic, domain)
        passed = sum(1 for g in gates if g["passed"])

        # Pflicht-Gates: ohne Substanz, ohne Konkretheit, mit Weichmacher oder als
        # Fuellphrase erkannt ist es kein Nugget, egal wie viele der weichen Gates bestehen.
        # (Verschaeft 21.09.2026: vorher waren nur substanz+konkretheit Pflicht, dadurch
        #  passierte ein als Fuellphrase erkannter Satz mit einer Ziffer das Gate.)
        pflicht = ("substanz", "konkretheit", "kein_weichmacher", "keine_fuellphrase")
        pflicht_ok = all(g["passed"] for g in gates if g["name"] in pflicht)

        if typ_score < 0.25 or not pflicht_ok:
            ziel = "discard"
        elif passed >= 4 and typ_score >= 0.5:
            ziel = "qdrant"
        elif passed >= 3:
            ziel = "session_db"
        else:
            ziel = "discard"

        return {
            "store": ziel,
            "category": domain or "unknown",
            "score": typ_score,
            "gates": gates,
            "gates_passed": passed,
            "kontext": f"Topic: {topic}. Domain: {domain}",
        }


if __name__ == "__main__":
    import sys

    text = " ".join(sys.argv[1:]) or "Testnugget mit Zahl 42 und konkreter Aussage."
    gate = ExtractorGate()
    r = gate.process(text, topic="demo", domain="test")
    print(f"TypePrior {r['score']:.2f} | {r['kontext']}")
    for g in r["gates"]:
        print(f"  Gate: {g['name']:20s} {'PASS' if g['passed'] else 'FAIL'} ({g['confidence']:.2f})")
    print(f"{'OK' if r['store'] == 'qdrant' else 'Temp' if r['store'] == 'session_db' else 'Verworfen'}: {r['store']}")
