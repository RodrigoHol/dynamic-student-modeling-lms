from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import websockets

from demo.runner import (
    DASHBOARD_URL,
    PHASE6_DATASET,
    QUERY_API_URL,
    REPLAYER_BIN,
    print_header,
    run_cmd,
)
from dsm_common.config import AppSettings


async def _wait_for_c7_and_c8(timeout_seconds: float = 40.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    async with httpx.AsyncClient(timeout=5.0) as client:
        while loop.time() < deadline:
            try:
                r7 = await client.get(f"{QUERY_API_URL}/health")
                r8 = await client.get(DASHBOARD_URL)
                if r7.status_code == 200 and r8.status_code == 200:
                    print(f"C7 /health -> {r7.status_code} {r7.json()}")
                    print(f"C8 Dashboard ({DASHBOARD_URL}) -> {r8.status_code}")
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1.0)
    raise RuntimeError("C7 Query API o C8 Dashboard no respondieron 200 dentro del timeout.")


async def _verify_api_and_ws(run_id: str) -> None:
    ws_url = QUERY_API_URL.replace("http://", "ws://") + f"/ws/runs/{run_id}"
    ws_events: list[dict] = []

    async with httpx.AsyncClient(base_url=QUERY_API_URL, timeout=15.0) as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "docente", "password": "docente123"},
        )
        if login.status_code != 200:
            raise RuntimeError(f"Login docente falló en C7: {login.status_code} {login.text}")
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        async with websockets.connect(ws_url) as ws:
            loop = asyncio.get_running_loop()
            proc = await asyncio.create_subprocess_exec(
                str(REPLAYER_BIN),
                "replay",
                str(PHASE6_DATASET),
                "--speed",
                "max",
                "--run-id",
                run_id,
            )
            rc = await proc.wait()
            if rc != 0:
                raise RuntimeError(f"dsm-replayer falló con código {rc}")

            deadline = loop.time() + 30.0
            while loop.time() < deadline and len(ws_events) < 5:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    ws_events.append(json.loads(raw))
                except TimeoutError:
                    if ws_events:
                        break

        if not ws_events:
            raise RuntimeError(f"No se recibieron eventos WebSocket para '{run_id}'.")
        print(f"WebSocket OK -> {len(ws_events)} eventos 'window_updated' recibidos en vivo.")

        # Esperar breve consolidación en C5/C6 y consultar vistas REST
        await asyncio.sleep(3.0)
        courses = (await client.get("/api/v1/courses", headers=headers)).json()
        runs = (await client.get("/api/v1/runs", headers=headers)).json()
        evo = (
            await client.get(
                f"/api/v1/runs/{run_id}/clusters/evolution?granularity=weekly",
                headers=headers,
            )
        ).json()
        students = (
            await client.get(
                f"/api/v1/runs/{run_id}/students?granularity=weekly",
                headers=headers,
            )
        ).json()

        if not courses or not any(r["run_id"] == run_id for r in runs):
            raise RuntimeError(f"C7 no expone cursos/corrida '{run_id}'.")
        if not evo.get("windows") or not students:
            raise RuntimeError(f"C7 evolución/estudiantes vacío para '{run_id}'.")

        sample_win = evo["windows"][0]["window_id"]
        sample_cid = next(iter(evo["windows"][0]["counts"].keys()))
        sample_sid = students[0]["student_id"]

        dfg = (
            await client.get(
                f"/api/v1/runs/{run_id}/dfg?granularity=weekly&window_id={sample_win}"
                f"&scope=cluster&scope_id={sample_cid}",
                headers=headers,
            )
        ).json()
        timeline = (
            await client.get(
                f"/api/v1/runs/{run_id}/students/{sample_sid}?granularity=weekly",
                headers=headers,
            )
        ).json()

        print(
            f"C7 REST OK -> cursos={len(courses)} | ventanas_weekly={len(evo['windows'])} | "
            f"sankey_links={len(evo['sankey_links'])} | dfg_edges={len(dfg['edges'])} | "
            f"timeline_len={len(timeline['history'])}"
        )


def verify_phase6(_settings: AppSettings) -> None:
    print_header("ETAPA 7 — Comprobación de Fase 6 (C7 Query API + C8 Dashboard + WebSocket)")
    asyncio.run(_wait_for_c7_and_c8())

    run_cmd(
        [
            str(REPLAYER_BIN),
            "generate",
            str(PHASE6_DATASET),
            "--target-events",
            "1200",
            "--students",
            "25",
            "--weeks",
            "6",
            "--seed",
            "66",
            "--noise-ratio",
            "0.05",
        ]
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_id = f"run_p6_{stamp}_{uuid4().hex[:4]}"
    asyncio.run(_verify_api_and_ws(run_id))
    print(
        f"\n[OK] Etapa 7 verificada: C7 (JWT + REST + WS) y C8 Dashboard ({DASHBOARD_URL}) "
        f"operativos para {run_id}."
    )
