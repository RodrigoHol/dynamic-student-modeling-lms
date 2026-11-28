FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
COPY libs/dsm_common/pyproject.toml libs/dsm_common/pyproject.toml
COPY libs/dsm_core/pyproject.toml libs/dsm_core/pyproject.toml
COPY services/ingestion-gateway/pyproject.toml services/ingestion-gateway/pyproject.toml
COPY services/replayer/pyproject.toml services/replayer/pyproject.toml
COPY services/preprocessor/pyproject.toml services/preprocessor/pyproject.toml
COPY services/clustering/pyproject.toml services/clustering/pyproject.toml
COPY services/process-mining/pyproject.toml services/process-mining/pyproject.toml
COPY services/query-api/pyproject.toml services/query-api/pyproject.toml
COPY experiments/pyproject.toml experiments/pyproject.toml

RUN uv sync --frozen --package dsm-replayer --no-install-workspace --no-dev

COPY libs/dsm_common libs/dsm_common
COPY services/replayer services/replayer

RUN uv sync --frozen --package dsm-replayer --no-dev

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["dsm-replayer"]
