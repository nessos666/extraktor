"""Tests fuer das Extractor Gate."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from extractor_gate import ExtractorGate, MemoryGate, TypePriorScorer  # noqa: E402


def test_starker_nugget_wird_gespeichert():
    gate = ExtractorGate()
    r = gate.process("Der CI-Fehler entstand weil .venv/bin/python hartkodiert war. "
                     "Fix: sys.executable nutzen.", topic="ci", domain="technik")
    assert r["store"] == "qdrant"
    assert r["gates_passed"] >= 4


def test_weichmacher_wird_verworfen():
    gate = ExtractorGate()
    r = gate.process("Vielleicht ist das irgendwie so", topic="x", domain="y")
    assert r["store"] == "discard"


def test_zu_kurzer_text_wird_verworfen():
    gate = ExtractorGate()
    r = gate.process("ok")
    assert r["store"] == "discard"


def test_pflichtgates_konkretheit():
    """Ohne Konkretheit (Zahl, Pfad, Akronym) darf nichts nach Qdrant."""
    gate = ExtractorGate()
    r = gate.process("Das System arbeitet mit mehreren Schritten und speichert dann.")
    assert r["store"] != "qdrant"


def test_zahl_erhoeht_score():
    s = TypePriorScorer("tool")
    ohne = s.score("Ein Werkzeug fuer Aufgaben")
    mit = s.score("Ein Werkzeug fuer Aufgaben mit 42 Treffern")
    assert mit >= ohne


def test_weichmacher_senkt_score():
    s = TypePriorScorer("strategy")
    hart = s.score("Regel: immer sys.executable verwenden")
    weich = s.score("Vielleicht koennte man eventuell sys.executable verwenden")
    assert weich < hart


def test_gates_liefern_struktur():
    g = MemoryGate()
    gates = g.pruefen("Ein konkreter Text mit Zahl 7 und Details.")
    assert len(gates) == 5
    for eintrag in gates:
        assert {"name", "passed", "confidence"} <= set(eintrag)


def test_leerer_text_faellt_durch():
    gate = ExtractorGate()
    assert gate.process("")["store"] == "discard"
