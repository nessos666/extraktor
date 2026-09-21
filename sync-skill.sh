#!/usr/bin/env bash
# Stellt den /exstraktor-Hermes-Skill aus diesem Repo her.
#
# Nutzung:  ./sync-skill.sh
#
# Der Skill liegt in ~/.hermes/skills/exstraktor/ und wird beim Speichern
# eines Chats gebraucht. Nach einem 'hermes update' kann er fehlen.
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
ZIEL="$HOME/.hermes/skills/exstraktor"

if [ ! -f "$REPO/SKILL.md" ]; then
    echo "FEHLER: $REPO/SKILL.md fehlt" >&2; exit 1
fi

mkdir -p "$ZIEL/scripts"
cp "$REPO/SKILL.md" "$ZIEL/SKILL.md"
cp "$REPO/scripts/upsert.py" "$ZIEL/scripts/upsert.py"
cp "$REPO/scripts/extractor_gate.py" "$ZIEL/scripts/extractor_gate.py"
cp "$REPO/scripts/memory_kandidaten.py" "$ZIEL/scripts/memory_kandidaten.py"
rm -rf "$ZIEL/scripts/__pycache__"

echo "✓ Skill wiederhergestellt: $ZIEL"
echo "  (Hermes-Session neu starten, damit /exstraktor die neue Fassung laedt)"
