from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiokafka import AIOKafkaProducer


@dataclass(slots=True)
class PublishedMessage:
    topic: str
    key: str | None
    value: dict[str, Any]


class EventProducer(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None: ...

    @abstractmethod
    async def publish_batch(self, messages: Sequence[PublishedMessage]) -> None: ...


class KafkaEventProducer(EventProducer):
    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is None:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                acks="all",
            )
            await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaEventProducer no ha sido iniciado con start().")
        await self._producer.send_and_wait(topic, key=key, value=value)

    async def publish_batch(self, messages: Sequence[PublishedMessage]) -> None:
        if not messages:
            return
        if self._producer is None:
            raise RuntimeError("KafkaEventProducer no ha sido iniciado con start().")
        futures = [
            await self._producer.send(msg.topic, key=msg.key, value=msg.value) for msg in messages
        ]
        await asyncio.gather(*futures)


class InMemoryEventProducer(EventProducer):
    def __init__(self) -> None:
        self.started: bool = False
        self.messages: list[PublishedMessage] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        if not self.started:
            raise RuntimeError("InMemoryEventProducer no ha sido iniciado con start().")
        self.messages.append(PublishedMessage(topic=topic, key=key, value=value))

    async def publish_batch(self, messages: Sequence[PublishedMessage]) -> None:
        if not self.started:
            raise RuntimeError("InMemoryEventProducer no ha sido iniciado con start().")
        self.messages.extend(messages)
