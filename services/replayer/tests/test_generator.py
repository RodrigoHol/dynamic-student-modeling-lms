from pathlib import Path

from dsm_replayer.generator import (
    SyntheticCourseConfig,
    generate_synthetic_events,
    write_synthetic_dataset,
)
from dsm_replayer.parsers import create_parser


def test_generator_is_deterministic_by_seed() -> None:
    cfg = SyntheticCourseConfig(num_students=10, num_weeks=2, seed=123, target_events=120)
    run_a = generate_synthetic_events(cfg)
    run_b = generate_synthetic_events(cfg)
    assert len(run_a) == 120
    assert [e.model_dump(mode="json") for e in run_a] == [
        e.model_dump(mode="json") for e in run_b
    ]


def test_generator_5000_events_50_students_8_weeks() -> None:
    cfg = SyntheticCourseConfig(
        num_students=50,
        num_weeks=8,
        seed=42,
        course_id="course_105",
        target_events=5000,
    )
    events = generate_synthetic_events(cfg)
    assert len(events) == 5000

    timestamps = [ev.timestamp for ev in events]
    assert timestamps == sorted(timestamps)

    students = {ev.raw_user_id for ev in events}
    assert len(students) == 50

    span_days = (timestamps[-1] - timestamps[0]).days
    assert span_days >= 45

    components = {ev.metadata.component for ev in events}
    assert {"core", "mod_resource", "mod_forum", "mod_assign", "mod_quiz"}.issubset(components)


def test_generator_round_trip_all_formats(tmp_path: Path) -> None:
    events = generate_synthetic_events(
        SyntheticCourseConfig(num_students=5, num_weeks=2, seed=7, target_events=60)
    )
    for fmt, ext in [
        ("synthetic_jsonl", "jsonl"),
        ("moodle_csv", "csv"),
        ("moodle_db", "csv"),
    ]:
        out_path = tmp_path / f"dataset_{fmt}.{ext}"
        written = write_synthetic_dataset(events, out_path, fmt=fmt)
        assert written == 60
        parsed = list(create_parser(fmt).parse_stream(out_path))
        assert len(parsed) == 60
        assert [e.timestamp for e in parsed] == sorted(e.timestamp for e in parsed)
