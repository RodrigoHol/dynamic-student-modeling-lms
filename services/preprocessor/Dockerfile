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

RUN uv sync --frozen --package dsm-preprocessor --no-install-workspace --no-dev

COPY libs/dsm_common libs/dsm_common
COPY libs/dsm_core libs/dsm_core
COPY services/preprocessor services/preprocessor

RUN uv sync --frozen --package dsm-preprocessor --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8004

CMD ["dsm-preprocessor"]
