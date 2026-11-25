import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dsm_replayer.parsers import (
    MoodleCsvExportParser,
    MoodleDbLogParser,
    SyntheticJsonlParser,
    create_parser,
    detect_format,
)


def test_moodle_csv_spanish_sorts_chronologically_and_maps_components(tmp_path: Path) -> None:
    csv_path = tmp_path / "moodle_es.csv"
    header = (
        "Hora,Nombre completo del usuario,Usuario afectado,Contexto del evento,"
        "Componente,Nombre del evento,Descripción,Origen,Dirección IP"
    )
    row_1 = (
        '"18/09/2024, 15:10:00",Ana Perez,-,Tarea: Tarea 1,Tarea,'
        "Se ha enviado una entrega,"
        '"El usuario con id \'alu_02\' ha enviado su entrega en el módulo del curso '
        'id \'42\' del curso con id \'105\'.",web,127.0.0.1'
    )
    row_2 = (
        '"18/09/2024, 14:00:00",Ana Perez,-,Curso: ML 105,Sistema,Curso visto,'
        '"El usuario con id \'alu_02\' vio el curso con id \'105\'.",web,127.0.0.1'
    )
    csv_path.write_text("\n".join([header, row_1, row_2]), encoding="utf-8-sig")

    assert detect_format(csv_path) == "moodle_csv"
    events = list(MoodleCsvExportParser().parse_stream(csv_path))
    assert len(events) == 2
    assert events[0].timestamp < events[1].timestamp
    assert events[0].raw_user_id == "alu_02"
    assert events[0].action == "viewed"
    assert events[0].metadata.component == "core"
    assert events[0].metadata.model_extra["target"] == "course"
    assert events[0].metadata.course_id == "course_105"

    assert events[1].action == "submitted"
    assert events[1].metadata.component == "mod_assign"
    assert events[1].resource.resource_id == "assign_42"


def test_moodle_csv_english_headers(tmp_path: Path) -> None:
    csv_path = tmp_path / "moodle_en.csv"
    header = (
        "Time,User full name,Affected user,Event context,"
        "Component,Event name,Description,Origin,IP address"
    )
    row_1 = (
        '"18/09/24, 16:00:00",John Doe,-,Quiz: Midterm,Quiz,Quiz attempt submitted,'
        '"The user with id \'u_77\' submitted the attempt with id \'9\' '
        'in course module id \'15\'.",web,10.0.0.1'
    )
    csv_path.write_text("\n".join([header, row_1]), encoding="utf-8")
    events = list(MoodleCsvExportParser(default_course_id="course_202").parse_stream(csv_path))
    assert len(events) == 1
    ev = events[0]
    assert ev.raw_user_id == "u_77"
    assert ev.action == "submitted"
    assert ev.metadata.component == "mod_quiz"
    assert ev.metadata.course_id == "course_202"
    assert ev.timestamp == datetime(2024, 9, 18, 16, 0, 0, tzinfo=UTC)


def test_moodle_db_log_parser_csv_and_jsonl(tmp_path: Path) -> None:
    csv_path = tmp_path / "mdl_log.csv"
    csv_path.write_text(
        "\n".join(
            [
                "id,eventname,component,action,target,objecttable,objectid,crud,edulevel,contextinstanceid,userid,courseid,relateduserid,timecreated,origin",
                "2,\\mod_forum\\event\\post_created,mod_forum,created,post,forum_posts,88,c,2,12,501,105,,1726669200,web",
                "1,\\core\\event\\course_viewed,core,viewed,course,course,105,r,2,105,501,105,,1726665600,web",
            ]
        ),
        encoding="utf-8",
    )
    assert detect_format(csv_path) == "moodle_db"
    csv_events = list(MoodleDbLogParser().parse_stream(csv_path))
    assert len(csv_events) == 2
    assert csv_events[0].timestamp < csv_events[1].timestamp
    assert csv_events[0].raw_user_id == "501"
    assert csv_events[0].metadata.course_id == "course_105"
    assert csv_events[1].metadata.component == "mod_forum"

    jsonl_path = tmp_path / "mdl_log.jsonl"
    jsonl_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": 10,
                        "eventname": "\\mod_assign\\event\\assessable_submitted",
                        "component": "mod_assign",
                        "action": "submitted",
                        "target": "assessable",
                        "objecttable": "assign_submission",
                        "objectid": 33,
                        "userid": 900,
                        "courseid": 300,
                        "timecreated": 1726670000,
                    }
                )
            ]
        ),
        encoding="utf-8",
    )
    assert detect_format(jsonl_path) == "moodle_db"
    jsonl_events = list(create_parser("moodle_db").parse_stream(jsonl_path))
    assert len(jsonl_events) == 1
    assert jsonl_events[0].raw_user_id == "900"
    assert jsonl_events[0].metadata.course_id == "course_300"


def test_synthetic_jsonl_parser_sorts_unordered_events(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "unordered.jsonl"
    ev_late = {
        "raw_user_id": "alu_1",
        "action": "submitted",
        "resource": {"resource_id": "assign_1", "resource_type": "assign"},
        "timestamp": "2024-09-02T12:00:00Z",
        "metadata": {"course_id": "course_105", "component": "mod_assign"},
    }
    ev_early = {
        "raw_user_id": "alu_1",
        "action": "viewed",
        "resource": {"resource_id": "course_105", "resource_type": "course"},
        "timestamp": "2024-09-02T08:00:00Z",
        "metadata": {"course_id": "course_105", "component": "core"},
    }
    jsonl_path.write_text(
        json.dumps(ev_late) + "\n\n" + json.dumps(ev_early) + "\n",
        encoding="utf-8",
    )

    assert detect_format(jsonl_path) == "synthetic_jsonl"
    events = list(SyntheticJsonlParser().parse_stream(jsonl_path))
    assert len(events) == 2
    assert events[0].timestamp < events[1].timestamp
    assert events[0].action == "viewed"


def test_versioned_sample_datasets_parse_cleanly() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    samples_dir = repo_root / "data" / "samples"
    expected_files = [
        ("sample_synthetic.jsonl", "synthetic_jsonl"),
        ("sample_moodle_export.csv", "moodle_csv"),
        ("sample_moodle_db_log.csv", "moodle_db"),
    ]
    for filename, expected_fmt in expected_files:
        path = samples_dir / filename
        assert path.is_file(), f"Falta muestra versionada: {path}"
        detected = detect_format(path)
        assert detected == expected_fmt
        events = list(create_parser(detected).parse_stream(path))
        assert len(events) == 80
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)


def test_unknown_format_raises_value_error() -> None:
    with pytest.raises(ValueError):
        create_parser("unsupported_fmt")
