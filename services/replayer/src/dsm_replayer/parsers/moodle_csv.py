from __future__ import annotations

import csv
import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

from dsm_common.schemas import EventMetadata, RawEventInput, ResourceInfo
from dsm_replayer.parsers.base import (
    SourceParser,
    ensure_file_exists,
    iter_chronological,
    parse_datetime_utc,
)

_MOODLE_TIME_FORMATS: tuple[str, ...] = (
    "%d/%m/%y, %H:%M:%S",
    "%d/%m/%Y, %H:%M:%S",
    "%d/%m/%y, %H:%M",
    "%d/%m/%Y, %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)

_COMPONENT_MAP: dict[str, str] = {
    "sistema": "core",
    "system": "core",
    "core": "core",
    "tarea": "mod_assign",
    "assignment": "mod_assign",
    "mod_assign": "mod_assign",
    "foro": "mod_forum",
    "forum": "mod_forum",
    "mod_forum": "mod_forum",
    "cuestionario": "mod_quiz",
    "quiz": "mod_quiz",
    "mod_quiz": "mod_quiz",
    "recurso": "mod_resource",
    "archivo": "mod_resource",
    "file": "mod_resource",
    "resource": "mod_resource",
    "mod_resource": "mod_resource",
    "url": "mod_url",
    "mod_url": "mod_url",
    "página": "mod_page",
    "pagina": "mod_page",
    "page": "mod_page",
    "mod_page": "mod_page",
    "carpeta": "mod_folder",
    "folder": "mod_folder",
    "mod_folder": "mod_folder",
    "informe del usuario": "gradereport_user",
    "user report": "gradereport_user",
    "calificaciones": "gradereport_user",
    "gradereport_user": "gradereport_user",
    "registros": "core",
    "logs": "core",
}

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "time": ("hora", "time"),
    "user": ("nombre completo del usuario", "user full name"),
    "affected_user": ("usuario afectado", "affected user"),
    "context": ("contexto del evento", "event context"),
    "component": ("componente", "component"),
    "event_name": ("nombre del evento", "event name"),
    "description": ("descripción", "descripcion", "description"),
    "origin": ("origen", "origin"),
    "ip": ("dirección ip", "direccion ip", "ip address"),
}

_USER_ID_RE = re.compile(r"(?:usuario|user)\s+(?:con|with)\s+id\s+'([^']+)'", re.IGNORECASE)
_CMID_RE = re.compile(
    r"(?:course module|m[oó]dulo del curso|actividad)\s+id\s+'([^']+)'", re.IGNORECASE
)
_GENERIC_ID_RE = re.compile(r"\bid\s+'([^']+)'", re.IGNORECASE)
_COURSE_ID_RE = re.compile(r"(?:curso|course)\s+(?:con\s+)?id\s+'([^']+)'", re.IGNORECASE)


