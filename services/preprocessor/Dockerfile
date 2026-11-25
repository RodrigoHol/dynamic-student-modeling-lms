FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
COPY libs/dsm_common libs/dsm_common
COPY libs/dsm_core libs/dsm_core
COPY services/preprocessor services/preprocessor

RUN uv sync --frozen --package dsm-preprocessor --no-dev

EXPOSE 8004

CMD ["uv", "run", "--package", "dsm-preprocessor", "--no-dev", "dsm-preprocessor"]
