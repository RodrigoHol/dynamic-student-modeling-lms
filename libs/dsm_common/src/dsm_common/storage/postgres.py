from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from dsm_common.config.loader import (
    compute_yaml_hash,
    load_clustering_config,
    load_features_config,
    load_hle_catalog,
    load_process_mining_config,
    load_windows_config,
)
from dsm_common.time import utc_now

if TYPE_CHECKING:
    import asyncpg


class RunRecord(BaseModel):
    run_id: str
    mode: Literal["stream", "batch"]
    status: Literal["running", "completed", "failed"]
    source_dataset: str
    speed_factor: str | None = None
    events_processed: int = 0
    started_at: datetime
    finished_at: datetime | None = None


class RunConfigSnapshot(BaseModel):
    """Fotografía inmutable de los YAML analíticos asociados a una corrida (RF-19)."""

    hle_version: str
    hle_yaml_hash: str = Field(..., min_length=64, max_length=64)
    hle_rules_json: list[dict[str, Any]]
    hle_is_provisional: bool = True
    clustering_algorithm: str
    clustering_params: dict[str, Any] = Field(default_factory=dict)
    seed: int
    active_granularities: list[str]
    windows_config: dict[str, Any]
    features_version: str
    features_list: list[str]
    raw_yaml_snapshot: dict[str, Any] = Field(default_factory=dict)


def load_run_config_snapshot(config_dir: Path) -> RunConfigSnapshot:
    hle_path = config_dir / "hle_catalog.yaml"
    hle = load_hle_catalog(hle_path)
    hle_hash = compute_yaml_hash(hle_path)
    features = load_features_config(config_dir / "features.yaml")
    windows = load_windows_config(config_dir / "windows.yaml")
    clustering = load_clustering_config(config_dir / "clustering.yaml")
    process_mining = load_process_mining_config(config_dir / "process_mining.yaml")

    return RunConfigSnapshot(
        hle_version=hle.version,
        hle_yaml_hash=hle_hash,
        hle_rules_json=[rule.model_dump(mode="json") for rule in hle.rules],
        hle_is_provisional=hle.status.upper() == "PROVISIONAL",
        clustering_algorithm=clustering.algorithm,
        clustering_params=clustering.params,
        seed=clustering.seed,
        active_granularities=windows.active_granularities,
        windows_config=windows.model_dump(mode="json"),
        features_version=features.version,
        features_list=features.enabled_extractors,
        raw_yaml_snapshot={
            "hle_catalog": hle.model_dump(mode="json"),
            "features": features.model_dump(mode="json"),
            "windows": windows.model_dump(mode="json"),
            "clustering": clustering.model_dump(mode="json"),
            "process_mining": process_mining.model_dump(mode="json"),
        },
    )


class RunRepository(ABC):
    @abstractmethod
    async def start_run(
        self,
        *,
        run_id: str,
        mode: Literal["stream", "batch"],
        source_dataset: str,
        speed_factor: str | None,
        config_snapshot: RunConfigSnapshot | None = None,
    ) -> RunRecord: ...

    @abstractmethod
    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord: ...

    @abstractmethod
    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord: ...

    @abstractmethod
    async def get_run(self, run_id: str) -> RunRecord | None: ...

    @abstractmethod
    async def close(self) -> None: ...


