from datetime import UTC, datetime, timedelta

from dsm_core.explainability import (
    OnlineFeatureStats,
    TransitionTracker,
    compute_top_contributing_features,
)


def test_online_feature_stats_welford_and_standardize() -> None:
    stats = OnlineFeatureStats()
    stats.update({"a": 10.0, "b": 5.0})
    stats.update({"a": 20.0, "b": 5.0})

    assert stats.count == 2
    assert stats.mean("a") == 15.0
    assert stats.std("a") == 5.0
    assert stats.std("b") == 0.0

    scaled = stats.standardize({"a": 20.0, "b": 5.0})
    assert scaled["a"] == 1.0
    assert scaled["b"] == 0.0

    restored = stats.unstandardize(scaled)
    assert restored["a"] == 20.0
    assert restored["b"] == 5.0


def test_compute_top_contributing_features_ranks_by_abs_z_score() -> None:
    stats = OnlineFeatureStats()
    for val in (10.0, 20.0):
        stats.update({"total_events": val, "active_days": 2.0, "regularity_index": 0.5})

    # En espacio estandarizado, total_events=20 -> +1.0 respecto a media 15
    centroid_scaled = {"total_events": -0.5, "active_days": 0.0, "regularity_index": 0.1}
    top = compute_top_contributing_features(
        {"total_events": 20.0, "active_days": 2.0, "regularity_index": 0.5},
        centroid_scaled,
        stats,
        is_outlier=False,
        scaled=True,
        top_k=2,
    )
    assert len(top) == 2
    assert top[0].feature == "total_events"
    assert top[0].z_score == 1.5

    # Caso de punto igual al centroide: recurre al z_score poblacional
    same_centroid = {"total_events": 1.0, "active_days": 0.0, "regularity_index": 0.0}
    fallback_top = compute_top_contributing_features(
        {"total_events": 20.0, "active_days": 2.0, "regularity_index": 0.5},
        same_centroid,
        stats,
        is_outlier=False,
        scaled=True,
        top_k=2,
    )
    assert fallback_top[0].feature == "total_events"
    assert fallback_top[0].z_score == 1.0

    # Caso outlier: usa z_score poblacional
    outlier_top = compute_top_contributing_features(
        {"total_events": 20.0, "active_days": 2.0, "regularity_index": 0.5},
        None,
        stats,
        is_outlier=True,
        scaled=True,
        top_k=2,
    )
    assert outlier_top[0].feature == "total_events"
    assert outlier_top[0].z_score == 1.0


def test_transition_tracker_detects_changes_and_stays_idempotent() -> None:
    tracker = TransitionTracker()
    w1 = datetime(2024, 9, 2, 0, 0, tzinfo=UTC)
    w2 = w1 + timedelta(days=7)
    w3 = w2 + timedelta(days=7)

    r1 = tracker.record(student_id="u1", window_id="2024-W36", window_start=w1, cluster_id=0)
    assert r1.previous_cluster_id is None
    assert r1.transition_detected is False

    # Reprocesar misma ventana mantiene previous_cluster_id=None
    r1_dup = tracker.record(student_id="u1", window_id="2024-W36", window_start=w1, cluster_id=0)
    assert r1_dup.previous_cluster_id is None
    assert r1_dup.transition_detected is False

    # Siguiente ventana cambia de 0 -> 2
    r2 = tracker.record(student_id="u1", window_id="2024-W37", window_start=w2, cluster_id=2)
    assert r2.previous_cluster_id == 0
    assert r2.transition_detected is True

    # Siguiente ventana permanece en 2
    r3 = tracker.record(student_id="u1", window_id="2024-W38", window_start=w3, cluster_id=2)
    assert r3.previous_cluster_id == 2
    assert r3.transition_detected is False
