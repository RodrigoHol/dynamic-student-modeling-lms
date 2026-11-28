from __future__ import annotations

import argparse
import shutil

from demo import (
    CLUSTERING_URL,
    DASHBOARD_URL,
    GRAFANA_URL,
    PREPROCESSOR_URL,
    PROCESS_MINING_URL,
    PROMETHEUS_URL,
    PYTEST_BIN,
    QUERY_API_URL,
    RUFF_BIN,
    compose_cmd,
    print_header,
    run_cmd,
    verify_phase1,
    verify_phase2,
    verify_phase3,
    verify_phase4,
    verify_phase5,
    verify_phase6,
    verify_phase7,
)

from dsm_common.config import AppSettings


def stage_0_clean_all(*, auto_yes: bool = False) -> None:
    print_header("ETAPA 0 — Limpieza total (docker compose down -v)")
    if not auto_yes:
        answer = (
            input(
                "Esto eliminará todos los contenedores y volúmenes locales de datos. "
                "¿Continuar? [s/N]: "
            )
            .strip()
            .lower()
        )
        if answer not in {"s", "si", "sí", "y", "yes"}:
            print("Operación cancelada por el usuario.")
            return
    run_cmd(compose_cmd("down", "-v"))
    print("Limpieza completa finalizada.")


def stage_1_env_and_tests() -> None:
    print_header("ETAPA 1 — Entorno Python, pruebas unitarias y linter")
    if shutil.which("uv"):
        run_cmd(["uv", "sync", "--all-packages"])
    else:
        print("Aviso: 'uv' no encontrado en PATH; se omite 'uv sync --all-packages'.")

    run_cmd([str(PYTEST_BIN), "-v"])
    run_cmd([str(RUFF_BIN), "check", "."])
    print("\n[OK] Etapa 1 verificada: pytest y ruff pasaron sin errores.")


def stage_9_stop_stack() -> None:
    print_header("ETAPA 9 — Apagar stack Docker (conservando volúmenes)")
    run_cmd(compose_cmd("down"))
    print("Contenedores detenidos.")


def show_status(settings: AppSettings) -> None:
    print_header("Estado de contenedores e interfaces web")
    run_cmd(compose_cmd("ps"), check=False)
    print("\nInterfaces web locales para demostración:")
    print(f"  - C8 Dashboard Docente (Vue 3):    {DASHBOARD_URL}")
    print(f"  - C7 Query API (OpenAPI /docs):    {QUERY_API_URL}/docs")
    print(f"  - Swagger / OpenAPI (C2 Gateway):  {settings.gateway_url.rstrip('/')}/docs")
    print(f"  - C4 Preprocessor (/health):       {PREPROCESSOR_URL}/health")
    print(f"  - C5 Clustering (/health):         {CLUSTERING_URL}/health")
    print(f"  - C6 Process Mining (/health):     {PROCESS_MINING_URL}/health")
    print("  - Redpanda Console (Kafka):        http://localhost:8080")
    print("  - Neo4j Browser (Grafos):          http://localhost:7474")
    print(f"  - Prometheus (Métricas):           {PROMETHEUS_URL}")
    print(f"  - Grafana (Paneles):               {GRAFANA_URL}")


def _render_menu(statuses: dict[str, str]) -> None:
    print("\n" + "=" * 72)
    print("  CONTROL DE AVANCE Y DEMOSTRACIÓN — DYNAMIC STUDENT MODELING LMS")
    print("=" * 72)
    print(f"  [0] Limpieza total desde cero (down -v)               [{statuses['0']}]")
    print(f"  [1] Etapa 1: Entorno, pytest y ruff                   [{statuses['1']}]")
    print(f"  [2] Etapa 2: Comprobar Fase 1 (Docker + C2 + 3 BDs)   [{statuses['2']}]")
    print(f"  [3] Etapa 3: Comprobar Fase 2 (5,000 ev C3 -> Kafka)  [{statuses['3']}]")
    print(f"  [4] Etapa 4: Comprobar Fase 3 (C4 + 10x vs max)       [{statuses['4']}]")
    print(f"  [5] Etapa 5: Comprobar Fase 4 (C5 + MongoDB + Algos)  [{statuses['5']}]")
    print(f"  [6] Etapa 6: Comprobar Fase 5 (C6 + PM4Py + Neo4j)    [{statuses['6']}]")
    print(f"  [7] Etapa 7: Comprobar Fase 6 (C7 API + C8 + WS)      [{statuses['7']}]")
    print(f"  [8] Etapa 8: Comprobar Fase 7 (C9 + C10 Observab.)    [{statuses['8']}]")
    print(f"  [9] Etapa 9: Apagar stack Docker (down)               [{statuses['9']}]")
    print("  [a] Ejecutar demostración completa (Etapas 1 -> 8)")
    print("  [s] Ver estado de contenedores e interfaces web")
    print("  [q] Salir")
    print("-" * 72)


def _execute_choice(
    choice: str,
    settings: AppSettings,
    statuses: dict[str, str],
    *,
    auto_yes: bool = False,
) -> bool:
    normalized = choice.strip().lower()
    if normalized == "q":
        return False

    actions = {
        "0": lambda: stage_0_clean_all(auto_yes=auto_yes),
        "1": stage_1_env_and_tests,
        "2": lambda: verify_phase1(settings),
        "3": lambda: verify_phase2(settings),
        "4": lambda: verify_phase3(settings),
        "5": lambda: verify_phase4(settings),
        "6": lambda: verify_phase5(settings),
        "7": lambda: verify_phase6(settings),
        "8": lambda: verify_phase7(settings),
        "9": stage_9_stop_stack,
    }

    if normalized == "s":
        show_status(settings)
        return True

    if normalized == "a":
        for key in ("1", "2", "3", "4", "5", "6", "7", "8"):
            try:
                actions[key]()
                statuses[key] = "OK"
            except Exception as exc:
                statuses[key] = "Error"
                print(f"\n[ERROR] Falló la etapa {key}: {exc}")
                return True
        print("\n[OK] Demostración completa (Etapas 1 -> 8) finalizada con éxito.")
        return True

    if normalized in actions:
        try:
            actions[normalized]()
            statuses[normalized] = "OK"
        except Exception as exc:
            statuses[normalized] = "Error"
            print(f"\n[ERROR] Falló la etapa {normalized}: {exc}")
        return True

    print(f"Opción no válida: '{choice}'.")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Menú interactivo para verificar y demostrar las Fases 1 a 7."
    )
    parser.add_argument(
        "--step",
        choices=["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "all", "status"],
        default=None,
        help="Ejecuta una etapa directamente sin abrir el menú interactivo.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma automáticamente operaciones destructivas (como la Etapa 0).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = AppSettings()
    statuses = {
        "0": "Pendiente",
        "1": "Pendiente",
        "2": "Pendiente",
        "3": "Pendiente",
        "4": "Pendiente",
        "5": "Pendiente",
        "6": "Pendiente",
        "7": "Pendiente",
        "8": "Pendiente",
        "9": "-",
    }

    if args.step is not None:
        mapped = {"all": "a", "status": "s"}.get(args.step, args.step)
        _execute_choice(mapped, settings, statuses, auto_yes=args.yes)
        return 1 if any(val == "Error" for val in statuses.values()) else 0

    while True:
        _render_menu(statuses)
        try:
            choice = input("Selecciona una opción: ")
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo del menú.")
            break
        if not _execute_choice(choice, settings, statuses, auto_yes=args.yes):
            print("Hasta luego.")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
