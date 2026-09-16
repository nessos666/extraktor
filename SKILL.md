---
name: exstraktor
description: "/skill exstraktor — Extrahiert Wissen aus der aktuellen Session nach Qdrant, Living Memory und MODEL_CARDs. Session kann danach gefahrlos gelöscht werden."
version: 1.0.0
author: David/Hermes
category: hermes-brain-architecture
metadata:
  hermes:
    tags: [session, wissen, extraktion, qdrant, memory]
---

# Session-Wissen-Extraktor (/exstraktor)

Extrahiert strukturiertes Wissen aus der aktuellen Chat-Session und speichert es in den richtigen Wissensspeichern. Nach Extraktion kann die Session gelöscht werden — das Wissen bleibt erhalten.

## Trigger
- `/exstraktor` (Slash-Command)
- `extrahier wissen`, `session auswerten`, `wissen speichern`, `session extrahieren`

## Pipeline (5 Schritte)

### Schritt 1: Session-Inhalt laden
- Session-ID aus Kontext ermitteln
- Vollständigen Session-Verlauf mit `session_search(session_id=..., profile="default")` laden
- Wenn aktuelle Session: nur diese laden

### Schritt 2: Wissen extrahieren (LLM-Analyse)
Analysiere den Session-Verlauf und extrahiere strukturiert:

```
KATEGORIEN:
- TRADING: Strategie-Entscheidungen, Modell-Performance, Backtest-Ergebnisse, Markt-Erkenntnisse
- FORSCHUNG: Neue Erkenntnisse, Paper-Insights, Methodik-Verbesserungen
- TECHNIK/TOOLS: Bug-Fixes, Tool-Konfiguration, Code-Muster, API-Erkenntnisse  
- PROJEKTE: Projekt-Status, Meilensteine, Entscheidungen
- REGELN: Neue Arbeitsregeln, Präferenzen, "Immer/Niemals"-Aussagen
- FAKTEN: Metriken, Zahlen, Datenpunkte
- DAVID: Persönliche Präferenzen, Arbeitsweise, Entscheidungen
```

### Schritt 3: Einsortieren (Brain Router)

| Kategorie | Ziel | Aktion |
|-----------|------|--------|
| TRADING | Qdrant Port 6335 | Collection `trading-research` |
| FORSCHUNG | Qdrant Port 6335 | Collection `research-papers` |
| TECHNIK/TOOLS | Qdrant Port 6335 | Collection `knowledge_nuggets` |
| FAKTEN/Metriken | Qdrant Port 6335 | Collection `knowledge_nuggets` |
| PROJEKTE | Qdrant Port 6335 + MODEL_CARD | Collection `active_projects` + MODEL_CARD updaten |
| REGELN (nur max 150 Zeichen) | Living Memory | `memory` tool, target='memory' |
| DAVID (nur max 150 Zeichen) | Living Memory | `memory` tool, target='memory' |

> ⚠️ **Dimensions-Hinweis (2026-08):** Collection `trading-research` ist **32-dim** (anderes Embedding-Modell), all-MiniLM-L6-v2 liefert **384-dim** → schlägt mit 400 fehl. TRADING-Erkenntnisse deshalb nach `knowledge_nuggets` (category="TRADING") schreiben, bis das 32-dim-Modell identifiziert ist. `active_projects`, `research-papers`, `knowledge_nuggets` sind 384-dim und funktionieren mit all-MiniLM-L6-v2.

**GRUNDREGEL: NUR persönliche Regeln/David-Präferenzen (<150 Zeichen) in Living Memory. ALLES andere → Qdrant. Living Memory ist kein Archiv, sondern ein schneller Regel-Cache.**

### Schritt 4: Vektorisieren & Speichern
- Jede extrahierte Erkenntnis als Chunk vektorisieren (all-MiniLM-L6-v2, 384dim)
- In entsprechende Qdrant-Collection indexieren
- Living Memory Facts anlegen (max 200 Zeichen pro Fakt)

### Schritt 5: Zusammenfassung + Lösch-Angebot
- Zusammenfassung ausgeben: X Erkenntnisse → Qdrant, Y Fakten → Memory, Z Updates → MODEL_CARDs
- Optional: Session löschen mit `hermes sessions delete <id>`

## Wichtige Regeln
- **Living Memory ist NUR für kurze Regeln/David-Präferenzen (<150 Zeichen)** — kein Archiv!
- **ALLES andere → Qdrant** (Port 6335, Collections: knowledge_nuggets, trading-research, research-papers, active_projects)
- **NIE Fakten doppelt speichern** — vorher Qdrant Similarity Search
- **NIE vage Aussagen als Fakten** — nur konkrete Metriken, Regeln, Entscheidungen
- **Keine Cron-Sessions extrahieren** — nur User-Sessions (kein `cron_` Prefix)

## Speicherorte
- Qdrant (PRIMÄR): Port 6335
- Living Memory (NUR Regeln): `~/.hermes/memory_store.db`
- MODEL_CARDs: `~/BRAIN_LIBRARY/<project>/MODEL_CARD.md`
- Extraktions-Log: `~/HAUPTLAGER/07_SYSTEM/33_System_Reports/extraction_log.md`
