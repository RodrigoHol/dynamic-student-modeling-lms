"""Registro declarativo y autodetección de formatos de `SourceParser`."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from dsm_replayer.parsers.base import SourceParser, ensure_file_exists
from dsm_replayer.parsers.moodle_csv import MoodleCsvExportParser
from dsm_replayer.parsers.moodle_db import MoodleDbLogParser
from dsm_replayer.parsers.synthetic import SyntheticJsonlParser

PARSER_REGISTRY: dict[str, type[SourceParser]] = {
    "moodle_csv": MoodleCsvExportParser,
    "moodle_db": MoodleDbLogParser,
    "synthetic_jsonl": SyntheticJsonlParser,
}


def detect_format(file_path: str | Path) -> str:
    """Detecta el formato del dataset inspeccionando extensión, encabezados o primer registro."""
    path = ensure_file_exists(file_path)
    suffix = path.suffix.lower()

    if suffix in {".jsonl", ".ndjson"}:
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                if isinstance(obj, dict):
                    if "timecreated" in obj and "userid" in obj:
                        return "moodle_db"
                    if "raw_user_id" in obj:
                        return "synthetic_jsonl"
                break
        return "synthetic_jsonl"

    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            headers = next(reader, [])
            lowered = {h.strip().lower() for h in headers}
            if {"timecreated", "userid", "eventname"}.issubset(lowered) or "timecreated" in lowered:
                return "moodle_db"
            if "hora" in lowered or "time" in lowered:
                return "moodle_csv"
            raise ValueError(f"No se pudo detectar el formato CSV de {path}: encabezados={headers}")

    raise ValueError(f"Extensión no soportada para autodetección: {path.suffix}")


def create_parser(fmt: str, *, course_id: str | None = None) -> SourceParser:
    """Instancia el parser registrado para `fmt`."""
    if fmt not in PARSER_REGISTRY:
        supported = ", ".join(sorted(PARSER_REGISTRY))
        raise ValueError(f"Formato no soportado '{fmt}'. Opciones válidas: {supported}")

    parser_cls = PARSER_REGISTRY[fmt]
    if parser_cls in (MoodleCsvExportParser, MoodleDbLogParser) and course_id is not None:
        return parser_cls(default_course_id=course_id)
    return parser_cls()
