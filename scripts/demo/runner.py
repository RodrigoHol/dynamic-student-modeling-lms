from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aiokafka import AIOKafkaConsumer

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"
SYNTHETIC_DATASET = REPO_ROOT / "data" / "synthetic" / "synthetic_course_5000.jsonl"
PHASE3_DATASET = REPO_ROOT / "data" / "synthetic" / "phase3_determinism.jsonl"
PREPROCESSOR_URL = "http://localhost:8004"

VENV_SCRIPTS = REPO_ROOT / ".venv" / "Scripts"
PYTEST_BIN = VENV_SCRIPTS / "pytest.exe"
RUFF_BIN = VENV_SCRIPTS / "ruff.exe"
REPLAYER_BIN = VENV_SCRIPTS / "dsm-replayer.exe"


def print_header(title: str) -> None:
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"El comando falló con código {result.returncode}: {' '.join(cmd)}")
    return result


def run_capture(cmd: list[str]) -> str:
    print(f"\n> {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"El comando falló con código {result.returncode}: {' '.join(cmd)}")
    return result.stdout


def compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


async def collect_topic_records(
    bootstrap_servers: str,
    topic: str,
    predicate: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    # En scripts de verificación acotados se lee hasta end_offsets con getmany(timeout_ms=2000).
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    await consumer.start()
    collected: list[dict[str, Any]] = []
    try:
        partitions = sorted(consumer.assignment(), key=lambda tp: tp.partition)
        if not partitions:
            raise RuntimeError(f"No se encontraron particiones asignadas en {topic}.")
        await consumer.seek_to_beginning(*partitions)
        end_offsets = await consumer.end_offsets(partitions)
        while True:
            positions = {tp: await consumer.position(tp) for tp in partitions}
            if all(positions[tp] >= end_offsets[tp] for tp in partitions):
                break
            batches = await consumer.getmany(timeout_ms=2000)
            if not batches:
                break
            for records in batches.values():
                for msg in records:
                    val = msg.value
                    if isinstance(val, dict) and predicate(val):
                        collected.append(val)
    finally:
        await consumer.stop()
    return collected
