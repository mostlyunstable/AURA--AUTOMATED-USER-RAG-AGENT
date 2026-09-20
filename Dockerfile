FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for asyncpg + healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY core/ ./core/
COPY apps/ ./apps/
COPY agents/ ./agents/
COPY policies/ ./policies/
COPY alembic/ ./alembic/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e "."

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
