from pathlib import Path

import httpx
from click.testing import CliRunner

from dsm_common.config import AppSettings
from dsm_common.messaging import InMemoryEventProducer, Topics
from dsm_gateway.main import create_app
from dsm_replayer.cli import main


def test_cli_generate_creates_dataset(tmp_path: Path) -> None:
    out_file = tmp_path / "synthetic_small.jsonl"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            str(out_file),
            "--students",
            "5",
            "--weeks",
            "2",
            "--target-events",
            "40",
            "--seed",
            "11",
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_file.is_file()
    lines = [line for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 40


def test_cli_replay_no_db_routes_to_gateway(tmp_path: Path, monkeypatch) -> None:
    dataset = tmp_path / "course.jsonl"
    runner = CliRunner()
    gen_res = runner.invoke(
        main,
        [
            "generate",
            str(dataset),
            "--students",
            "4",
            "--weeks",
            "1",
            "--target-events",
            "25",
            "--seed",
            "3",
        ],
    )
    assert gen_res.exit_code == 0

    producer = InMemoryEventProducer()
    settings = AppSettings(pseudonym_salt="cli-test-salt", default_run_id="run_cli")
    app = create_app(producer=producer, settings=settings)

    class _AsgiAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.ASGITransport(app=app)
            kwargs["base_url"] = "http://test"
            super().__init__(*args, **kwargs)
            self._lifespan_ctx = None

        async def post(self, *args, **kwargs):
            if self._lifespan_ctx is None:
                self._lifespan_ctx = app.router.lifespan_context(app)
                await self._lifespan_ctx.__aenter__()
            return await super().post(*args, **kwargs)

        async def aclose(self) -> None:
            try:
                await super().aclose()
            finally:
                if self._lifespan_ctx is not None:
                    await self._lifespan_ctx.__aexit__(None, None, None)
                    self._lifespan_ctx = None

    monkeypatch.setattr("dsm_replayer.scheduler.httpx.AsyncClient", _AsgiAsyncClient)

    replay_res = runner.invoke(
        main,
        [
            "replay",
            str(dataset),
            "--speed",
            "max",
            "--run-id",
            "run_cli_001",
            "--gateway-url",
            "http://test",
            "--no-db",
        ],
    )
    assert replay_res.exit_code == 0, replay_res.output
    assert "run_cli_001" in replay_res.output
    assert "aceptados=25" in replay_res.output
    canonical = [m for m in producer.messages if m.topic == Topics.CANONICAL_EVENTS]
    assert len(canonical) == 25