class PostgresRunRepository(RunRepository):
    def __init__(self, dsn: str, *, min_pool_size: int = 1, max_pool_size: int = 5) -> None:
        self._dsn = dsn
        self._min_pool_size = min_pool_size
        self._max_pool_size = max_pool_size
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    import asyncpg

                    self._pool = await asyncpg.create_pool(
                        self._dsn,
                        min_size=self._min_pool_size,
                        max_size=self._max_pool_size,
                    )
        return self._pool

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            mode=row["mode"],
            status=row["status"],
            source_dataset=row["source_dataset"],
            speed_factor=row["speed_factor"],
            events_processed=row["events_processed"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
        )

    async def start_run(
        self,
        *,
        run_id: str,
        mode: Literal["stream", "batch"],
        source_dataset: str,
        speed_factor: str | None,
        config_snapshot: RunConfigSnapshot | None = None,
    ) -> RunRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO runs (
                    run_id, mode, status, source_dataset, speed_factor, events_processed
                )
                VALUES ($1, $2, 'running', $3, $4, 0)
                RETURNING run_id, mode, status, source_dataset, speed_factor,
                          events_processed, started_at, finished_at
                """,
                run_id,
                mode,
                source_dataset,
                speed_factor,
            )
            if row is None:
                raise RuntimeError(f"No se pudo registrar la corrida '{run_id}' en runs.")
            if config_snapshot is not None:
                await conn.execute(
                    """
                    INSERT INTO hle_catalog_versions (
                        hle_version, yaml_hash, rules_json, is_provisional
                    )
                    VALUES ($1, $2, $3::jsonb, $4)
                    ON CONFLICT (hle_version) DO NOTHING
                    """,
                    config_snapshot.hle_version,
                    config_snapshot.hle_yaml_hash,
                    json.dumps(config_snapshot.hle_rules_json),
                    config_snapshot.hle_is_provisional,
                )
                await conn.execute(
                    """
                    INSERT INTO run_configs (
                        run_id,
                        clustering_algorithm,
                        clustering_params_json,
                        seed,
                        active_granularities_json,
                        windows_config_json,
                        features_version,
                        features_list_json,
                        hle_version,
                        raw_yaml_snapshot
                    )
                    VALUES (
                        $1, $2, $3::jsonb, $4, $5::jsonb, $6::jsonb, $7, $8::jsonb, $9, $10::jsonb
                    )
                    """,
                    run_id,
                    config_snapshot.clustering_algorithm,
                    json.dumps(config_snapshot.clustering_params),
                    config_snapshot.seed,
                    json.dumps(config_snapshot.active_granularities),
                    json.dumps(config_snapshot.windows_config),
                    config_snapshot.features_version,
                    json.dumps(config_snapshot.features_list),
                    config_snapshot.hle_version,
                    json.dumps(config_snapshot.raw_yaml_snapshot),
                )
        return self._row_to_record(row)

    async def _update_status(
        self,
        run_id: str,
        status: Literal["completed", "failed"],
        *,
        events_processed: int,
    ) -> RunRecord:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE runs
                SET status = $2,
                    events_processed = $3,
                    finished_at = NOW()
                WHERE run_id = $1
                RETURNING run_id, mode, status, source_dataset, speed_factor,
                          events_processed, started_at, finished_at
                """,
                run_id,
                status,
                events_processed,
            )
        if row is None:
            raise KeyError(f"No existe la corrida '{run_id}' en la tabla runs.")
        return self._row_to_record(row)

    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord:
        return await self._update_status(
            run_id,
            "completed",
            events_processed=events_processed,
        )

    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord:
        return await self._update_status(
            run_id,
            "failed",
            events_processed=events_processed,
        )

    async def get_run(self, run_id: str) -> RunRecord | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT run_id, mode, status, source_dataset, speed_factor,
                       events_processed, started_at, finished_at
                FROM runs
                WHERE run_id = $1
                """,
                run_id,
            )
        return self._row_to_record(row) if row is not None else None

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


class InMemoryRunRepository(RunRepository):
    def __init__(self) -> None:
        self.runs: dict[str, RunRecord] = {}
        self.run_configs: dict[str, RunConfigSnapshot] = {}

    async def start_run(
        self,
        *,
        run_id: str,
        mode: Literal["stream", "batch"],
        source_dataset: str,
        speed_factor: str | None,
        config_snapshot: RunConfigSnapshot | None = None,
    ) -> RunRecord:
        if run_id in self.runs:
            raise ValueError(f"La corrida '{run_id}' ya existe.")
        record = RunRecord(
            run_id=run_id,
            mode=mode,
            status="running",
            source_dataset=source_dataset,
            speed_factor=speed_factor,
            events_processed=0,
            started_at=utc_now(),
            finished_at=None,
        )
        self.runs[run_id] = record
        if config_snapshot is not None:
            self.run_configs[run_id] = config_snapshot
        return record

    def _update_status(
        self,
        run_id: str,
        status: Literal["completed", "failed"],
        *,
        events_processed: int,
    ) -> RunRecord:
        existing = self.runs.get(run_id)
        if existing is None:
            raise KeyError(f"No existe la corrida '{run_id}'.")
        updated = existing.model_copy(
            update={
                "status": status,
                "events_processed": events_processed,
                "finished_at": utc_now(),
            }
        )
        self.runs[run_id] = updated
        return updated

    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord:
        return self._update_status(run_id, "completed", events_processed=events_processed)

    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord:
        return self._update_status(run_id, "failed", events_processed=events_processed)

    async def get_run(self, run_id: str) -> RunRecord | None:
        return self.runs.get(run_id)

    async def close(self) -> None:
        return None
