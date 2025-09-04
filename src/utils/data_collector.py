"""
Data Collector
==============
Sammelt beliebige `data`-Objekte (Python-Dicts), extrahiert konfigurierte Spalten
über JSON-Pfade und schreibt eine CSV-Datei.

Features
--------
- Spaltenkonfiguration als **Liste von JSON-Pfaden** (Dot-Notation), z. B.:
  [
    "meta.from",
    "meta.subject",
    "ai_email_parser.body_window",
    "ai_email_parser.signature.full_name",
    "spacy_ner_entities[*].label",          # Wildcard über Listen
    "spacy_ner_entities[0].text",           # Index-Zugriff
  ]
- Unterstützt `[*]` (alle Elemente; werden per Separator zusammengeführt) und
  `[N]` (0-basierter Index) in jedem Pfadsegment.
- Listenwerte werden standardmäßig zu einem String **zusammengeführt**.
- Sichere Extraktion: fehlende Keys ergeben leere Strings.

Public API
----------
- collect_records(records) -> list[dict]
- extract_rows(records, columns, join_sep=" | ") -> list[dict]
- write_csv(rows, headers, output_csv, encoding="utf-8-sig") -> None
- collect_and_write(records, columns, output_csv, join_sep=" | ") -> None

Hinweis: *records* ist ein Iterable von Dicts (z. B. die Pipeline-`data` Objekte).
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple
import csv
import json

# -----------------------------
# JSON-Pfad Utilities
# -----------------------------

def _tokenize(path: str) -> List[Tuple[str, str | None]]:
    """Zerlegt einen Pfad wie "a.b[0].c[*]" in Tokens.
    Rückgabe: Liste von (key, index) mit index in {None, "*", "0", ...}
    """
    tokens: List[Tuple[str, str | None]] = []
    for raw in path.split('.'):
        key = raw
        idx: str | None = None
        if '[' in raw and raw.endswith(']'):
            key, bracket = raw.split('[', 1)
            idx = bracket[:-1]  # ohne schließende Klammer
        tokens.append((key, idx))
    return tokens


def _is_primitive(x: Any) -> bool:
    return isinstance(x, (str, int, float, bool)) or x is None


def _stringify(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if _is_primitive(x):
        return str(x)
    # Für Dicts/Listen als JSON serialisieren
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)


def _descend(values: List[Any], key: str) -> List[Any]:
    out: List[Any] = []
    for v in values:
        if isinstance(v, dict) and key in v:
            out.append(v[key])
        else:
            out.append(None)
    return out


def _apply_index(values: List[Any], idx: str | None) -> List[Any]:
    if idx is None:
        return values
    out: List[Any] = []
    if idx == '*':
        for v in values:
            if isinstance(v, list):
                out.extend(v)
            else:
                out.append(v)
        return out
    # numerischer Index
    try:
        i = int(idx)
    except Exception:
        return values
    for v in values:
        if isinstance(v, list) and 0 <= i < len(v):
            out.append(v[i])
        else:
            out.append(None)
    return out


def get_values_by_path(obj: Dict[str, Any], path: str) -> List[Any]:
    """Gibt **alle** Werte für einen JSON-Pfad zurück (Liste),
    unter Berücksichtigung von [*] und [N].
    """
    tokens = _tokenize(path)
    current: List[Any] = [obj]
    for key, idx in tokens:
        current = _descend(current, key)
        current = _apply_index(current, idx)
    return current


def get_value_by_path_joined(obj: Dict[str, Any], path: str, join_sep: str = " | ") -> str:
    """Wie get_values_by_path, aber als **String** zusammengeführt.
    - Filtert None heraus
    - Stringifiziert Nicht-Primitives
    - Führt Mehrfachwerte mit join_sep zusammen
    """
    vals = [v for v in get_values_by_path(obj, path) if v is not None]
    if not vals:
        return ""
    if len(vals) == 1 and _is_primitive(vals[0]):
        return _stringify(vals[0])
    # Falls noch Listen übrig sind, flach machen
    flat: List[Any] = []
    for v in vals:
        if isinstance(v, list):
            flat.extend(v)
        else:
            flat.append(v)
    return join_sep.join(_stringify(x) for x in flat if x is not None)


# -----------------------------
# Collector / CSV Writer
# -----------------------------

def collect_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sammelt alle Dict-Objekte in eine Liste (Materialisierung eines Iterables)."""
    return list(records)


def _normalize_columns(columns: Sequence[str] | Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Erlaubt entweder
    - Liste von Pfaden → Header = Pfad
    - Dict {Header: Pfad}
    Liefert (headers, paths).
    """
    if isinstance(columns, dict):
        headers = list(columns.keys())
        paths = [columns[h] for h in headers]
        return headers, paths
    headers = list(columns)
    paths = list(columns)
    return headers, paths


def extract_rows(records: Iterable[Dict[str, Any]], columns: Sequence[str] | Dict[str, str], *, join_sep: str = " | ") -> List[Dict[str, str]]:
    """Extrahiert Zeilen entsprechend der Spaltenkonfiguration.
    columns: Liste von JSON-Pfaden **oder** Dict {Header: Pfad}
    Rückgabe: Liste von Zeilen-Dicts {Header: Wert-als-String}
    """
    headers, paths = _normalize_columns(columns)
    rows: List[Dict[str, str]] = []
    for obj in records:
        row: Dict[str, str] = {}
        for h, p in zip(headers, paths):
            row[h] = get_value_by_path_joined(obj, p, join_sep=join_sep)
        rows.append(row)
    return rows


def write_csv(rows: Iterable[Dict[str, str]], headers: Sequence[str], output_csv: str, *, encoding: str = "utf-8-sig") -> None:
    """Schreibt eine CSV mit den gegebenen Headern.
    - encoding `utf-8-sig` sorgt dafür, dass Excel die Datei als UTF‑8 erkennt.
    """
    with open(output_csv, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=list(headers))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def collect_and_write(records: Iterable[Dict[str, Any]], columns: Sequence[str] | Dict[str, str], output_csv: str, *, join_sep: str = " | ") -> None:
    """Convenience: Records sammeln → Zeilen extrahieren → CSV schreiben."""
    recs = collect_records(records)
    rows = extract_rows(recs, columns, join_sep=join_sep)
    headers, _ = _normalize_columns(columns)
    write_csv(rows, headers, output_csv)


# -----------------------------
# Mini-CLI (optional)
# -----------------------------
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Collect data dicts and export CSV via JSON paths.")
    parser.add_argument("output", help="Pfad zur Ausgabe-CSV")
    parser.add_argument("--columns", "-c", nargs=",", required=True,
                        help="Kommagetrennte JSON-Pfade für Spalten (z. B. meta.from,ai_email_parser.body_window)")
    parser.add_argument("--jsonl", help="Optional: Pfad zu einer JSONL-Datei (ein Objekt pro Zeile)")
    parser.add_argument("--sep", default=" | ", help="Separator zum Joinen von Listenwerten (Default: ' | ')")

    args = parser.parse_args()

    # Quellen laden
    records_in: List[Dict[str, Any]] = []
    if args.jsonl:
        with open(args.jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records_in.append(json.loads(line))
                except Exception:
                    print("WARN: Konnte Zeile nicht als JSON parsen", file=sys.stderr)

    columns = [c for c in (args.columns or []) if c]
    rows = extract_rows(records_in, columns, join_sep=args.sep)
    write_csv(rows, headers=columns, output_csv=args.output)
    print(f"CSV geschrieben: {args.output}  (Zeilen: {len(rows)})")
