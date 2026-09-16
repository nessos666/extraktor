#!/usr/bin/env python3
"""upsert — schreibt extrahierte Erkenntnisse nach Qdrant.

Liest JSON von stdin:
    [{"collection": "knowledge_nuggets", "category": "TECHNIK", "text": "..."}, ...]

Dedup: vor dem Schreiben wird die Aehnlichkeit gegen bestehende Punkte geprueft.
Ab einem Score von DUP_THRESHOLD gilt der Nugget als Duplikat und wird uebersprungen.

Optionen (Umgebungsvariablen):
    QDRANT_URL      default http://127.0.0.1:6335
    EMBED_MODEL     default all-MiniLM-L6-v2
    DUP_THRESHOLD   default 0.85

Optionen (Kommandozeile):
    --gate          jeden Nugget vorher durch ExtractorGate schicken
    --dry-run       nichts schreiben, nur anzeigen was passieren wuerde
    --url URL       Qdrant-URL ueberschreiben
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6335")
MODEL_NAME = os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2")
DUP_THRESHOLD = float(os.environ.get("DUP_THRESHOLD", "0.85"))


def main() -> int:
    args = sys.argv[1:]
    nutze_gate = "--gate" in args
    dry_run = "--dry-run" in args
    url = QDRANT_URL
    if "--url" in args:
        url = args[args.index("--url") + 1]

    roh = sys.stdin.read()
    if not roh.strip():
        print("Keine Eingabe auf stdin. Erwartet: JSON-Liste.", file=sys.stderr)
        return 1
    try:
        items = json.loads(roh)
    except json.JSONDecodeError as e:
        print(f"Ungueltiges JSON: {e}", file=sys.stderr)
        return 1
    if not isinstance(items, list):
        print("Erwartet wird eine JSON-Liste.", file=sys.stderr)
        return 1

    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient

    gate = None
    if nutze_gate:
        try:
            from extractor_gate import ExtractorGate
            gate = ExtractorGate()
        except ImportError:
            print("Hinweis: extractor_gate.py nicht gefunden — Gate uebersprungen.",
                  file=sys.stderr)

    model = SentenceTransformer(MODEL_NAME)
    client = None if dry_run else QdrantClient(url=url)

    gespeichert = uebersprungen = verworfen = fehler = 0

    for item in items:
        col = item.get("collection", "knowledge_nuggets")
        text = item.get("text", "")
        if not text.strip():
            verworfen += 1
            continue

        # Optional: Qualitaetspruefung vor dem Schreiben
        if gate is not None:
            entscheidung = gate.process(text, topic=item.get("topic", ""),
                                        domain=item.get("category", ""))
            if entscheidung["store"] == "discard":
                print(f"DISCARD [{col}] score={entscheidung['score']:.2f} :: {text[:60]}...")
                verworfen += 1
                continue

        try:
            vec = model.encode(text).tolist()

            if dry_run:
                print(f"WOULD STORE [{col}] :: {text[:70]}...")
                gespeichert += 1
                continue

            res = client.query_points(collection_name=col, query=vec, limit=3)
            top_sim = res.points[0].score if res.points else 0.0

            if top_sim >= DUP_THRESHOLD:
                print(f"SKIP  [{col}] sim={top_sim:.3f} :: {text[:70]}...")
                uebersprungen += 1
                continue

            client.upsert(
                collection_name=col,
                points=[{
                    "id": str(uuid.uuid4()),
                    "vector": vec,
                    "payload": {
                        "text": text,
                        "category": item.get("category", "knowledge"),
                        "source": item.get("source", "extraktor"),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                    },
                }],
            )
            print(f"STORE [{col}] sim={top_sim:.3f} :: {text[:70]}...")
            gespeichert += 1
        except Exception as e:
            # Ein Dimensions-Mismatch (z.B. 32-dim Collection) darf den Rest nicht stoppen
            print(f"ERROR [{col}] :: {text[:60]}... -> {e}")
            fehler += 1

    print(f"\n=== extraktor: {gespeichert} gespeichert, {uebersprungen} Duplikate, "
          f"{verworfen} verworfen, {fehler} Fehler ===")
    return 0 if fehler == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
