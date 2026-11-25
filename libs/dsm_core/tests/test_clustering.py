from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dsm_common.config import ClusteringConfig, load_clustering_config
from dsm_common.schemas import FeatureVectorMessage
from dsm_core.clustering import (
    CLUSTERING_REGISTRY,
    ClusteringEngine,
    DBSTREAMAdapter,
    DenStreamAdapter,
    create_clustering_model,
    resolve_clustering_params,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_vector(
    *,
    run_id: str = "run_t",
    u: str,
    granularity: str,
    window_id: str,
    window_start: datetime,
    features: dict[str, float],
    ingested_at: datetime,
) -> FeatureVectorMessage:
    return FeatureVectorMessage(
        run_id=run_id,
        course_id="course_105",
        u=u,
        granularity=granularity,
        window_id=window_id,
        window_start=window_start,
        window_end=window_start + timedelta(days=7),
        features_version="v0.1-provisional",
        hle_version="v0.1-provisional",
        features=features,
        event_count=int(features.get("total_events", 1.0)),
        last_event_ingested_at=ingested_at,
        emitted_at=ingested_at + timedelta(milliseconds=5),
    )


def test_registry_and_adapters_validation() -> None:
    assert "denstream" in CLUSTERING_REGISTRY
    assert "dbstream" in CLUSTERING_REGISTRY

    with pytest.raises(ValueError, match="no soportado"):
        create_clustering_model("kmeans")

    with pytest.raises(ValueError, match="Parámetros no soportados"):
        create_clustering_model("denstream", {"bad_param": 1.0})

    with pytest.raises(ValueError, match=r"mu \* beta > 1\.0"):
        DenStreamAdapter(mu=2.0, beta=0.5)

    cfg = ClusteringConfig(
        algorithm="dbstream",
        params={"decaying_factor": 0.05, "epsilon": 2.5},
    )
    resolved = resolve_clustering_params(cfg)
    assert "clustering_threshold" in resolved
    model = create_clustering_model(cfg.algorithm, resolved, seed=cfg.seed)
    assert isinstance(model, DBSTREAMAdapter)


def test_denstream_and_dbstream_adapters_cluster_two_groups() -> None:
    for algo_name, params in (
        (
            "denstream",
            {
                "decaying_factor": 0.05,
                "beta": 0.75,
                "mu": 2.0,
                "epsilon": 0.8,
                "n_samples_init": 6,
                "stream_speed": 100,
            },
        ),
        (
            "dbstream",
            {
                "clustering_threshold": 0.8,
                "fading_factor": 0.05,
                "cleanup_interval": 5,
                "intersection_factor": 0.3,
                "minimum_weight": 1.0,
            },
        ),
    ):
        model = create_clustering_model(algo_name, params, seed=42)
        if algo_name == "denstream":
            assert model.predict_one({"x": 0.0, "y": 0.0}) == -1

        for idx in range(12):
            pt = {"x": 0.0 + (idx % 2) * 0.05, "y": 0.0} if idx % 2 == 0 else {"x": 5.0, "y": 5.0}
            model.learn_one(pt)

        c_low = model.predict_one({"x": 0.0, "y": 0.0})
        c_high = model.predict_one({"x": 5.0, "y": 5.0})
        assert c_low >= 0
        assert c_high >= 0
        assert c_low != c_high
        assert model.get_centroid(c_low) is not None
        snap = model.snapshot()
        assert snap["algorithm"] == algo_name
        assert snap["cluster_count"] >= 2


@pytest.mark.parametrize("algorithm", ["denstream", "dbstream"])
def test_clustering_engine_isolates_granularities_and_tracks_transitions(algorithm: str) -> None:
    base_cfg = load_clustering_config(REPO_ROOT / "config" / "clustering.yaml")
    cfg = base_cfg.model_copy(update={"algorithm": algorithm})
    engine = ClusteringEngine(cfg)

    base_t = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    ingested = datetime(2026, 11, 25, 1, 0, tzinfo=UTC)
    processed = ingested + timedelta(milliseconds=42)

    low_feats = {
        "total_events": 3.0,
        "active_days": 1.0,
        "hle_acceso_curso_count": 2.0,
        "hle_consulta_recurso_count": 1.0,
        "hle_participacion_foro_count": 0.0,
        "hle_envio_tarea_count": 0.0,
        "hle_intento_cuestionario_count": 0.0,
        "hle_revision_retroalimentacion_count": 0.0,
        "regularity_index": 0.1,
        "session_count": 1.0,
        "mean_session_duration_sec": 120.0,
    }
    high_feats = {
        "total_events": 45.0,
        "active_days": 6.0,
        "hle_acceso_curso_count": 10.0,
        "hle_consulta_recurso_count": 18.0,
        "hle_participacion_foro_count": 8.0,
        "hle_envio_tarea_count": 4.0,
        "hle_intento_cuestionario_count": 3.0,
        "hle_revision_retroalimentacion_count": 2.0,
        "regularity_index": 0.9,
        "session_count": 9.0,
        "mean_session_duration_sec": 1800.0,
    }

    results = []
    # 24 vectores semanales (6 semanas x 4 estudiantes): u_0 y u_2 empiezan bajos,
    # u_1 y u_3 empiezan altos; desde la semana 3, u_0 pasa a perfil alto (transición).
    for week in range(6):
        w_start = base_t + timedelta(weeks=week)
        for idx in range(4):
            uid = f"u_{idx}"
            is_high = (idx in {1, 3}) or (uid == "u_0" and week >= 3)
            base_feats = high_feats if is_high else low_feats
            # Pequeña variación realista por semana
            feats = {**base_feats, "total_events": base_feats["total_events"] + float(week % 2)}
            vec = _make_vector(
                u=uid,
                granularity="weekly",
                window_id=f"2024-W{36 + week}",
                window_start=w_start,
                features=feats,
                ingested_at=ingested,
            )
            results.append(engine.process_vector(vec, processed_at=processed))

    daily_res = engine.process_vector(
        _make_vector(
            u="u_0",
            granularity="daily",
            window_id="2024-09-02",
            window_start=base_t,
            features=high_feats,
            ingested_at=ingested,
        ),
        processed_at=processed,
    )

    # El estado diario no debe haber heredado el previous_cluster_id del semanal
    assert daily_res.profile.granularity == "daily"
    assert daily_res.profile.clustering.previous_cluster_id is None
    assert daily_res.profile.latencies_ms.ingested_to_profile == 42
    assert len(daily_res.profile.explainability.top_contributing_features) <= 3

    weekly_clusters = {
        r.profile.clustering.cluster_id
        for r in results
        if not r.profile.clustering.is_outlier
    }
    assert len(weekly_clusters) >= 2
    assert any(r.profile.clustering.transition_detected for r in results)
    assert results[-1].snapshot.algorithm == algorithm
    assert results[-1].snapshot.cluster_count >= 2
