import ast
from pathlib import Path

FORBIDDEN_MODULES = {
    "aiokafka",
    "asyncpg",
    "confluent_kafka",
    "fastapi",
    "httpx",
    "kafka",
    "neo4j",
    "pymongo",
    "quixstreams",
    "rocksdict",
}


def test_dsm_core_has_no_io_or_broker_imports() -> None:
    core_src = Path(__file__).resolve().parents[1] / "src" / "dsm_core"
    py_files = list(core_src.rglob("*.py"))
    assert py_files, "No se encontraron archivos Python en dsm_core."

    violations: list[str] = []
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_MODULES:
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    violations.append(f"{path.name}: from {node.module} import ...")

    assert violations == []
