from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler


def features_to_matrix(
    feature_dicts: Sequence[dict[str, float]],
    *,
    feature_names: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    if not feature_dicts:
        return np.empty((0, 0), dtype=float), []
    names = (
        list(feature_names)
        if feature_names is not None
        else sorted({key for d in feature_dicts for key in d})
    )
    matrix = np.array(
        [[float(d.get(col, 0.0)) for col in names] for d in feature_dicts],
        dtype=float,
    )
    return matrix, names


def compute_silhouette(
    feature_dicts: Sequence[dict[str, float]],
    labels: Sequence[int],
    *,
    scale: bool = True,
) -> float | None:
    if len(feature_dicts) != len(labels) or len(labels) < 3:
        return None

    valid_indices = [idx for idx, lbl in enumerate(labels) if lbl >= 0]
    if len(valid_indices) < 3:
        return None

    valid_labels = [labels[idx] for idx in valid_indices]
    unique_labels = set(valid_labels)
    if len(unique_labels) < 2 or len(unique_labels) >= len(valid_labels):
        return None

    filtered_features = [feature_dicts[idx] for idx in valid_indices]
    matrix, _ = features_to_matrix(filtered_features)
    if matrix.shape[1] == 0:
        return None

    if scale:
        matrix = StandardScaler().fit_transform(matrix)

    return round(float(silhouette_score(matrix, valid_labels)), 6)


def compute_ari(labels_a: Sequence[int], labels_b: Sequence[int]) -> float | None:
    if len(labels_a) != len(labels_b) or len(labels_a) < 2:
        return None
    return round(float(adjusted_rand_score(labels_a, labels_b)), 6)
