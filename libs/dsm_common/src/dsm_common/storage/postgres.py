"""Repositorio de corridas y snapshots de configuración en PostgreSQL (Sección 6.5)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import asyncpg
from pydantic import BaseModel, Field

from dsm_common.config.loader import (
    compute_yaml_hash,
    load_clustering_config,
    load_features_config,
    load_hle_catalog,
    load_process_mining_config,
    load_windows_config,
)


class RunRecord(BaseModel):
    """Registro operativo de una ejecución en la tabla `runs`."""

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
    """Carga y valida los cinco archivos YAML en `config_dir` para registrarlos por `run_id`."""
    hle_path = config_dir / "hle_catalog.yaml"
    features_path = config_dir / "features.yaml"
    windows_path = config_dir / "windows.yaml"
    clustering_path = config_dir / "clustering.yaml"
    pm_path = config_dir / "process_mining.yaml"

    hle = load_hle_catalog(hle_path)
    hle_hash = compute_yaml_hash(hle_path)
    features = load_features_config(features_path)
    windows = load_windows_config(windows_path)
    clustering = load_clustering_config(clustering_path)
    process_mining = load_process_mining_config(pm_path)

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
    """Contrato común para persistir el ciclo de vida de corridas en PostgreSQL."""

    @abstractmethod
    async def start_run(
        self,
        *,
        run_id: str,
        mode: Literal["stream", "batch"],
        source_dataset: str,
        speed_factor: str | None,
        config_snapshot: RunConfigSnapshot | None = None,
    ) -> RunRecord:
        """Inserta la corrida en estado `running` y opcionalmente su `run_configs`."""

    @abstractmethod
    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord:
        """Marca la corrida como `completed` y registra el total de eventos procesados."""

    @abstractmethod
    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord:
        """Marca la corrida como `failed` y registra los eventos procesados hasta el fallo."""

    @abstractmethod
    async def get_run(self, run_id: str) -> RunRecord | None:
        """Obtiene una corrida por `run_id`, o `None` si no existe."""

    @abstractmethod
    async def close(self) -> None:
        """Cierra las conexiones subyacentes del repositorio."""


class PostgresRunRepository(RunRepository):
    """Implementación asíncrona sobre PostgreSQL usando `asyncpg`."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._conn: asyncpg.Connection | None = None

    async def _get_conn(self) -> asyncpg.Connection:
        if self._conn is None or self._conn.is_closed():
            self._conn = await asyncpg.connect(self._dsn)
        return self._conn

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
        conn = await self._get_conn()
        async with conn.transaction():
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
        assert row is not None
        return self._row_to_record(row)

    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord:
        conn = await self._get_conn()
        row = await conn.fetchrow(
            """
            UPDATE runs
            SET status = 'completed',
                events_processed = $2,
                finished_at = NOW()
            WHERE run_id = $1
            RETURNING run_id, mode, status, source_dataset, speed_factor,
                      events_processed, started_at, finished_at
            """,
            run_id,
            events_processed,
        )
        if row is None:
            raise KeyError(f"No existe la corrida '{run_id}' en la tabla runs.")
        return self._row_to_record(row)

    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord:
        conn = await self._get_conn()
        row = await conn.fetchrow(
            """
            UPDATE runs
            SET status = 'failed',
                events_processed = $2,
                finished_at = NOW()
            WHERE run_id = $1
            RETURNING run_id, mode, status, source_dataset, speed_factor,
                      events_processed, started_at, finished_at
            """,
            run_id,
            events_processed,
        )
        if row is None:
            raise KeyError(f"No existe la corrida '{run_id}' en la tabla runs.")
        return self._row_to_record(row)

    async def get_run(self, run_id: str) -> RunRecord | None:
        conn = await self._get_conn()
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
        if self._conn is not None and not self._conn.is_closed():
            await self._conn.close()
        self._conn = None


class InMemoryRunRepository(RunRepository):
    """Repositorio en memoria para pruebas unitarias y de integración sin PostgreSQL."""

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
            started_at=datetime.now(UTC),
            finished_at=None,
        )
        self.runs[run_id] = record
        if config_snapshot is not None:
            self.run_configs[run_id] = config_snapshot
        return record

    async def complete_run(self, run_id: str, *, events_processed: int) -> RunRecord:
        existing = self.runs.get(run_id)
        if existing is None:
            raise KeyError(f"No existe la corrida '{run_id}'.")
        updated = existing.model_copy(
            update={
                "status": "completed",
                "events_processed": events_processed,
                "finished_at": datetime.now(UTC),
            }
        )
        self.runs[run_id] = updated
        return updated

    async def fail_run(self, run_id: str, *, events_processed: int = 0) -> RunRecord:
        existing = self.runs.get(run_id)
        if existing is None:
            raise KeyError(f"No existe la corrida '{run_id}'.")
        updated = existing.model_copy(
            update={
                "status": "failed",
                "events_processed": events_processed,
                "finished_at": datetime.now(UTC),
            }
        )
        self.runs[run_id] = updated
        return updated

    async def get_run(self, run_id: str) -> RunRecord | None:
        return self.runs.get(run_id)

    async def close(self) -> None:
        return None
