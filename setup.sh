#!/usr/bin/env bash
# Extraktor — Einrichtung in einem Schritt. Idempotent.
set -uo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"

echo "════════════════════════════════════════"
echo " Extraktor — Einrichtung"
echo "════════════════════════════════════════"
echo
FEHLER=0

echo "1) Python"
if command -v python3 >/dev/null 2>&1; then
    echo "   ✓ $(python3 -c 'import sys;print("python3 %d.%d"%sys.version_info[:2])')"
else
    echo "   ✗ python3 fehlt"; FEHLER=1
fi

echo
echo "2) Virtuelle Umgebung"
if [ -x .venv/bin/python ]; then echo "   ✓ .venv vorhanden"
else
    echo "   → lege .venv an …"
    python3 -m venv .venv || { echo "   ✗ fehlgeschlagen"; FEHLER=1; }
fi

echo
echo "3) Abhängigkeiten"
if [ -x .venv/bin/pip ]; then
    echo "   → installiere (kann 1-2 Minuten dauern) …"
    .venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
    if .venv/bin/pip install -q -r requirements.txt; then echo "   ✓ installiert"
    else echo "   ✗ Installation fehlgeschlagen"; FEHLER=1; fi
fi

echo
echo "4) Qdrant erreichbar?"
URL="${QDRANT_URL:-http://127.0.0.1:6335}"
if curl -s -m 3 "$URL/collections" >/dev/null 2>&1; then
    N=$(curl -s -m 5 "$URL/collections" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['result']['collections']))" 2>/dev/null || echo "?")
    echo "   ✓ $URL erreichbar ($N Collections)"
else
    echo "   !  $URL antwortet nicht — Extraktor braucht eine laufende Qdrant"
    echo "      (URL per QDRANT_URL setzbar)"
fi

echo
echo "5) Gate-Test"
if [ -x .venv/bin/python ]; then
    R=$(.venv/bin/python scripts/extractor_gate.py "Ein konkreter Test mit Zahl 42 und Details." 2>/dev/null | tail -1)
    case "$R" in *qdrant*) echo "   ✓ Gate arbeitet ($R)";; *) echo "   !  Gate-Ausgabe: $R";; esac
fi

echo
echo "════════════════════════════════════════"
if [ "$FEHLER" -eq 0 ]; then
    echo " FERTIG. Beispiel:"
    echo
    echo "   echo '[{\"collection\":\"knowledge_nuggets\",\"category\":\"TECHNIK\",\"text\":\"Dein Nugget mit Zahl 7\"}]' \\"
    echo "     | .venv/bin/python scripts/upsert.py --dry-run"
    echo
    echo " Health-Check: ./check.sh"
else
    echo " ACHTUNG — $FEHLER Schritt(e) fehlgeschlagen"
fi
echo "════════════════════════════════════════"
exit "$FEHLER"
