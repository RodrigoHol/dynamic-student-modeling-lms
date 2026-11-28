from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from neo4j import AsyncGraphDatabase
from pymongo import AsyncMongoClient

from demo.runner import (
    PHASE5_DATASET,
    PROCESS_MINING_URL,
    REPLAYER_BIN,
    REPO_ROOT,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings, load_process_mining_config
from dsm_common.messaging import Topics

EXPECTED_GRANULARITIES = {"daily", "weekly", "monthly", "course"}

_NEO4J_RUN_EDGES_CYPHER = """
MATCH (src)-[r:DFG {run_id: $run_id}]->(dst)
RETURN
    r.granularity AS granularity,
    r.window_id AS window_id,
    r.scope AS scope,
    r.scope_id AS scope_id,
    CASE WHEN src:Boundary THEN src.name ELSE src.hle_code END AS source,
    CASE WHEN src:Boundary THEN 'boundary' ELSE 'activity' END AS source_kind,
    CASE WHEN dst:Boundary THEN dst.name ELSE dst.hle_code END AS target,
    CASE WHEN dst:Boundary THEN 'boundary' ELSE 'activity' END AS target_kind,
    r.freq AS freq,
    r.total_time_sec AS total_time_sec,
    r.mean_time_sec AS mean_time_sec,
    r.trace_support_count AS trace_support_count,
    r.support AS support,
    r.trace_count AS trace_count
""".strip()


async def _wait_for_c6_health(timeout_seconds: float = 30.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    async with httpx.AsyncClient(base_url=PROCESS_MINING_URL, timeout=5.0) as client:
        while loop.time() < deadline:
            try:
                resp = await client.get("/health")
                if resp.status_code == 200 and resp.json().get("status") == "ok":
                    print(f"C6 /health -> {resp.status_code} {resp.json()}")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    raise RuntimeError(
        "C6 Process Mining Engine no respondió /health == 200 dentro del timeout."
    )


async def _fetch_mongo_cluster_members(
    settings: AppSettings,
    run_id: str,
    *,
    expected_students: int = 30,
    timeout_seconds: float = 60.0,
) -> dict[tuple[str, str, str], set[str]]:
    client = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    db = client[settings.mongo_db]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    profiles: list[dict[str, Any]] = []
    try:
        while loop.time() < deadline:
            profiles = await db["student_profiles"].find({"run_id": run_id}).to_list(length=None)
            course_students = {
                doc["student_id"] for doc in profiles if doc.get("granularity") == "course"
            }
            grans = {doc.get("granularity") for doc in profiles}
            if len(course_students) >= expected_students and grans == EXPECTED_GRANULARITIES:
                break
            await asyncio.sleep(1.0)
    finally:
        await client.close()

    if not profiles:
        raise RuntimeError(
            f"No se encontraron perfiles en MongoDB para '{run_id}' (necesarios desde C5)."
        )

    members: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for doc in profiles:
        cid = str(doc["clustering"]["cluster_id"])
        members[(doc["granularity"], doc["window_id"], cid)].add(doc["student_id"])
    return dict(members)


async def _wait_and_fetch_neo4j_edges(
    settings: AppSettings,
    run_id: str,
    cluster_members: dict[tuple[str, str, str], set[str]],
    *,
    timeout_seconds: float = 120.0,
) -> list[dict[str, Any]]:
    expected_student_keys = {
        (gran, wid, sid)
        for (gran, wid, _cid), sids in cluster_members.items()
        for sid in sids
    }
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    rows: list[dict[str, Any]] = []
    try:
        while loop.time() < deadline:
            async with driver.session() as session:
                result = await session.run(_NEO4J_RUN_EDGES_CYPHER, run_id=run_id)
                rows = await result.data()

            student_keys_seen = {
                (r["granularity"], r["window_id"], r["scope_id"])
                for r in rows
                if r["scope"] == "student"
            }
            cluster_trace_counts: dict[tuple[str, str, str], int] = {}
            for r in rows:
                if r["scope"] == "cluster":
                    cluster_trace_counts[(r["granularity"], r["window_id"], r["scope_id"])] = int(
                        r["trace_count"]
                    )

            all_students_ready = expected_student_keys.issubset(student_keys_seen)
            all_clusters_ready = all(
                cluster_trace_counts.get(ckey) == len(sids)
                for ckey, sids in cluster_members.items()
            )
            if rows and all_students_ready and all_clusters_ready:
                return rows
            await asyncio.sleep(1.0)
    finally:
        await driver.close()

    raise RuntimeError(
        f"Neo4j no consolidó todos los grafos DFG de '{run_id}' dentro del timeout "
        f"(aristas encontradas={len(rows)})."
    )


def _verify_additive_consistency(
    rows: list[dict[str, Any]],
    cluster_members: dict[tuple[str, str, str], set[str]],
    *,
    min_edge_frequency: int,
    include_boundaries: bool,
) -> dict[str, dict[str, int]]:
    student_edges: dict[
        tuple[str, str, str],
        dict[tuple[str, str, str, str], tuple[int, float]],
    ] = defaultdict(dict)
    cluster_edges: dict[
        tuple[str, str, str],
        dict[tuple[str, str, str, str], dict[str, Any]],
    ] = defaultdict(dict)

    student_grans: set[str] = set()
    cluster_grans: set[str] = set()
    has_boundaries = False

    for r in rows:
        edge_key = (r["source"], r["source_kind"], r["target"], r["target_kind"])
        if r["source_kind"] == "boundary" or r["target_kind"] == "boundary":
            has_boundaries = True
        scope_key = (r["granularity"], r["window_id"], r["scope_id"])
        if r["scope"] == "student":
            student_grans.add(r["granularity"])
            student_edges[scope_key][edge_key] = (int(r["freq"]), float(r["total_time_sec"]))
        elif r["scope"] == "cluster":
            cluster_grans.add(r["granularity"])
            cluster_edges[scope_key][edge_key] = r

    if student_grans != EXPECTED_GRANULARITIES or cluster_grans != EXPECTED_GRANULARITIES:
        raise RuntimeError(
            f"Granularidades incompletas en Neo4j "
            f"(student={sorted(student_grans)}, cluster={sorted(cluster_grans)})."
        )

    if include_boundaries and not has_boundaries:
        raise RuntimeError("No se encontraron nodos/aristas :Boundary (START/END) en Neo4j.")

    summary: dict[str, dict[str, int]] = defaultdict(lambda: {"clusters": 0, "edges": 0})

    for (gran, wid, cid), members in cluster_members.items():
        expected_agg: dict[tuple[str, str, str, str], list[float]] = {}
        for sid in members:
            s_edges = student_edges.get((gran, wid, sid))
            if not s_edges:
                raise RuntimeError(
                    f"Falta grafo DFG individual en Neo4j para ({gran}, {wid}, {sid})."
                )
            for ekey, (freq, total_sec) in s_edges.items():
                acc = expected_agg.setdefault(ekey, [0, 0.0, 0])
                acc[0] += freq
                acc[1] += total_sec
                acc[2] += 1

        expected_filtered = {
            ekey: vals for ekey, vals in expected_agg.items() if vals[0] >= min_edge_frequency
        }
        actual = cluster_edges.get((gran, wid, cid), {})
        if set(actual.keys()) != set(expected_filtered.keys()):
            raise RuntimeError(
                f"Aristas inconsistentes en clúster ({gran}, {wid}, {cid}): "
                f"esperadas={len(expected_filtered)}, actuales={len(actual)}."
            )

        trace_count = len(members)
        for ekey, (exp_freq_f, exp_total_sec, exp_trace_sup_f) in expected_filtered.items():
            exp_freq = int(exp_freq_f)
            exp_trace_sup = int(exp_trace_sup_f)
            exp_mean = exp_total_sec / exp_freq
            exp_support = exp_trace_sup / trace_count
            act = actual[ekey]

            if int(act["freq"]) != exp_freq:
                raise RuntimeError(
                    f"freq inconsistente en ({gran}, {wid}, {cid}) {ekey}: "
                    f"{act['freq']} != {exp_freq}"
                )
            if int(act["trace_count"]) != trace_count:
                raise RuntimeError(
                    f"trace_count inconsistente en ({gran}, {wid}, {cid}): "
                    f"{act['trace_count']} != {trace_count}"
                )
            if abs(float(act["total_time_sec"]) - exp_total_sec) > 1e-3:
                raise RuntimeError(
                    f"total_time_sec inconsistente en ({gran}, {wid}, {cid}) {ekey}: "
                    f"{act['total_time_sec']} != {exp_total_sec}"
                )
            if abs(float(act["mean_time_sec"]) - exp_mean) > 1e-3:
                raise RuntimeError(
                    f"mean_time_sec inconsistente en ({gran}, {wid}, {cid}) {ekey}: "
                    f"{act['mean_time_sec']} != {exp_mean}"
                )
            if abs(float(act["support"]) - exp_support) > 1e-4:
                raise RuntimeError(
                    f"support inconsistente en ({gran}, {wid}, {cid}) {ekey}: "
                    f"{act['support']} != {exp_support}"
                )

        summary[gran]["clusters"] += 1
        summary[gran]["edges"] += len(actual)

    return dict(summary)


def verify_phase5(settings: AppSettings) -> None:
    print_header(
        "ETAPA 6 — Comprobación de Fase 5 (C6 Process Mining + PM4Py + Neo4j DFG)"
    )
    asyncio.run(_wait_for_c6_health())

    pm_cfg = load_process_mining_config(REPO_ROOT / "config" / "process_mining.yaml")
    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(PHASE5_DATASET),
            "--target-events",
            "1500",
            "--students",
            "30",
            "--weeks",
            "8",
            "--seed",
            "77",
            "--noise-ratio",
            "0.05",
        ]
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_p5_{stamp}_{uuid4().hex[:4]}"
    run_cmd(
        [str(REPLAYER_BIN), "replay", str(PHASE5_DATASET), "--speed", "max", "--run-id", run_id]
    )

    cluster_members = asyncio.run(_fetch_mongo_cluster_members(settings, run_id))
    rows = asyncio.run(_wait_and_fetch_neo4j_edges(settings, run_id, cluster_members))
    summary = _verify_additive_consistency(
        rows,
        cluster_members,
        min_edge_frequency=pm_cfg.min_edge_frequency,
        include_boundaries=pm_cfg.include_boundaries,
    )

    print(
        f"\nNeo4j OK -> {len(rows)} aristas :DFG verificadas ({Topics.TRACES} + "
        f"{Topics.ASSIGNMENTS}) con consistencia aditiva 100% exacta:"
    )
    for gran in ("daily", "weekly", "monthly", "course"):
        info = summary[gran]
        print(f"  - {gran:7s}: {info['clusters']} grafos de clúster | {info['edges']} aristas :DFG")

    sample_weekly = next(
        (wid, cid) for (gran, wid, cid) in sorted(cluster_members) if gran == "weekly"
    )
    print("\nConsulta Cypher sugerida para Neo4j Browser (http://localhost:7474):")
    print(
        "  MATCH (s)-[r:DFG {run_id: '"
        f"{run_id}', granularity: 'weekly', window_id: '{sample_weekly[0]}', "
        f"scope: 'cluster', scope_id: '{sample_weekly[1]}'"
        "}]->(t) RETURN s, r, t;"
    )
    print(
        f"\n[OK] Etapa 6 verificada: DFG individuales y aditivos consolidados en Neo4j ({run_id})."
    )
