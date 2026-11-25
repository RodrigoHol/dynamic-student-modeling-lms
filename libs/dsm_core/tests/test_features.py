from datetime import UTC, datetime, timedelta
from pathlib import Path

from dsm_common.config import load_features_config, load_hle_catalog, load_windows_config
from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo
from dsm_core.features import FeaturePipeline, group_events_into_sessions
from dsm_core.pipeline import PreprocessingEngine

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_event(
    event_id: str,
    t: datetime,
    *,
    hle: str | None = "CONSULTA_RECURSO",
    session_hash: str | None = "sess_1",
    component: str = "mod_resource",
    action: str = "viewed",
    resource_type: str = "resource",
    raw_eventname: str = "\\mod_resource\\event\\course_module_viewed",
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        run_id="run_f",
        u="usr_f",
        a=action,
        r=ResourceInfo(resource_id="res_1", resource_type=resource_type),
        t=t,
        ingested_at=t,
        M=EventMetadata(
            course_id="course_105",
            component=component,
            raw_eventname=raw_eventname,
            hle=hle,
            session_hash=session_hash,
        ),
    )


def test_feature_pipeline_computes_all_configured_extractors() -> None:
    hle_cfg = load_hle_catalog(REPO_ROOT / "config" / "hle_catalog.yaml")
    feat_cfg = load_features_config(REPO_ROOT / "config" / "features.yaml")
    known_hles = [r.hle for r in hle_cfg.rules] + [hle_cfg.default_hle]
    pipeline = FeaturePipeline(feat_cfg, hle_categories=known_hles)

    day1 = datetime(2024, 9, 2, 10, 0, tzinfo=UTC)
    day2 = datetime(2024, 9, 3, 14, 0, tzinfo=UTC)
    events = [
        _make_event("e1", day1, hle="ACCESO_CURSO", session_hash="s1"),
        _make_event("e2", day1 + timedelta(minutes=5), hle="CONSULTA_RECURSO", session_hash="s1"),
        _make_event("e3", day2, hle="ACCESO_CURSO", session_hash="s2"),
        _make_event("e4", day2 + timedelta(minutes=10), hle="ENVIO_TAREA", session_hash="s2"),
    ]
    vec = pipeline.extract(
        events,
        window_meta={
            "window_start": datetime(2024, 9, 2, 0, 0, tzinfo=UTC),
            "window_end": datetime(2024, 9, 9, 0, 0, tzinfo=UTC),
        },
    )

    assert vec["total_events"] == 4.0
    assert vec["active_days"] == 2.0
    assert vec["hle_acceso_curso_count"] == 2.0
    assert vec["hle_consulta_recurso_count"] == 1.0
    assert vec["hle_envio_tarea_count"] == 1.0
    assert vec["hle_participacion_foro_count"] == 0.0
    assert vec["hle_otro_count"] == 0.0
    assert 0.0 < vec["regularity_index"] < 1.0
    assert vec["session_count"] == 2.0
    assert vec["mean_session_duration_sec"] == 450.0  # (300 + 600) / 2


def test_group_sessions_falls_back_to_inactivity_gap_without_session_hash() -> None:
    base = datetime(2024, 9, 2, 8, 0, tzinfo=UTC)
    events = [
        _make_event("e1", base, session_hash=None),
        _make_event("e2", base + timedelta(minutes=10), session_hash=None),
        _make_event("e3", base + timedelta(minutes=50), session_hash=None),
    ]
    sessions = group_events_into_sessions(events, inactivity_timeout_sec=1800)
    assert len(sessions) == 2
    assert [e.event_id for e in sessions[0]] == ["e1", "e2"]
    assert [e.event_id for e in sessions[1]] == ["e3"]


def test_preprocessing_engine_determinism_under_different_ingestion_clocks() -> None:
    hle_cfg = load_hle_catalog(REPO_ROOT / "config" / "hle_catalog.yaml")
    feat_cfg = load_features_config(REPO_ROOT / "config" / "features.yaml")
    win_cfg = load_windows_config(REPO_ROOT / "config" / "windows.yaml")

    base_t = datetime(2024, 9, 2, 9, 0, tzinfo=UTC)
    raw_events = [
        _make_event(
            "e_noise",
            base_t + timedelta(minutes=1),
            component="core",
            raw_eventname="\\core\\event\\log_report_viewed",
            hle=None,
        ),
        _make_event(
            "e1",
            base_t,
            component="core",
            action="viewed",
            resource_type="course",
            raw_eventname="\\core\\event\\course_viewed",
            hle=None,
            session_hash="s1",
        ),
        _make_event(
            "e2",
            base_t + timedelta(days=30),
            component="mod_assign",
            action="submitted",
            resource_type="assign",
            raw_eventname="\\mod_assign\\event\\assessable_submitted",
            hle=None,
            session_hash="s2",
        ),
    ]

    def _run_with_ingested_offset(offset_sec: int) -> list[tuple[dict, list]]:
        engine = PreprocessingEngine(hle_cfg, feat_cfg, win_cfg)
        outputs = []
        for idx, ev in enumerate(raw_events):
            shifted = ev.model_copy(
                update={
                    "ingested_at": datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
                    + timedelta(seconds=idx * offset_sec)
                }
            )
            res = engine.process_event(shifted)
            outputs.extend(res.outputs)
        outputs.extend(engine.flush_run("run_f"))
        return [
            (
                {
                    "granularity": f.granularity,
                    "window_id": f.window_id,
                    "features": f.features,
                    "event_count": f.event_count,
                },
                [(item.hle, item.t.isoformat(), item.a) for item in tr.trace],
            )
            for f, tr in outputs
        ]

    run_slow = _run_with_ingested_offset(100)
    run_fast = _run_with_ingested_offset(1)
    assert run_slow == run_fast
    assert len(run_slow) == 7  # 2 daily + 2 weekly + 2 monthly + 1 course
