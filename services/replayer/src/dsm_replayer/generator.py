"""Generador determinista de logs sintéticos realistas compatibles con Moodle."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from dsm_common.schemas import EventMetadata, RawEventInput, ResourceInfo

_ARCHETYPE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("consistent_active", 0.25),
    ("deadline_driven", 0.25),
    ("passive_reader", 0.20),
    ("at_risk_declining", 0.15),
    ("improving", 0.15),
)


@dataclass(slots=True)
class SyntheticCourseConfig:
    """Parámetros de generación de un curso sintético compatible con Moodle."""

    num_students: int = 50
    num_weeks: int = 8
    seed: int = 42
    course_id: str = "course_105"
    start_date: datetime = datetime(2024, 9, 2, 8, 0, tzinfo=UTC)
    target_events: int | None = None
    noise_ratio: float = 0.02


@dataclass(frozen=True, slots=True)
class _EventTemplate:
    hle: str
    component: str
    action: str
    target: str
    raw_eventname: str
    resource_type: str
    resource_pool_size: int
    label_prefix: str


_TEMPLATES: dict[str, _EventTemplate] = {
    "ACCESO_CURSO": _EventTemplate(
        hle="ACCESO_CURSO",
        component="core",
        action="viewed",
        target="course",
        raw_eventname="\\core\\event\\course_viewed",
        resource_type="course",
        resource_pool_size=1,
        label_prefix="Curso Principal",
    ),
    "CONSULTA_RECURSO": _EventTemplate(
        hle="CONSULTA_RECURSO",
        component="mod_resource",
        action="viewed",
        target="course_module",
        raw_eventname="\\mod_resource\\event\\course_module_viewed",
        resource_type="resource",
        resource_pool_size=12,
        label_prefix="Lectura Semana",
    ),
    "CONSULTA_PAGINA": _EventTemplate(
        hle="CONSULTA_RECURSO",
        component="mod_page",
        action="viewed",
        target="course_module",
        raw_eventname="\\mod_page\\event\\course_module_viewed",
        resource_type="page",
        resource_pool_size=6,
        label_prefix="Guía Temática",
    ),
    "PARTICIPACION_FORO": _EventTemplate(
        hle="PARTICIPACION_FORO",
        component="mod_forum",
        action="created",
        target="post",
        raw_eventname="\\mod_forum\\event\\post_created",
        resource_type="forum",
        resource_pool_size=4,
        label_prefix="Foro de Discusión",
    ),
    "LECTURA_FORO": _EventTemplate(
        hle="PARTICIPACION_FORO",
        component="mod_forum",
        action="viewed",
        target="discussion",
        raw_eventname="\\mod_forum\\event\\discussion_viewed",
        resource_type="forum",
        resource_pool_size=4,
        label_prefix="Foro de Discusión",
    ),
    "ENVIO_TAREA": _EventTemplate(
        hle="ENVIO_TAREA",
        component="mod_assign",
        action="submitted",
        target="assessable",
        raw_eventname="\\mod_assign\\event\\assessable_submitted",
        resource_type="assign",
        resource_pool_size=8,
        label_prefix="Tarea Práctica",
    ),
    "INTENTO_CUESTIONARIO": _EventTemplate(
        hle="INTENTO_CUESTIONARIO",
        component="mod_quiz",
        action="submitted",
        target="attempt",
        raw_eventname="\\mod_quiz\\event\\attempt_submitted",
        resource_type="quiz",
        resource_pool_size=6,
        label_prefix="Cuestionario",
    ),
    "REVISION_RETROALIMENTACION": _EventTemplate(
        hle="REVISION_RETROALIMENTACION",
        component="gradereport_user",
        action="viewed",
        target="grade",
        raw_eventname="\\gradereport_user\\event\\grade_report_viewed",
        resource_type="grade",
        resource_pool_size=2,
        label_prefix="Calificaciones",
    ),
    "NOISE_LOG": _EventTemplate(
        hle="NOISE",
        component="core",
        action="viewed",
        target="log_report",
        raw_eventname="\\core\\event\\log_report_viewed",
        resource_type="report",
        resource_pool_size=1,
        label_prefix="Informe de Registro",
    ),
}

_ARCHETYPE_SEQUENCES: dict[str, list[list[str]]] = {
    "consistent_active": [
        [
            "ACCESO_CURSO",
            "CONSULTA_RECURSO",
            "CONSULTA_PAGINA",
            "PARTICIPACION_FORO",
            "ENVIO_TAREA",
            "REVISION_RETROALIMENTACION",
        ],
        [
            "ACCESO_CURSO",
            "CONSULTA_RECURSO",
            "LECTURA_FORO",
            "PARTICIPACION_FORO",
            "INTENTO_CUESTIONARIO",
            "REVISION_RETROALIMENTACION",
        ],
    ],
    "deadline_driven": [
        ["ACCESO_CURSO", "CONSULTA_RECURSO", "ENVIO_TAREA"],
        ["ACCESO_CURSO", "CONSULTA_RECURSO", "INTENTO_CUESTIONARIO", "REVISION_RETROALIMENTACION"],
    ],
    "passive_reader": [
        ["ACCESO_CURSO", "CONSULTA_RECURSO", "LECTURA_FORO"],
        ["ACCESO_CURSO", "CONSULTA_PAGINA", "CONSULTA_RECURSO"],
    ],
    "at_risk_declining": [
        ["ACCESO_CURSO", "CONSULTA_RECURSO", "PARTICIPACION_FORO", "ENVIO_TAREA"],
        ["ACCESO_CURSO", "CONSULTA_RECURSO"],
    ],
    "improving": [
        ["ACCESO_CURSO", "CONSULTA_RECURSO"],
        [
            "ACCESO_CURSO",
            "CONSULTA_RECURSO",
            "PARTICIPACION_FORO",
            "ENVIO_TAREA",
            "INTENTO_CUESTIONARIO",
            "REVISION_RETROALIMENTACION",
        ],
    ],
}


def _assign_archetypes(num_students: int, rng: random.Random) -> list[str]:
    archetypes: list[str] = []
    for idx in range(num_students):
        cursor = (idx + 0.5) / num_students
        cumulative = 0.0
        chosen = _ARCHETYPE_WEIGHTS[-1][0]
        for name, weight in _ARCHETYPE_WEIGHTS:
            cumulative += weight
            if cursor <= cumulative:
                chosen = name
                break
        archetypes.append(chosen)
    rng.shuffle(archetypes)
    return archetypes


def _weekly_sessions_for_archetype(
    archetype: str,
    week_idx: int,
    total_weeks: int,
    rng: random.Random,
) -> tuple[int, bool]:
    """Devuelve `(num_sesiones, prefer_late_week)` según arquetipo y semana."""
    midpoint = max(1, total_weeks // 2)
    if archetype == "consistent_active":
        return rng.randint(4, 6), False
    if archetype == "deadline_driven":
        return rng.randint(2, 3), True
    if archetype == "passive_reader":
        return rng.randint(2, 4), False
    if archetype == "at_risk_declining":
        if week_idx < midpoint:
            return rng.randint(3, 5), False
        return rng.randint(0, 1), False
    # improving
    if week_idx < midpoint:
        return rng.randint(1, 2), False
    return rng.randint(4, 6), False


def _choose_sequence(
    archetype: str,
    week_idx: int,
    total_weeks: int,
    rng: random.Random,
) -> list[str]:
    midpoint = max(1, total_weeks // 2)
    options = _ARCHETYPE_SEQUENCES[archetype]
    if archetype == "at_risk_declining":
        return options[0] if week_idx < midpoint else options[1]
    if archetype == "improving":
        return options[0] if week_idx < midpoint else options[1]
    return rng.choice(options)


def _build_session_events(
    *,
    student_id: str,
    archetype: str,
    week_idx: int,
    total_weeks: int,
    week_start: datetime,
    course_id: str,
    prefer_late_week: bool,
    noise_ratio: float,
    rng: random.Random,
    session_counter: int,
) -> list[RawEventInput]:
    day_offset = rng.randint(4, 6) if prefer_late_week else rng.randint(0, 6)
    hour = rng.randint(17, 23) if prefer_late_week else rng.randint(8, 22)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    current_ts = week_start + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)

    session_seed = f"{course_id}:{student_id}:{week_idx}:{session_counter}"
    session_hash = f"sess_{hashlib.sha1(session_seed.encode('utf-8')).hexdigest()[:8]}"

    sequence = _choose_sequence(archetype, week_idx, total_weeks, rng)
    events: list[RawEventInput] = []

    for step_idx, template_key in enumerate(sequence):
        if step_idx > 0:
            current_ts = current_ts + timedelta(seconds=rng.randint(30, 720))

        tpl = _TEMPLATES["NOISE_LOG"] if rng.random() < noise_ratio else _TEMPLATES[template_key]
        if tpl.resource_type == "course":
            resource_id = course_id
            resource_name = f"{tpl.label_prefix} {course_id}"
        else:
            slot = ((week_idx * 2 + step_idx) % tpl.resource_pool_size) + 1
            resource_id = f"{tpl.resource_type}_{slot}"
            resource_name = f"{tpl.label_prefix} {slot}"

        events.append(
            RawEventInput(
                raw_user_id=student_id,
                action=tpl.action,
                resource=ResourceInfo(
                    resource_id=resource_id,
                    resource_type=tpl.resource_type,
                    name=resource_name,
                ),
                timestamp=current_ts,
                metadata=EventMetadata(
                    course_id=course_id,
                    source_format="synthetic_jsonl",
                    component=tpl.component,
                    raw_eventname=tpl.raw_eventname,
                    target=tpl.target,
                    session_hash=session_hash,
                    archetype=archetype,
                ),
            )
        )

    return events


def generate_synthetic_events(config: SyntheticCourseConfig) -> list[RawEventInput]:
    """Genera una lista cronológica determinista de eventos sintéticos estilo Moodle."""
    if config.num_students < 1:
        raise ValueError("num_students debe ser >= 1.")
    if config.num_weeks < 1:
        raise ValueError("num_weeks debe ser >= 1.")
    if config.target_events is not None and config.target_events < 1:
        raise ValueError("target_events debe ser >= 1.")

    rng = random.Random(config.seed)
    start_utc = (
        config.start_date.replace(tzinfo=UTC)
        if config.start_date.tzinfo is None
        else config.start_date.astimezone(UTC)
    )
    archetypes = _assign_archetypes(config.num_students, rng)
    student_ids = [f"alu_{idx + 1:03d}" for idx in range(config.num_students)]

    events: list[RawEventInput] = []
    session_counter = 0

    for week_idx in range(config.num_weeks):
        week_start = start_utc + timedelta(weeks=week_idx)
        for student_id, archetype in zip(student_ids, archetypes, strict=True):
            num_sessions, prefer_late = _weekly_sessions_for_archetype(
                archetype, week_idx, config.num_weeks, rng
            )
            for _ in range(num_sessions):
                session_counter += 1
                events.extend(
                    _build_session_events(
                        student_id=student_id,
                        archetype=archetype,
                        week_idx=week_idx,
                        total_weeks=config.num_weeks,
                        week_start=week_start,
                        course_id=config.course_id,
                        prefer_late_week=prefer_late,
                        noise_ratio=config.noise_ratio,
                        rng=rng,
                        session_counter=session_counter,
                    )
                )

    while config.target_events is not None and len(events) < config.target_events:
        week_idx = rng.randrange(config.num_weeks)
        student_idx = rng.randrange(config.num_students)
        week_start = start_utc + timedelta(weeks=week_idx)
        session_counter += 1
        events.extend(
            _build_session_events(
                student_id=student_ids[student_idx],
                archetype=archetypes[student_idx],
                week_idx=week_idx,
                total_weeks=config.num_weeks,
                week_start=week_start,
                course_id=config.course_id,
                prefer_late_week=archetypes[student_idx] == "deadline_driven",
                noise_ratio=config.noise_ratio,
                rng=rng,
                session_counter=session_counter,
            )
        )

    events.sort(key=lambda ev: (ev.timestamp, ev.raw_user_id))

    if config.target_events is not None and len(events) > config.target_events:
        total = len(events)
        target = config.target_events
        selected_indices = [(i * total) // target for i in range(target)]
        events = [events[i] for i in selected_indices]

    return events


def _extract_numeric_suffix(value: str, fallback: int) -> int:
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else fallback


def _moodle_csv_event_label(event: RawEventInput) -> str:
    extra = event.metadata.model_extra or {}
    target = str(extra.get("target") or "")
    raw_name = event.metadata.raw_eventname or ""
    if "log_report_viewed" in raw_name:
        return "Informe de registro visto (log_report_viewed)"
    if target == "course":
        return "Curso visto"
    if target == "grade":
        return "Informe de usuario de calificaciones visto"
    if target == "feedback":
        return "Retroalimentación vista"
    if event.action == "submitted" and event.metadata.component == "mod_assign":
        return "Se ha enviado una entrega"
    if event.action == "submitted" and event.metadata.component == "mod_quiz":
        return "Intento de cuestionario enviado"
    if event.action == "created":
        return "Mensaje creado en el foro"
    return f"Módulo de curso {event.action}"


def write_synthetic_dataset(
    events: list[RawEventInput],
    output_path: str | Path,
    fmt: str = "synthetic_jsonl",
) -> int:
    """Serializa una lista de eventos sintéticos en el formato indicado."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "synthetic_jsonl":
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return len(events)

    if fmt == "moodle_csv":
        fieldnames = [
            "Hora",
            "Nombre completo del usuario",
            "Usuario afectado",
            "Contexto del evento",
            "Componente",
            "Nombre del evento",
            "Descripción",
            "Origen",
            "Dirección IP",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for idx, event in enumerate(events, start=1):
                course_num = _extract_numeric_suffix(event.metadata.course_id, 105)
                res_num = _extract_numeric_suffix(event.resource.resource_id, idx)
                writer.writerow(
                    {
                        "Hora": event.timestamp.astimezone(UTC).strftime("%d/%m/%Y, %H:%M:%S"),
                        "Nombre completo del usuario": event.raw_user_id,
                        "Usuario afectado": "-",
                        "Contexto del evento": event.resource.name or event.resource.resource_id,
                        "Componente": event.metadata.component or "core",
                        "Nombre del evento": _moodle_csv_event_label(event),
                        "Descripción": (
                            f"El usuario con id '{event.raw_user_id}' realizó '{event.action}' "
                            f"en el módulo del curso id '{res_num}' "
                            f"del curso con id '{course_num}'."
                        ),
                        "Origen": "web",
                        "Dirección IP": "127.0.0.1",
                    }
                )
        return len(events)

    if fmt == "moodle_db":
        fieldnames = [
            "id",
            "eventname",
            "component",
            "action",
            "target",
            "objecttable",
            "objectid",
            "crud",
            "edulevel",
            "contextinstanceid",
            "userid",
            "courseid",
            "relateduserid",
            "timecreated",
            "origin",
        ]
        crud_map = {"created": "c", "viewed": "r", "updated": "u", "submitted": "u"}
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for idx, event in enumerate(events, start=1):
                extra: dict[str, Any] = event.metadata.model_extra or {}
                course_num = _extract_numeric_suffix(event.metadata.course_id, 105)
                res_num = _extract_numeric_suffix(event.resource.resource_id, idx)
                writer.writerow(
                    {
                        "id": idx,
                        "eventname": event.metadata.raw_eventname
                        or f"\\{event.metadata.component or 'core'}\\event\\{event.action}",
                        "component": event.metadata.component or "core",
                        "action": event.action,
                        "target": extra.get("target") or event.resource.resource_type,
                        "objecttable": event.resource.resource_type,
                        "objectid": res_num,
                        "crud": crud_map.get(event.action, "r"),
                        "edulevel": 2,
                        "contextinstanceid": res_num,
                        "userid": event.raw_user_id,
                        "courseid": course_num,
                        "relateduserid": "",
                        "timecreated": int(event.timestamp.timestamp()),
                        "origin": "web",
                    }
                )
        return len(events)

    raise ValueError(f"Formato de exportación no soportado: '{fmt}'.")
