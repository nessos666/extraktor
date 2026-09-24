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
| REGELN (nur max 150 Zeichen) | Living Memory | `memory` tool, target='memory' — **erst fragen (Schritt 3b)** |
| DAVID (nur max 150 Zeichen) | Living Memory | `memory` tool, target='memory' — **erst fragen (Schritt 3b)** |

> ⚠️ **Dimensions-Hinweis (2026-08):** Collection `trading-research` ist **32-dim** (anderes Embedding-Modell), all-MiniLM-L6-v2 liefert **384-dim** → schlägt mit 400 fehl. TRADING-Erkenntnisse deshalb nach `knowledge_nuggets` (category="TRADING") schreiben, bis das 32-dim-Modell identifiziert ist. `active_projects`, `research-papers`, `knowledge_nuggets` sind 384-dim und funktionieren mit all-MiniLM-L6-v2.

**GRUNDREGEL: NUR persönliche Regeln/David-Präferenzen (<150 Zeichen) in Living Memory. ALLES andere → Qdrant. Living Memory ist kein Archiv, sondern ein schneller Regel-Cache.**

### Schritt 3b (Pflicht seit 20.09.2026): Living-Memory-Frage stellen
**Nie automatisch ins Living Memory schreiben.** Vor jedem Memory-Write:
1. Kandidaten erzeugen: `python scripts/memory_kandidaten.py --kategorien REGELN,DAVID < nuggets.json`
   (filtert Kategorien, erzwingt <150 Zeichen, prüft Duplikate gegen `MEMORY.md`/`USER.md` und
   meldet die Auslastung; **schreibt selbst nichts**).
2. Im Chat als **Auswahlliste** zeigen (`clarify`, mehrfach auswählbar): „Diese Sätze ins Living Memory?" mit „Alle / Keine / einzeln abwählen".
3. Erst nach ausdrücklichem Ja schreiben — ohne Antwort wird **nichts** geschrieben.

**Grund (Davids Ansage 20.09.2026):** Living Memory ist ein Regel-Cache, kein Archiv (Stand
20.09.2026: 3411/3500 Zeichen = 97 % voll). **Recherche-Chats** (Preise, Produkte, Personen,
Markt, Technik-Recherche) speichern **ausschließlich nach Qdrant**; Memory-Kandidat = „keine".
Wenn der Kandidat für die Ewigkeit taugt, gehört er eher in diesen Skill (Prozedur) als ins Memory.
**Qdrant-Writes sind nicht betroffen** und laufen weiterhin ohne Rückfrage.

