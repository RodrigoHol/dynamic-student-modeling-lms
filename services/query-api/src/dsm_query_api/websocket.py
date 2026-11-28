from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import Any

from aiokafka import AIOKafkaConsumer
from fastapi import WebSocket

from dsm_common.messaging import Topics
from dsm_common.schemas import ClusterAssignmentMessage
from dsm_query_api.metrics import QUERY_WS_CONNECTIONS
from dsm_query_api.schemas import WsWindowUpdateEvent


class ConnectionManager:
    """Administra clientes WebSocket suscritos por ``run_id`` o canal global."""

    def __init__(self) -> None:
        self._channels: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, channel: str = "*") -> None:
        await websocket.accept()
        async with self._lock:
            self._channels[channel].add(websocket)
            total = sum(len(clients) for clients in self._channels.values())
        QUERY_WS_CONNECTIONS.set(total)

    async def disconnect(self, websocket: WebSocket, channel: str = "*") -> None:
        async with self._lock:
            clients = self._channels.get(channel)
            if clients is not None:
                clients.discard(websocket)
                if not clients:
                    del self._channels[channel]
            total = sum(len(c) for c in self._channels.values())
        QUERY_WS_CONNECTIONS.set(total)

    async def broadcast_update(self, event: WsWindowUpdateEvent) -> int:
        payload = event.model_dump(mode="json")
        async with self._lock:
            targets = list(self._channels.get(event.run_id, set())) + list(
                self._channels.get("*", set())
            )
        sent = 0
        for ws in targets:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                continue
        return sent


class KafkaAssignmentsWsBridge:
    """Puente en segundo plano de ``analytics.assignments`` hacia clientes WebSocket."""

    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str,
        manager: ConnectionManager,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._consumer_group = consumer_group
        self._manager = manager
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def _run(self) -> None:
        consumer = AIOKafkaConsumer(
            Topics.ASSIGNMENTS,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._consumer_group,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        try:
            await consumer.start()
        except Exception:
            return
        try:
            while not self._stop_event.is_set():
                batches = await consumer.getmany(timeout_ms=1000)
                if not batches:
                    continue
                for records in batches.values():
                    for record in records:
                        try:
                            raw: Any = json.loads(record.value.decode("utf-8"))
                            msg = ClusterAssignmentMessage.model_validate(raw)
                        except Exception:
                            continue
                        event = WsWindowUpdateEvent(
                            run_id=msg.run_id,
                            course_id=msg.course_id,
                            granularity=msg.granularity,
                            window_id=msg.window_id,
                            student_id=msg.u,
                            cluster_id=msg.cluster_id,
                            transition_detected=msg.transition_detected,
                            emitted_at=msg.emitted_at,
                        )
                        await self._manager.broadcast_update(event)
        finally:
            await consumer.stop()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
