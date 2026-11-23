FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY libs/dsm_common libs/dsm_common
COPY libs/dsm_core libs/dsm_core
COPY services/ingestion-gateway services/ingestion-gateway

RUN uv sync --frozen --package dsm-ingestion-gateway --no-dev

EXPOSE 8000

CMD ["uv", "run", "--package", "dsm-ingestion-gateway", "--no-dev", "uvicorn", "dsm_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
