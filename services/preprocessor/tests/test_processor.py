from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from dsm_common.config import load_features_config, load_hle_catalog, load_windows_config
from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo, RunEofEvent
from dsm_preprocessor.processor import InMemoryState, PreprocessorHandler

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_handler() -> PreprocessorHandler:
    return PreprocessorHandler(
        load_hle_catalog(REPO_ROOT / "config" / "hle_catalog.yaml"),
        load_features_config(REPO_ROOT / "config" / "features.yaml"),
        load_windows_config(REPO_ROOT / "config" / "windows.yaml"),
    )


def _canonical_dict(
    *,
    run_id: str,
    u: str,
    t: datetime,
    ingested_at: datetime,
    component: str,
    action: str,
    raw_eventname: str,
    resource_type: str,
    target: str | None = None,
    session_hash: str | None = "sess_1",
) -> dict:
    extra = {"target": target} if target is not None else {}
    ev = CanonicalEvent(
        event_id=str(uuid4()),
        run_id=run_id,
        u=u,
        a=action,
        r=ResourceInfo(resource_id="res_1", resource_type=resource_type),
        t=t,
        ingested_at=ingested_at,
        M=EventMetadata(
            course_id="course_105",
            source_format="synthetic_jsonl",
            component=component,
            raw_eventname=raw_eventname,
            session_hash=session_hash,
            **extra,
        ),
    )
    return ev.model_dump(mode="json")


def test_processor_filters_noise_maps_hle_and_closes_four_granularities() -> None:
    handler = _make_handler()
    state = InMemoryState()
    t0 = datetime(2024, 9, 2, 10, 0, tzinfo=UTC)

    noise = _canonical_dict(
        run_id="run_p1",
        u="usr_01",
        t=t0,
        ingested_at=t0,
        component="core",
        action="viewed",
        raw_eventname="\\core\\event\\log_report_viewed",
        resource_type="report",
        target="log_report",
    )
    assert handler.process_record(noise, state) == []

    ev1 = _canonical_dict(
        run_id="run_p1",
        u="usr_01",
        t=t0,
        ingested_at=t0,
        component="core",
        action="viewed",
        raw_eventname="\\core\\event\\course_viewed",
        resource_type="course",
        target="course",
    )
    assert handler.process_record(ev1, state) == []

    ev2 = _canonical_dict(
        run_id="run_p1",
        u="usr_01",
        t=t0 + timedelta(days=30),
        ingested_at=t0 + timedelta(seconds=5),
        component="mod_assign",
        action="submitted",
        raw_eventname="\\mod_assign\\event\\assessable_submitted",
        resource_type="assign",
        target="assessable",
        session_hash="sess_2",
    )
    out_mid = handler.process_record(ev2, state)
    # Debe cerrar daily (2024-09-02), weekly (2024-W36) y monthly (2024-09) -> 3*2 mensajes
    assert len(out_mid) == 6

    eof = RunEofEvent(
        event_id=str(uuid4()),
        run_id="run_p1",
        u="usr_01",
        course_id="course_105",
        emitted_at=t0 + timedelta(seconds=10),
    ).model_dump(mode="json")
    out_eof = handler.process_record(eof, state)
    # Restantes: daily (2024-10-02), weekly (2024-W40), monthly (2024-10), course (course_105)
    assert len(out_eof) == 8
    assert state.get("window_state") is None

    all_features = [m["payload"] for m in (out_mid + out_eof) if m["_target"] == "features"]
    all_traces = [m["payload"] for m in (out_mid + out_eof) if m["_target"] == "traces"]
    assert {f["granularity"] for f in all_features} == {"daily", "weekly", "monthly", "course"}
    assert {tr["granularity"] for tr in all_traces} == {"daily", "weekly", "monthly", "course"}
    course_trace = next(tr for tr in all_traces if tr["granularity"] == "course")
    assert [item["hle"] for item in course_trace["trace"]] == ["ACCESO_CURSO", "ENVIO_TAREA"]


def test_processor_routes_invalid_payloads_to_dlq() -> None:
    handler = _make_handler()
    state = InMemoryState()
    out = handler.process_record({"bad": "payload"}, state)
    assert len(out) == 1
    assert out[0]["_target"] == "dlq"
    assert out[0]["payload"]["raw_payload"] == {"bad": "payload"}


def test_processor_determinism_across_different_ingestion_speeds() -> None:
    handler = _make_handler()
    t0 = datetime(2024, 9, 2, 9, 0, tzinfo=UTC)
    events = [
        (t0, "core", "viewed", "\\core\\event\\course_viewed", "course", "course", "s1"),
        (
            t0 + timedelta(minutes=15),
            "mod_resource",
            "viewed",
            "\\mod_resource\\event\\course_module_viewed",
            "resource",
            "course_module",
            "s1",
        ),
        (
            t0 + timedelta(days=9),
            "mod_forum",
            "created",
            "\\mod_forum\\event\\post_created",
            "forum",
            "post",
            "s2",
        ),
    ]

    def _run(run_id: str, ingested_step_sec: int) -> list[tuple[str, str, dict, list]]:
        state = InMemoryState()
        envelopes: list[dict] = []
        base_ing = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
        for idx, (ts, comp, act, evname, rtype, tgt, sess) in enumerate(events):
            msg = _canonical_dict(
                run_id=run_id,
                u="usr_det",
                t=ts,
                ingested_at=base_ing + timedelta(seconds=idx * ingested_step_sec),
                component=comp,
                action=act,
                raw_eventname=evname,
                resource_type=rtype,
                target=tgt,
                session_hash=sess,
            )
            envelopes.extend(handler.process_record(msg, state))

        eof = RunEofEvent(
            event_id=str(uuid4()),
            run_id=run_id,
            u="usr_det",
            course_id="course_105",
            emitted_at=base_ing + timedelta(seconds=999),
        ).model_dump(mode="json")
        envelopes.extend(handler.process_record(eof, state))

        feats = {
            (e["payload"]["granularity"], e["payload"]["window_id"]): e["payload"]["features"]
            for e in envelopes
            if e["_target"] == "features"
        }
        traces = {
            (e["payload"]["granularity"], e["payload"]["window_id"]): [
                (item["hle"], item["t"], item["a"]) for item in e["payload"]["trace"]
            ]
            for e in envelopes
            if e["_target"] == "traces"
        }
        return [
            (gran, wid, feats[(gran, wid)], traces[(gran, wid)])
            for gran, wid in sorted(feats)
        ]

    assert _run("run_10x", 10) == _run("run_max", 0)
