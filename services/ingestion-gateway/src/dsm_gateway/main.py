"""Punto de entrada de la aplicación FastAPI para C2 Ingestion Gateway."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from dsm_common.config import AppSettings
from dsm_common.messaging import EventProducer, KafkaEventProducer
from dsm_gateway.api import router


def create_app(
    producer: EventProducer | None = None,
    settings: AppSettings | None = None,
) -> FastAPI:
    """Construye la aplicación FastAPI inyectando configuración y productor."""
    active_settings = settings or AppSettings()
    active_producer = producer or KafkaEventProducer(active_settings.kafka_bootstrap_servers)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = active_settings
        application.state.producer = active_producer
        await active_producer.start()
        try:
            yield
        finally:
            await active_producer.stop()

    application = FastAPI(
        title="DSM Ingestion Gateway (C2)",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
