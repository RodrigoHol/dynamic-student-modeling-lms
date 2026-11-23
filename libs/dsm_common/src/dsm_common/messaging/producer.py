"""Abstracciones de publicación de eventos hacia Apache Kafka."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from aiokafka import AIOKafkaProducer


@dataclass(slots=True)
class PublishedMessage:
    """Mensaje registrado en el productor en memoria."""

    topic: str
    key: str | None
    value: dict[str, Any]


class EventProducer(ABC):
    """Contrato común para productores asíncronos de eventos."""

    @abstractmethod
    async def start(self) -> None:
        """Inicializa la conexión con el broker."""

    @abstractmethod
    async def stop(self) -> None:
        """Cierra limpiamente los recursos del productor."""

    @abstractmethod
    async def publish(self, topic: str, key: str | None, value: dict[str, Any]) -> None:
        """Publica un evento serializable en JSON con clave de partición opcional."""


class KafkaEventProducer(EventProducer):
    """Productor asíncrono respaldado por Apache Kafka (aiokafka)."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        if self._producer is None:
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


class InMemoryEventProducer(EventProducer):
    """Productor en memoria para pruebas unitarias y de integración sin broker."""

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
