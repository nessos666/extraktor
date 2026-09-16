# Extraktor — Session-Wissen in Qdrant

[![skills.sh](https://skills.sh/b/nessos666/extraktor)](https://skills.sh/nessos666/extraktor)

Ein Chat mit einem KI-Agenten produziert Wissen: Bugfixes, Entscheidungen, Zahlen,
Regeln. Beim Löschen der Session ist es weg. Der Extraktor holt es vorher raus
und legt es dauerhaft ab.

Nach dem Lauf kann die Session gelöscht werden, das Wissen bleibt.

Läuft lokal gegen Qdrant. Keine Cloud, keine API-Keys.

## Was genau gespeichert wird

Die Erkenntnisse werden in sieben Kategorien sortiert und je nach Art
unterschiedlich abgelegt:

| Kategorie | Beispiel | Ziel |
|---|---|---|
| **Technik / Tools** | „Tests dürfen `.venv/bin/python` nicht hartkodieren — im CI-Runner gibt es kein venv" | Qdrant `knowledge_nuggets` |
| **Fakten / Metriken** | „148 Quellen, 157 Tests, 10 geparkt" | Qdrant `knowledge_nuggets` |
| **Forschung** | „OpenAlex liefert 429, Budget aufgebraucht — CrossRef als Primärquelle" | Qdrant `research-papers` |
| **Projekte** | „Wissenschafts-Tool V4.1, Repo public, CI grün" | Qdrant `active_projects` |
| **Regeln** (nur kurze) | „Fremde Cron-Jobs nie anfassen" | Living Memory |
| **Präferenzen** (nur kurze) | „David: Belege statt Lob" | Living Memory |
| **Trading** | Strategie-Entscheidungen, Backtest-Zahlen | Qdrant `knowledge_nuggets` (Kategorie TRADING) |

**Grundregel:** Living Memory ist ein Regel-Cache, kein Archiv. Nur kurze
persönliche Regeln (unter ~150 Zeichen) landen dort. Alles andere geht nach Qdrant,
weil das Gedächtnis des Agenten begrenzt ist und nicht mit Inhalten zugestellt
werden darf.

## Installation

```bash
git clone https://github.com/nessos666/extraktor.git
cd extraktor
./setup.sh
```

Voraussetzung: Python 3.10+, ein laufender Qdrant auf Port 6335 (oder eine
andere URL per `QDRANT_URL`).

## Nutzung

Der Extraktor läuft in zwei Schritten: erst wird das Wissen aus dem Gespräch
gezogen, dann geschrieben.

**1. Erkenntnisse als JSON vorbereiten**

```json
[
  {"collection": "knowledge_nuggets", "category": "TECHNIK",
   "text": "Tests duerfen .venv/bin/python nicht hartkodieren, im CI-Runner fehlt es."},
  {"collection": "active_projects", "category": "PROJEKT",
   "text": "Wissenschafts-Tool V4.1 mit 148 Quellen, Repo public, CI gruen."}
]
```

**2. Schreiben**

```bash
cat erkenntnisse.json | python3 scripts/upsert.py
cat erkenntnisse.json | python3 scripts/upsert.py --gate      # mit Qualitaetspruefung
cat erkenntnisse.json | python3 scripts/upsert.py --dry-run   # nur anzeigen
```

Ausgabe pro Eintrag: `STORE`, `SKIP` (Duplikat) oder `DISCARD` (Qualität zu
schwach), am Ende eine Summe.

## Das Gate — Qualitätsprüfung vor dem Schreiben

`scripts/extractor_gate.py` prüft jeden Nugget, bevor er in die Datenbank kommt.
Ohne diese Prüfung sammelt sich Beliebiges an, und die Suche liefert später
Müll.

Fünf Gates, zwei davon Pflicht:

| Gate | Prüft | Pflicht |
|---|---|---|
| `substanz` | lang genug, um Inhalt zu haben | **ja** |
| `konkretheit` | Zahl, Pfad, Akronym oder Dateiname enthalten | **ja** |
| `kein_weichmacher` | kein „vielleicht", „könnte", „eventuell" | nein |
| `laenge_ok` | Nuggets sind Chunks, keine Aufsätze | nein |
| `keine_fuellphrase` | kein „hier ist", „ich habe" | nein |

Ergebnis:

| Entscheidung | Bedeutung |
|---|---|
| `qdrant` | speichern (mindestens 4 Gates, Typ-Score ≥ 0.5) |
| `session_db` | zu schwach für die Dauerablage, nur temporär |
| `discard` | verwerfen |

Ein Typ-Score gewichtet zusätzlich nach Art der Erkenntnis: eine Strategie oder
Architektur-Entscheidung ist mehr wert als ein allgemeiner Begriff. Formulierungen
wie „immer", „nie", „gemessen" heben den Score, Weichmacher senken ihn.

Einzeln ausprobieren:

```bash
python3 scripts/extractor_gate.py "Der Fix war sys.executable statt .venv/bin/python."
python3 scripts/extractor_gate.py "Vielleicht ist das irgendwie so"
```

## Dateien

| Datei | Zweck |
|---|---|
| `SKILL.md` | Anleitung für den Agenten (`/exstraktor` in Hermes) |
| `scripts/upsert.py` | schreibt nach Qdrant, mit Dedup |
| `scripts/extractor_gate.py` | Qualitätsprüfung vor dem Schreiben |
| `tests/` | Tests für das Gate |
| `check.sh` | Health-Check |
| `setup.sh` | Einrichtung |

## Konfiguration

| Variable | Standard | Zweck |
|---|---|---|
| `QDRANT_URL` | `http://127.0.0.1:6335` | Adresse der Datenbank |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | Embedding-Modell (384 Dimensionen) |
| `DUP_THRESHOLD` | `0.85` | ab welcher Ähnlichkeit ein Nugget als Duplikat gilt |

**Wichtig bei den Collections:** Alle Ziel-Collections müssen mit 384 Dimensionen
angelegt sein (passend zu `all-MiniLM-L6-v2`). Eine Collection mit anderer
Dimension führt zu einem Fehler; der Extraktor überspringt sie und macht mit den
übrigen weiter.

## Dedup

Vor jedem Schreiben wird die Ähnlichkeit gegen bestehende Punkte geprüft. Ab
`DUP_THRESHOLD` gilt der Nugget als Duplikat und wird übersprungen. Das verhindert,
dass dasselbe Wissen in zehn Sessions zehnmal landet.

## Grenzen

- Das Tool schreibt nur. Die Auswahl, was ein Nugget ist, trifft der Agent
  (oder du) — dafür gibt es keine Automatik.
- Es prüft nicht, ob ein Nugget inhaltlich **wahr** ist, nur ob er konkret und
  wohlgeformt ist.
- Ohne laufenden Qdrant passiert nichts. Der Aufruf scheitert mit einer
  Verbindungsfehlermeldung.

## Lizenz

MIT.
