from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

from aiokafka import AIOKafkaConsumer

from dsm_clustering.config import ClusteringServiceSettings
from dsm_clustering.processor import ClusteringServiceProcessor
from dsm_common.config import load_clustering_config
from dsm_common.messaging import KafkaEventProducer, Topics
from dsm_common.observability import start_observability_server
from dsm_common.storage import MongoProfileRepository
from dsm_core.clustering import ClusteringEngine


def build_engine(settings: ClusteringServiceSettings) -> ClusteringEngine:
    config = load_clustering_config(settings.config_dir / "clustering.yaml")
    return ClusteringEngine(config)


def _decode_json_payload(raw_bytes: bytes | None) -> Any:
    if raw_bytes is None:
        return None
    return json.loads(raw_bytes.decode("utf-8"))


async def run_service(
    settings: ClusteringServiceSettings,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    engine = build_engine(settings)
    repository = MongoProfileRepository(settings.mongo_uri, settings.mongo_db)
    producer = KafkaEventProducer(settings.kafka_bootstrap_servers)
    processor = ClusteringServiceProcessor(engine, repository, producer)

    consumer = AIOKafkaConsumer(
        Topics.FEATURES,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.clustering_consumer_group,
        auto_offset_reset=settings.clustering_auto_offset_reset,
        enable_auto_commit=False,
    )

    shutdown_event = stop_event or asyncio.Event()
    await producer.start()
    await consumer.start()
    try:
        while not shutdown_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000)
            if not batches:
                continue
            for records in batches.values():
                for record in records:
                    try:
                        payload = _decode_json_payload(record.value)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raw_repr = (
                            record.value.decode("utf-8", errors="replace")
                            if isinstance(record.value, bytes)
                            else record.value
                        )
                        await processor._send_to_dlq(
                            {"raw_value": raw_repr},
                            f"JSON inválido en analytics.features: {exc}",
                        )
                        continue
                    await processor.handle_raw_payload(payload)
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()
        await repository.close()


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_event: asyncio.Event,
) -> None:
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: stop_event.set())


def main_async(settings: ClusteringServiceSettings | None = None) -> None:
    cfg = settings or ClusteringServiceSettings()
    server = start_observability_server(
        "clustering",
        cfg.clustering_metrics_host,
        cfg.clustering_metrics_port,
    )

    async def _runner() -> None:
        stop_event = asyncio.Event()
        _install_signal_handlers(asyncio.get_running_loop(), stop_event)
        await run_service(cfg, stop_event=stop_event)

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
