from datetime import UTC, datetime
from pathlib import Path

from dsm_common.config import load_hle_catalog
from dsm_common.schemas import CanonicalEvent, EventMetadata, ResourceInfo
from dsm_core.preprocessing import HLEMapper, NoiseFilter

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_event(
    *,
    action: str,
    component: str,
    raw_eventname: str,
    resource_type: str = "course_module",
    target: str | None = None,
) -> CanonicalEvent:
    now = datetime(2024, 9, 10, 12, 0, tzinfo=UTC)
    extra = {"target": target} if target is not None else {}
    return CanonicalEvent(
        event_id="evt-1",
        run_id="run_test",
        u="usr_abc123",
        a=action,
        r=ResourceInfo(resource_id="res_1", resource_type=resource_type),
        t=now,
        ingested_at=now,
        M=EventMetadata(
            course_id="course_105",
            source_format="moodle_csv",
            component=component,
            raw_eventname=raw_eventname,
            **extra,
        ),
    )


def test_noise_filter_detects_moodle_log_and_user_reports() -> None:
    catalog = load_hle_catalog(REPO_ROOT / "config" / "hle_catalog.yaml")
    noise_filter = NoiseFilter(catalog)

    log_noise = _make_event(
        action="viewed",
        component="core",
        raw_eventname="\\core\\event\\log_report_viewed",
        resource_type="report",
        target="log_report",
    )
    user_report_noise = _make_event(
        action="viewed",
        component="core",
        raw_eventname="\\core\\event\\course_user_report_viewed",
        resource_type="report",
    )
    valid_course_view = _make_event(
        action="viewed",
        component="core",
        raw_eventname="\\core\\event\\course_viewed",
        resource_type="course",
        target="course",
    )

    assert noise_filter.is_noise(log_noise) is True
    assert noise_filter.is_noise(user_report_noise) is True
    assert noise_filter.is_noise(valid_course_view) is False


def test_hle_mapper_covers_all_catalog_rules_and_default() -> None:
    catalog = load_hle_catalog(REPO_ROOT / "config" / "hle_catalog.yaml")
    mapper = HLEMapper(catalog)

    assert mapper.known_hles == (
        "ACCESO_CURSO",
        "CONSULTA_RECURSO",
        "PARTICIPACION_FORO",
        "ENVIO_TAREA",
        "INTENTO_CUESTIONARIO",
        "REVISION_RETROALIMENTACION",
        "OTRO",
    )

    cases = [
        (
            _make_event(
                action="viewed",
                component="core",
                raw_eventname="\\core\\event\\course_viewed",
                resource_type="course",
                target="course",
            ),
            "ACCESO_CURSO",
        ),
        (
            _make_event(
                action="viewed",
                component="mod_resource",
                raw_eventname="\\mod_resource\\event\\course_module_viewed",
                resource_type="resource",
                target="course_module",
            ),
            "CONSULTA_RECURSO",
        ),
        (
            _make_event(
                action="created",
                component="mod_forum",
                raw_eventname="\\mod_forum\\event\\post_created",
                resource_type="forum",
                target="post",
            ),
            "PARTICIPACION_FORO",
        ),
        (
            _make_event(
                action="submitted",
                component="mod_assign",
                raw_eventname="\\mod_assign\\event\\assessable_submitted",
                resource_type="assign",
                target="assessable",
            ),
            "ENVIO_TAREA",
        ),
        (
            _make_event(
                action="submitted",
                component="mod_quiz",
                raw_eventname="\\mod_quiz\\event\\attempt_submitted",
                resource_type="quiz",
                target="attempt",
            ),
            "INTENTO_CUESTIONARIO",
        ),
        (
            _make_event(
                action="viewed",
                component="gradereport_user",
                raw_eventname="\\gradereport_user\\event\\grade_report_viewed",
                resource_type="grade",
                target="grade",
            ),
            "REVISION_RETROALIMENTACION",
        ),
        (
            _make_event(
                action="exported",
                component="mod_glossary",
                raw_eventname="\\mod_glossary\\event\\entries_exported",
                resource_type="glossary",
                target="glossary",
            ),
            "OTRO",
        ),
    ]

    for event, expected_hle in cases:
        enriched = mapper.enrich_event(event)
        assert enriched.M.hle == expected_hle
