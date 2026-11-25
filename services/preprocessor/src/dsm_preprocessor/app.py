from __future__ import annotations

from pathlib import Path

from quixstreams import Application
from quixstreams.dataframe import StreamingDataFrame
from quixstreams.models.topics import TopicManager

from dsm_common.config import load_features_config, load_hle_catalog, load_windows_config
from dsm_common.messaging import Topics
from dsm_core.pipeline import window_partition_key
from dsm_preprocessor.config import PreprocessorSettings
from dsm_preprocessor.processor import PreprocessorHandler


def load_preprocessor_handler(config_dir: Path) -> PreprocessorHandler:
    hle_catalog = load_hle_catalog(config_dir / "hle_catalog.yaml")
    features_cfg = load_features_config(config_dir / "features.yaml")
    windows_cfg = load_windows_config(config_dir / "windows.yaml")
    return PreprocessorHandler(hle_catalog, features_cfg, windows_cfg)


def build_application(
    settings: PreprocessorSettings | None = None,
    *,
    topic_manager: TopicManager | None = None,
) -> tuple[Application, StreamingDataFrame]:
    cfg = settings or PreprocessorSettings()
    cfg.preprocessor_state_dir.mkdir(parents=True, exist_ok=True)
    handler = load_preprocessor_handler(cfg.config_dir)

    app = Application(
        broker_address=cfg.kafka_bootstrap_servers,
        consumer_group=cfg.preprocessor_consumer_group,
        auto_offset_reset=cfg.preprocessor_auto_offset_reset,
        state_dir=str(cfg.preprocessor_state_dir),
        auto_create_topics=False,
        use_changelog_topics=cfg.preprocessor_use_changelog_topics,
        topic_manager=topic_manager,
    )

    canonical_topic = app.topic(
        Topics.CANONICAL_EVENTS,
        value_deserializer="json",
        key_deserializer="bytes",
    )
    features_topic = app.topic(
        Topics.FEATURES,
        value_serializer="json",
        key_serializer="str",
    )
    traces_topic = app.topic(
        Topics.TRACES,
        value_serializer="json",
        key_serializer="str",
    )
    dlq_topic = app.topic(
        Topics.DLQ_EVENTS,
        value_serializer="json",
        key_serializer="str",
    )

    sdf = app.dataframe(canonical_topic)
    sdf = sdf.apply(handler.process_record, stateful=True, expand=True)

    features_sdf = sdf[sdf["_target"] == "features"].apply(lambda env: env["payload"])
    features_sdf.to_topic(
        features_topic,
        key=lambda payload: window_partition_key(payload["granularity"], payload["u"]),
    )

    traces_sdf = sdf[sdf["_target"] == "traces"].apply(lambda env: env["payload"])
    traces_sdf.to_topic(
        traces_topic,
        key=lambda payload: window_partition_key(payload["granularity"], payload["u"]),
    )

    dlq_sdf = sdf[sdf["_target"] == "dlq"].apply(lambda env: env["payload"])
    dlq_sdf.to_topic(dlq_topic, key=lambda payload: payload["dlq_id"])

    return app, sdf
