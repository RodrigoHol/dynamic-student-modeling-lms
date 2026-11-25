from pathlib import Path

from dsm_common.config import (
    AppSettings,
    compute_yaml_hash,
    load_clustering_config,
    load_features_config,
    load_hle_catalog,
    load_process_mining_config,
    load_windows_config,
)

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def test_load_all_project_yaml_configs() -> None:
    hle = load_hle_catalog(CONFIG_DIR / "hle_catalog.yaml")
    features = load_features_config(CONFIG_DIR / "features.yaml")
    windows = load_windows_config(CONFIG_DIR / "windows.yaml")
    clustering = load_clustering_config(CONFIG_DIR / "clustering.yaml")
    pm = load_process_mining_config(CONFIG_DIR / "process_mining.yaml")

    assert hle.status == "PROVISIONAL"
    assert len(hle.rules) >= 6
    assert "regularity_index" in features.enabled_extractors
    assert windows.active_granularities == ["daily", "weekly", "monthly", "course"]
    assert clustering.algorithm == "denstream"
    assert pm.algorithm == "dfg"
    assert len(compute_yaml_hash(CONFIG_DIR / "hle_catalog.yaml")) == 64


def test_app_settings_defaults() -> None:
    settings = AppSettings()
    assert settings.gateway_port == 8000
    assert settings.kafka_bootstrap_servers == "localhost:9092"


def test_clustering_config_effective_params_switches_by_algorithm() -> None:
    clustering = load_clustering_config(CONFIG_DIR / "clustering.yaml")
    den_params = clustering.effective_params()
    assert "epsilon" in den_params

    switched = clustering.model_copy(update={"algorithm": "dbstream"})
    db_params = switched.effective_params()
    assert "clustering_threshold" in db_params
    assert "epsilon" not in db_params
