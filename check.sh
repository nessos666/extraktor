#!/usr/bin/env bash
# Extraktor — Health-Check.
REPO="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO"
FEHLER=0
echo "════════════════════════════════════════"
echo " Extraktor — HEALTH-CHECK"
echo "════════════════════════════════════════"
echo
if [ -x .venv/bin/python ]; then echo "✓ venv .............. vorhanden"
else echo "✗ venv .............. fehlt (./setup.sh)"; FEHLER=1; fi

for f in scripts/upsert.py scripts/extractor_gate.py SKILL.md README.md; do
    if [ -f "$f" ]; then echo "✓ Datei ............. $f"
    else echo "✗ Datei ............. $f FEHLT"; FEHLER=1; fi
done

if [ -x .venv/bin/python ]; then
    T=$(timeout 120 .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1)
    case "$T" in *failed*|*error*) echo "✗ Tests ............. $T"; FEHLER=1;; *passed*) echo "✓ Tests ............. $T";; *) echo "? Tests ............. $T";; esac
fi

URL="${QDRANT_URL:-http://127.0.0.1:6335}"
if curl -s -m 3 "$URL/collections" >/dev/null 2>&1; then echo "✓ Qdrant ............ $URL erreichbar"
else echo "! Qdrant ............ $URL nicht erreichbar"; fi

if [ -z "$(git status --short 2>/dev/null)" ]; then echo "✓ Git ............... sauber"
else echo "! Git ............... $(git status --short | wc -l) Änderungen"; fi

echo
[ "$FEHLER" -eq 0 ] && echo "ERGEBNIS: ✓ alles in Ordnung" || echo "ERGEBNIS: ✗ $FEHLER Problem(e)"
echo "════════════════════════════════════════"
exit "$FEHLER"
