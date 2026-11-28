from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dsm_query_api.api import router
from dsm_query_api.config import QueryApiSettings
from dsm_query_api.repositories import PolyglotQueryRepository, QueryRepository
from dsm_query_api.websocket import ConnectionManager, KafkaAssignmentsWsBridge


def create_app(
    repository: QueryRepository | None = None,
    settings: QueryApiSettings | None = None,
    *,
    enable_ws_bridge: bool | None = None,
) -> FastAPI:
    active_settings = settings or QueryApiSettings()
    active_repo = repository or PolyglotQueryRepository(
        postgres_dsn=active_settings.postgres_dsn,
        mongo_uri=active_settings.mongo_uri,
        mongo_db=active_settings.mongo_db,
        neo4j_uri=active_settings.neo4j_uri,
        neo4j_user=active_settings.neo4j_user,
        neo4j_password=active_settings.neo4j_password,
    )
    ws_manager = ConnectionManager()
    bridge_enabled = (
        active_settings.query_enable_ws_kafka_bridge
        if enable_ws_bridge is None
        else enable_ws_bridge
    )
    ws_bridge = (
        KafkaAssignmentsWsBridge(
            active_settings.kafka_bootstrap_servers,
            active_settings.query_ws_consumer_group,
            ws_manager,
        )
        if bridge_enabled
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = active_settings
        application.state.repository = active_repo
        application.state.ws_manager = ws_manager
        application.state.ws_bridge = ws_bridge
        if active_settings.query_seed_demo_users:
            await active_repo.ensure_demo_users()
        if ws_bridge is not None:
            ws_bridge.start()
        try:
            yield
        finally:
            if ws_bridge is not None:
                await ws_bridge.stop()
            await active_repo.close()

    application = FastAPI(
        title="DSM Query API (C7)",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(router)
    return application


app = create_app()


def main() -> None:
    cfg = QueryApiSettings()
    uvicorn.run(
        "dsm_query_api.main:app",
        host=cfg.query_api_host,
        port=cfg.query_api_port,
    )


if __name__ == "__main__":
    main()
