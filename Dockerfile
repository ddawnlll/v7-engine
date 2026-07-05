FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY lib/ lib/
COPY simulation/ simulation/
COPY alphaforge/src/alphaforge/ alphaforge/
COPY v7/src/v7/ v7/
COPY v6/ v6/
COPY runtime/ runtime/
COPY integration/ integration/

RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

ENV PYTHONPATH=/app/alphaforge/src:/app/v7/src

CMD ["python", "-m", "pytest", "lib/tests/", "simulation/tests/", "integration/tests/", "runtime/tests/", "v7/tests/", "alphaforge/tests/", "-q"]