def _slugify_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _pick_column(row_lower: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        if alias in row_lower:
            return row_lower[alias].strip()
    return ""


def _normalize_component(raw_component: str) -> str:
    cleaned = raw_component.strip().lower()
    if cleaned in _COMPONENT_MAP:
        return _COMPONENT_MAP[cleaned]
    if cleaned.startswith(("mod_", "core", "gradereport_")):
        return cleaned
    return re.sub(r"[^a-z0-9_]+", "_", cleaned).strip("_") or "unknown"


def _infer_action_target(
    event_name: str,
    description: str,
    component: str,
) -> tuple[str, str | None, str]:
    lowered = f"{event_name} {description}".lower()

    if (
        "log_report_viewed" in lowered
        or "informe de registro" in lowered
        or ("log report" in lowered and "viewed" in lowered)
    ):
        return "viewed", "log_report", "\\core\\event\\log_report_viewed"

    if "course_user_report_viewed" in lowered:
        return "viewed", "report", "\\core\\event\\course_user_report_viewed"

    target: str | None = None
    if any(tok in lowered for tok in ("calificaci", "grade report", "informe del usuario")):
        target = "grade"
    elif any(tok in lowered for tok in ("retroalimentaci", "feedback")):
        target = "feedback"
    elif any(tok in lowered for tok in ("curso visto", "course viewed")):
        target = "course"
    elif "módulo" in lowered or "modulo" in lowered or "course module" in lowered:
        target = "course_module"
    elif "intento" in lowered or "attempt" in lowered:
        target = "attempt"
    elif "entrega" in lowered or "submission" in lowered or "assessable" in lowered:
        target = "assessable"

    action = "viewed"
    if any(tok in lowered for tok in ("enviado", "enviada", "submitted")):
        action = "submitted"
    elif any(tok in lowered for tok in ("subido", "cargado", "uploaded")):
        action = "uploaded"
    elif any(tok in lowered for tok in ("iniciado", "comenzado", "started")):
        action = "started"
    elif any(tok in lowered for tok in ("revisado", "reviewed")):
        action = "reviewed"
    elif any(tok in lowered for tok in ("creado", "creada", "añadido", "created")):
        action = "created"
    elif any(tok in lowered for tok in ("actualizado", "actualizada", "modificado", "updated")):
        action = "updated"
    elif any(tok in lowered for tok in ("visto", "vista", "visualizado", "viewed")):
        action = "viewed"

    raw_eventname = event_name.strip() or f"\\{component}\\event\\{action}"
    return action, target, raw_eventname


class MoodleCsvExportParser(SourceParser):
    def __init__(self, default_course_id: str = "course_unknown") -> None:
        self._default_course_id = default_course_id

    @property
    def format_name(self) -> str:
        return "moodle_csv"

    def _parse_row(self, idx: int, row: dict[str | None, str | None]) -> RawEventInput | None:
        row_lower = {
            (k or "").strip().lower(): (v or "") for k, v in row.items() if k is not None
        }
        raw_time = _pick_column(row_lower, _COLUMN_ALIASES["time"])
        if not raw_time:
            return None

        timestamp = parse_datetime_utc(raw_time, _MOODLE_TIME_FORMATS)
        user_name = _pick_column(row_lower, _COLUMN_ALIASES["user"])
        description = _pick_column(row_lower, _COLUMN_ALIASES["description"])
        context = _pick_column(row_lower, _COLUMN_ALIASES["context"])
        raw_component = _pick_column(row_lower, _COLUMN_ALIASES["component"])
        event_name = _pick_column(row_lower, _COLUMN_ALIASES["event_name"])
        origin = _pick_column(row_lower, _COLUMN_ALIASES["origin"])

        user_match = _USER_ID_RE.search(description)
        raw_user_id = (
            user_match.group(1).strip()
            if user_match
            else (user_name if user_name and user_name != "-" else f"anon_{idx}")
        )

        component = _normalize_component(raw_component)
        action, target, raw_eventname = _infer_action_target(
            event_name=event_name,
            description=description,
            component=component,
        )

        cmid_match = _CMID_RE.search(description) or _GENERIC_ID_RE.search(description)
        resource_type = component.removeprefix("mod_")
        if cmid_match:
            resource_id = f"{resource_type}_{cmid_match.group(1).strip()}"
        else:
            resource_id = _slugify_id(resource_type, context or event_name or str(idx))

        course_match = _COURSE_ID_RE.search(description)
        course_id = (
            f"course_{course_match.group(1).strip()}"
            if course_match
            else self._default_course_id
        )

        return RawEventInput(
            raw_user_id=raw_user_id,
            action=action,
            resource=ResourceInfo(
                resource_id=resource_id,
                resource_type=resource_type,
                name=context or event_name or None,
            ),
            timestamp=timestamp,
            metadata=EventMetadata(
                course_id=course_id,
                source_format=self.format_name,
                component=component,
                raw_eventname=raw_eventname,
                target=target,
                origin=origin or None,
                event_context=context or None,
            ),
        )

    def parse_stream(self, file_path: str | Path) -> Iterator[RawEventInput]:
        path = ensure_file_exists(file_path)
        parsed_rows: list[tuple[int, RawEventInput]] = []

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"El archivo CSV está vacío o sin encabezados: {path}")

            for idx, row in enumerate(reader):
                event = self._parse_row(idx, row)
                if event is not None:
                    parsed_rows.append((idx, event))

        yield from iter_chronological(parsed_rows)