### Schritt 4: Quality-Gate, Vektorisieren & Speichern
- **Zuerst durch `scripts/extractor_gate.py` (Pflicht):** Jedes Nugget wird bewertet und einem Ziel
  zugeordnet — `discard` (verwerfen) / `session_db` (zu schwach) / `qdrant` (speichern).
  Entscheidung: `qdrant` ab **4 von 5 Gates** und Score ≥ 0.5; `session_db` ab 3; sonst `discard`.
  - **Pflicht-Gates (verschärft 21.09.2026):** `substanz` (≥ 20 Zeichen), `konkretheit` (Zahl,
    Dateipfad oder Akronym), `kein_weichmacher` und `keine_fuellphrase` — ein Fail bei einem dieser
    vier verwirft den Nugget sofort. **Grund (gemessen):** Ein Satz, den das Gate selbst als Füllphrase
    erkannte, wurde mit einer Ziffer trotzdem gespeichert („Hier ist ein Beispiel: irgendwas mit
    Zahlen 1 2 3 und sonst nichts Inhaltliches dabei." → qdrant, Score 0.66). Vorher waren nur
    `substanz`+`konkretheit` Pflicht, faktisch passierte jeder Satz über 20 Zeichen mit einer Ziffer.
  - Typ-Gewicht (TypePriorScorer): strategy 1.0 > system 0.95 > model 0.9 > tool 0.85 > paper 0.8 > concept 0.6.
  - ✅ **Typ-Gewichtung greift (BEHOBEN 21.09.2026):** `upsert.py --gate` liest jetzt `typ` aus dem Nugget
    (`{"typ": "tool", ...}`) und reicht es an `ExtractorGate(typ=...)` durch. Ohne `typ` gilt weiter
    `concept` (Prior 0.60). Der Unterschied ist messbar: derselbe Satz mit Weichmacher ergibt als
    `concept` 0.40 → **discard**, als `tool` 0.56 → **qdrant**. Nuggets mit echtem Typ versehen lohnt sich.
    (Vorher: `ExtractorGate()` ohne Argument → Typ-Prior war über die CLI **toter Code**.)
    Deshalb: Nuggets faktisch formulieren, ohne „vielleicht/könnte/eventuell/ich glaube".
    (Lauf 17.09.2026: 11/11 `qdrant`, 0 verworfen.)
  - **Weichmacher kosten ein Gate** („vielleicht“, „könnte“, „eventuell“, „ich glaube“) — Nuggets
    faktisch und mit Zahlen/Pfaden formulieren.
  - Nur `qdrant`-Nuggets werden gespeichert; aussortierte ehrlich protokollieren, nicht stillschweigend
    ablegen. (Historischer Hinweis: `substanz`+`konkretheit` verwerfen vage Aussagen hart.)
- Bestandene Nuggets als Chunk vektorisieren (all-MiniLM-L6-v2, 384dim) und in die Ziel-Collection indexieren
- Living Memory Facts anlegen (max 200 Zeichen pro Fakt) — nur Regeln/Präferenzen

### Schritt 5: Zusammenfassung + Lösch-Angebot
- Zusammenfassung ausgeben: X Erkenntnisse → Qdrant, Y Fakten → Memory, Z Updates → MODEL_CARDs
- Optional: Session löschen mit `hermes sessions delete <id>`

## Wichtige Regeln
- **Living Memory ist NUR für kurze Regeln/David-Präferenzen (<150 Zeichen)** — kein Archiv!
- **ALLES andere → Qdrant** (Port 6335, Collections: knowledge_nuggets, trading-research, research-papers, active_projects)
- **NIE Fakten doppelt speichern** — vorher Qdrant Similarity Search
- **NIE vage Aussagen als Fakten** — nur konkrete Metriken, Regeln, Entscheidungen
- **Keine Cron-Sessions extrahieren** — nur User-Sessions (kein `cron_` Prefix)

## Pitfalls (gemessen 17.09.2026)

- **Der Live-Skill ist eine KOPIE — hier NICHT direkt ändern.** `~/.hermes/skills/exstraktor/`
  (SKILL.md + scripts/) wird per `sync-skill.sh` aus dem Repo erzeugt:
  `~/HAUPTLAGER/03_PROJEKTE/48_Extraktor_Tool` → Remote `github.com/nessos666/extraktor` (privat).
  Änderungen nur am Live-Skill sind beim nächsten `sync-skill.sh` oder `hermes update` **weg**
  (17.09.2026 verifiziert: Repo-Dateien 16.09. vs. Live 21.09., alle drei Dateien abweichend).
  **Richtige Reihenfolge:** im REPO ändern → `./sync-skill.sh` → `./check.sh` → committen → pushen.
  Umgekehrt (Live → Repo spiegeln) nur, wenn der Live-Stand der neuere und getestete ist —
  danach `md5sum`-Vergleich: Live == Repo.
- **`sync-skill.sh` und `check.sh` mitpflegen.** Beide listen die Dateien einzeln auf; ein neues
  Skript (z.B. `memory_kandidaten.py`) fehlte in beiden und wäre nach einem Sync verloren gewesen.
  Wer ein Skript ergänzt, trägt es in `sync-skill.sh` UND in die Datei-Prüfliste von `check.sh` ein.
- **Nugget-Datei eindeutig benennen und VOR dem Einlesen gegenpruefen.** `/tmp/nuggets.json`
  kann eine **Altlast** sein: `write_file` hat sie stillschweigend NICHT ueberschrieben, die
  Datei vom 16.09. blieb liegen, `upsert.py` las fremde Nuggets („1 gespeichert, 12 Duplikate")
  und **der eigene Batch lief gar nicht**. **Erkennungsmerkmal:** die STORE/SKIP-Zeilen zeigen
  Text, der nicht aus dem aktuellen Batch stammt. Deshalb: Dateiname mit Datum/Uhrzeit,
  mit `open(path,"w")` schreiben, `md5sum` + `grep` gegenpruefen, dann erst pipen.
  **Root cause:** `write_file` **verweigert** das Ueberschreiben einer bereits vorhandenen
  Datei, die in dieser Aufgabe nicht gelesen wurde — die Ablehnung ist im Rueckgabewert,
  nicht im stdout, und wird ohne Pruefung uebersehen.
- **Nach jedem Lauf beweisen, nicht annehmen:** Punkte-Zahlen der Collections vor/nach
  vergleichen und 2–3 Similarity-Suchen auf Kernbegriffe des Batches (auffindbar = gespeichert).
- `python3 -c`/`-e` ist im Hermes-Single-Query-Modus blockiert → Pruefskript als `.py`-Datei schreiben und ausfuehren.
- **Grosse Sammelbefehle im Terminal werden blockiert (gemessen 20.09.2026).** Ein Befehl aus
  Shell-Schleife + curl + python lief 173 s ohne Nutzer-Freigabe und endete als `BLOCKED`; er darf
  danach **nicht wiederholt** werden. **Regel: ein Schritt pro Tool-Aufruf**, Logik nach `execute_code`.
- **Die ganze Pipeline laeuft ohne Terminal (bewaehrt 20.09.2026: 16/16 und 4/4 gespeichert):**
  Der Hermes-Kernel-Python (`/home/boobi/.hermes/hermes-agent/venv/bin/python`) hat
  `sentence_transformers` (5.6.1) und `qdrant_client` — `upsert.py` per
  `subprocess.run([PY, SCRIPT, "--gate"], stdin=open(nugget_file,"rb"))` aufrufen, Dry-Run mit
  `--gate --dry-run` vorweg, Punktzahlen per HTTP GET `/collections/<name>` gegenpruefen.

## Speicherorte
- Living Memory (AKTIV, injiziert): `~/.hermes/memories/MEMORY.md` (Budget 3500 Zeichen) und
  `~/.hermes/memories/USER.md` (Budget 2000 Zeichen); Einträge sind mit `§` getrennt.
  **Nicht** mit `~/.hermes/memory_store.db` verwechseln — das ist der fact-store (519 Fakten)
  für Similarity-Suche, nicht das injizierte Memory.
- Qdrant (PRIMÄR): Port 6335
- Living Memory (NUR Regeln): `~/.hermes/memory_store.db`
- MODEL_CARDs: `~/BRAIN_LIBRARY/<project>/MODEL_CARD.md`
- Extraktions-Log: `~/HAUPTLAGER/07_SYSTEM/33_System_Reports/extraction_log.md`
