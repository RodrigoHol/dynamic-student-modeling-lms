from datetime import UTC, datetime, timedelta
from pathlib import Path

from dsm_common.config import WindowDefinition, WindowsConfig, load_windows_config
from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo
from dsm_core.windowing import MultiGranularityWindowManager, compute_window_spec

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_event(
    event_id: str,
    t: datetime,
    *,
    u: str = "usr_001",
    run_id: str = "run_w",
    ingested_at: datetime | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id=run_id,
        u=u,
        a="viewed",
        r=ResourceInfo(resource_id="res_1", resource_type="resource"),
        t=t,
        ingested_at=ingested_at or t,
        M=EventMetadata(course_id="course_105", component="mod_resource", hle="CONSULTA_RECURSO"),
    )


def test_compute_window_spec_across_four_granularities() -> None:
    cfg = load_windows_config(REPO_ROOT / "config" / "windows.yaml")
    ts = datetime(2024, 9, 4, 15, 30, tzinfo=UTC)  # Miércoles de la semana 2024-W36

    daily = compute_window_spec(ts, "daily", cfg.windows["daily"], course_id="course_105")
    assert daily.window_id == "2024-09-04"
    assert daily.window_start == datetime(2024, 9, 4, 0, 0, tzinfo=UTC)
    assert daily.window_end == datetime(2024, 9, 5, 0, 0, tzinfo=UTC)

    weekly = compute_window_spec(ts, "weekly", cfg.windows["weekly"], course_id="course_105")
    assert weekly.window_id == "2024-W36"
    assert weekly.window_start == datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    assert weekly.window_end == datetime(2024, 9, 9, 0, 0, tzinfo=UTC)

    monthly = compute_window_spec(ts, "monthly", cfg.windows["monthly"], course_id="course_105")
    assert monthly.window_id == "2024-09"
    assert monthly.window_start == datetime(2024, 9, 1, 0, 0, tzinfo=UTC)
    assert monthly.window_end == datetime(2024, 10, 1, 0, 0, tzinfo=UTC)

    course = compute_window_spec(ts, "course", cfg.windows["course"], course_id="course_105")
    assert course.window_id == "course_105"
    assert course.close_on_eof is True

    fixed_def = WindowDefinition(type="tumbling", mode="fixed_30d", duration_seconds=2592000)
    fixed_spec = compute_window_spec(
        datetime(2024, 10, 5, 10, 0, tzinfo=UTC),
        "monthly",
        fixed_def,
        course_id="course_105",
        course_start=datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
    )
    assert fixed_spec.window_id == "M02_2024-10-02"


def test_window_manager_grace_period_late_events_and_eof_flush() -> None:
    cfg = load_windows_config(REPO_ROOT / "config" / "windows.yaml")
    manager = MultiGranularityWindowManager(cfg)

    # Evento en día 2024-09-02 10:00
    out1 = manager.ingest(_make_event("e1", datetime(2024, 9, 2, 10, 0, tzinfo=UTC)))
    assert out1.closed_windows == []

    # Evento duplicado (mismo event_id) debe ignorarse
    dup = manager.ingest(_make_event("e1", datetime(2024, 9, 2, 10, 0, tzinfo=UTC)))
    assert dup.is_duplicate is True

    # Evento en día siguiente 2024-09-03 00:02 (dentro de gracia de 300s para 2024-09-02)
    out2 = manager.ingest(_make_event("e2", datetime(2024, 9, 3, 0, 2, tzinfo=UTC)))
    assert out2.closed_windows == []

    # Evento tardío para 2024-09-02 antes de cerrar la ventana (00:02 < 00:05) -> aceptado
    out_late_ok = manager.ingest(_make_event("e3", datetime(2024, 9, 2, 23, 50, tzinfo=UTC)))
    assert out_late_ok.closed_windows == []
    assert out_late_ok.dropped_late_granularities == []

    # Evento en 2024-09-03 00:05:01 supera grace_period (300s) -> cierra daily 2024-09-02
    out3 = manager.ingest(_make_event("e4", datetime(2024, 9, 3, 0, 5, 1, tzinfo=UTC)))
    assert len(out3.closed_windows) == 1
    closed_day = out3.closed_windows[0]
    assert closed_day.granularity == "daily"
    assert closed_day.window_id == "2024-09-02"
    assert [ev.event_id for ev in closed_day.events] == ["e1", "e3"]

    # Evento muy tardío perteneciente al ya cerrado 2024-09-02 -> descartado solo en daily
    out_too_late = manager.ingest(_make_event("e5", datetime(2024, 9, 2, 20, 0, tzinfo=UTC)))
    assert out_too_late.dropped_late_granularities == ["daily"]

    # Flush EOF cierra las ventanas abiertas restantes: daily 2024-09-03, weekly, monthly y course
    flushed = manager.flush_run("run_w", u="usr_001")
    assert [(w.granularity, w.window_id) for w in flushed] == [
        ("daily", "2024-09-03"),
        ("weekly", "2024-W36"),
        ("monthly", "2024-09"),
        ("course", "course_105"),
    ]
    course_win = flushed[-1]
    assert [ev.event_id for ev in course_win.events] == ["e1", "e5", "e3", "e2", "e4"]
    assert manager.open_window_count("run_w", "usr_001") == 0


def test_window_manager_state_roundtrip_and_clock_invariance() -> None:
    cfg = WindowsConfig(
        version="test",
        grace_period_seconds=60,
        active_granularities=["daily", "course"],
        windows={
            "daily": WindowDefinition(type="tumbling", duration_seconds=86400),
            "course": WindowDefinition(type="tumbling", mode="full_course", close_on_eof=True),
        },
    )
    m1 = MultiGranularityWindowManager(cfg)
    t0 = datetime(2024, 9, 2, 12, 0, tzinfo=UTC)
    m1.ingest(_make_event("a1", t0, ingested_at=t0 + timedelta(seconds=1)))

    snapshot = m1.to_state_dict()
    m2 = MultiGranularityWindowManager.from_state_dict(snapshot, cfg)
    out = m2.ingest(
        _make_event(
            "a2",
            t0 + timedelta(days=2),
            ingested_at=t0 + timedelta(seconds=2),
        )
    )
    assert len(out.closed_windows) == 1
    assert out.closed_windows[0].window_id == "2024-09-02"
    flushed = m2.flush_run("run_w", u="usr_001")
    assert len(flushed) == 2
