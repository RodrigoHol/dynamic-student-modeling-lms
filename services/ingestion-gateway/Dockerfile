FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version README.md ./
COPY libs/dsm_common/pyproject.toml libs/dsm_common/pyproject.toml
COPY libs/dsm_core/pyproject.toml libs/dsm_core/pyproject.toml
COPY services/ingestion-gateway/pyproject.toml services/ingestion-gateway/pyproject.toml
COPY services/replayer/pyproject.toml services/replayer/pyproject.toml
COPY services/preprocessor/pyproject.toml services/preprocessor/pyproject.toml

RUN uv sync --frozen --package dsm-ingestion-gateway --no-install-workspace --no-dev

COPY libs/dsm_common libs/dsm_common
COPY services/ingestion-gateway services/ingestion-gateway

RUN uv sync --frozen --package dsm-ingestion-gateway --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "dsm_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
