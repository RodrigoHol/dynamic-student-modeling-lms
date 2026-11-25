from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dsm_common.schemas import EventMetadata, RawEventInput, ResourceInfo
from dsm_replayer.parsers.base import (
    SourceParser,
    ensure_file_exists,
    iter_chronological,
    parse_datetime_utc,
)


def _normalize_course_id(raw_course_id: Any, default_course_id: str) -> str:
    if raw_course_id is None or str(raw_course_id).strip() == "":
        return default_course_id
    text = str(raw_course_id).strip()
    return text if text.startswith("course_") else f"course_{text}"


def _build_event_from_db_row(
    row: dict[str, Any],
    *,
    fallback_index: int,
    default_course_id: str,
    source_format: str,
) -> tuple[int, RawEventInput]:
    raw_user = row.get("userid")
    if raw_user is None or str(raw_user).strip() == "":
        raise ValueError(f"Fila {fallback_index} sin 'userid' en mdl_logstore_standard_log.")

    raw_action = str(row.get("action") or "").strip()
    if not raw_action:
        raise ValueError(f"Fila {fallback_index} sin 'action' en mdl_logstore_standard_log.")

    raw_time = row.get("timecreated")
    if raw_time is None or str(raw_time).strip() == "":
        raise ValueError(f"Fila {fallback_index} sin 'timecreated' en mdl_logstore_standard_log.")

    timestamp = parse_datetime_utc(raw_time)
    component = str(row.get("component") or "core").strip()
    target = str(row.get("target") or "").strip() or None
    eventname = str(row.get("eventname") or "").strip() or None
    objecttable = str(row.get("objecttable") or "").strip() or None
    objectid = row.get("objectid")
    contextinstanceid = row.get("contextinstanceid")

    resource_type = objecttable or component.removeprefix("mod_") or "unknown"
    if objectid not in (None, "", "0", 0):
        resource_id = f"{resource_type}_{objectid}"
    elif contextinstanceid not in (None, "", "0", 0):
        resource_id = f"{resource_type}_{contextinstanceid}"
    else:
        resource_id = f"{resource_type}_{target or raw_action}"

    course_id = _normalize_course_id(row.get("courseid"), default_course_id)
    metadata = EventMetadata(
        course_id=course_id,
        source_format=source_format,
        component=component,
        raw_eventname=eventname,
        target=target,
        crud=row.get("crud"),
        edulevel=row.get("edulevel"),
        contextinstanceid=contextinstanceid,
        objecttable=objecttable,
        objectid=objectid,
        relateduserid=row.get("relateduserid"),
        origin=row.get("origin"),
    )
    event = RawEventInput(
        raw_user_id=str(raw_user).strip(),
        action=raw_action,
        resource=ResourceInfo(
            resource_id=resource_id,
            resource_type=resource_type,
            name=target or eventname,
        ),
        timestamp=timestamp,
        metadata=metadata,
    )

    raw_id = row.get("id")
    try:
        tie_breaker = int(raw_id) if raw_id not in (None, "") else fallback_index
    except (TypeError, ValueError):
        tie_breaker = fallback_index
    return tie_breaker, event


class MoodleDbLogParser(SourceParser):
    def __init__(self, default_course_id: str = "course_unknown") -> None:
        self._default_course_id = default_course_id

    @property
    def format_name(self) -> str:
        return "moodle_db"

    def parse_stream(self, file_path: str | Path) -> Iterator[RawEventInput]:
        path = ensure_file_exists(file_path)
        parsed_rows: list[tuple[int, RawEventInput]] = []

        if path.suffix.lower() in {".jsonl", ".ndjson"}:
            with path.open("r", encoding="utf-8-sig") as handle:
                for idx, line in enumerate(handle):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    row = json.loads(stripped)
                    if not isinstance(row, dict):
                        raise ValueError(f"Línea {idx + 1} en {path} no es un objeto JSON.")
                    parsed_rows.append(
                        _build_event_from_db_row(
                            row,
                            fallback_index=idx,
                            default_course_id=self._default_course_id,
                            source_format=self.format_name,
                        )
                    )
        else:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"El archivo CSV está vacío o sin encabezados: {path}")
                for idx, row in enumerate(reader):
                    normalized_row = {
                        k.strip(): v for k, v in row.items() if k is not None
                    }
                    parsed_rows.append(
                        _build_event_from_db_row(
                            normalized_row,
                            fallback_index=idx,
                            default_course_id=self._default_course_id,
                            source_format=self.format_name,
                        )
                    )

        yield from iter_chronological(parsed_rows)
