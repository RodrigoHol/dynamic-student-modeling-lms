from __future__ import annotations

import asyncio
import json
import signal
from typing import Any

from aiokafka import AIOKafkaConsumer

from dsm_common.config import load_process_mining_config
from dsm_common.messaging import KafkaEventProducer, Topics
from dsm_common.observability import start_observability_server
from dsm_common.storage import Neo4jGraphRepository
from dsm_core.process_mining import ProcessMiningEngine
from dsm_process_mining.config import ProcessMiningServiceSettings
from dsm_process_mining.processor import ProcessMiningServiceProcessor


def build_engine(settings: ProcessMiningServiceSettings) -> ProcessMiningEngine:
    config = load_process_mining_config(settings.config_dir / "process_mining.yaml")
    return ProcessMiningEngine(config)


def _decode_json_payload(raw_bytes: bytes | None) -> Any:
    if raw_bytes is None:
        return None
    return json.loads(raw_bytes.decode("utf-8"))


async def run_service(
    settings: ProcessMiningServiceSettings,
    *,
    stop_event: asyncio.Event | None = None,
) -> None:
    engine = build_engine(settings)
    repository = Neo4jGraphRepository(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password,
    )
    producer = KafkaEventProducer(settings.kafka_bootstrap_servers)
    processor = ProcessMiningServiceProcessor(engine, repository, producer)

    consumer = AIOKafkaConsumer(
        Topics.TRACES,
        Topics.ASSIGNMENTS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.process_mining_consumer_group,
        auto_offset_reset=settings.process_mining_auto_offset_reset,
        enable_auto_commit=False,
    )

    shutdown_event = stop_event or asyncio.Event()
    await repository.ensure_constraints()
    await producer.start()
    await consumer.start()
    try:
        while not shutdown_event.is_set():
            batches = await consumer.getmany(timeout_ms=1000)
            if not batches:
                continue

            traces_batch: list[Any] = []
            assignments_batch: list[Any] = []
            for tp, records in batches.items():
                for record in records:
                    try:
                        payload = _decode_json_payload(record.value)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raw_repr = (
                            record.value.decode("utf-8", errors="replace")
                            if isinstance(record.value, bytes)
                            else record.value
                        )
                        kind = "trace" if tp.topic == Topics.TRACES else "assignment"
                        await processor._send_to_dlq(
                            {"raw_value": raw_repr},
                            f"JSON inválido en {tp.topic}: {exc}",
                            kind=kind,
                        )
                        continue
                    if tp.topic == Topics.TRACES:
                        traces_batch.append(payload)
                    else:
                        assignments_batch.append(payload)

            await processor.process_batch(traces_batch, assignments_batch)
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


def main_async(settings: ProcessMiningServiceSettings | None = None) -> None:
    cfg = settings or ProcessMiningServiceSettings()
    server = start_observability_server(
        "process-mining",
        cfg.process_mining_metrics_host,
        cfg.process_mining_metrics_port,
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
