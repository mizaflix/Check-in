# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Instala dependências de sistema necessárias para psycopg (PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Apenas runtime libs do postgres
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copia pacotes instalados do builder
COPY --from=builder /install /usr/local

# Copia o código-fonte
COPY . .

# Pasta local de uploads; use um volume persistente no Docker Compose
RUN mkdir -p static/uploads

# Usuário não-root por segurança
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Inicia com gunicorn (4 workers; ajuste conforme os núcleos da VPS)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "app:app"]
