from pathlib import Path

from quixstreams.models.topics import TopicConfig, TopicManager

from dsm_common.messaging import Topics
from dsm_preprocessor.app import build_application
from dsm_preprocessor.config import PreprocessorSettings

REPO_ROOT = Path(__file__).resolve().parents[3]


class _FakeTopicAdmin:
    def inspect_topics(
        self,
        topic_names: list[str],
        timeout: float = 30.0,
    ) -> dict[str, TopicConfig]:
        return {
            name: TopicConfig(
                num_partitions=3,
                replication_factor=1,
                extra_config={"retention.ms": "-1", "retention.bytes": "-1"},
            )
            for name in topic_names
        }


def test_build_application_wires_quix_topics_without_kafka(tmp_path: Path) -> None:
    settings = PreprocessorSettings(
        kafka_bootstrap_servers="localhost:9092",
        config_dir=REPO_ROOT / "config",
        preprocessor_state_dir=tmp_path / "rocksdb_state",
        preprocessor_use_changelog_topics=False,
    )
    fake_tm = TopicManager(
        topic_admin=_FakeTopicAdmin(),  # type: ignore[arg-type]
        consumer_group=settings.preprocessor_consumer_group,
        auto_create_topics=False,
    )
    app, sdf = build_application(settings, topic_manager=fake_tm)
    assert app is not None
    assert sdf is not None
    registered = app._topic_manager.topics
    assert Topics.CANONICAL_EVENTS in registered
    assert Topics.FEATURES in registered
    assert Topics.TRACES in registered
    assert Topics.DLQ_EVENTS in registered
