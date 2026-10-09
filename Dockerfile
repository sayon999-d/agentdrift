# =============================================================================
# AgentDrift Cloud MCP — production image (multi-stage).
# Target:  uvicorn agentdrift.mcp.cloud_server:app --host 0.0.0.0 --port 8000
# Build:   docker build -t agentdrift-cloud-mcp .
# Run:     docker run -p 8000:8000 --env-file .env agentdrift-cloud-mcp
# Slim tip: for a ~2GB-smaller CPU-only image, add build arg
#   TORCH_INDEX=https://download.pytorch.org/whl/cpu (see builder stage).
# =============================================================================

# ---- Stage 1: builder (compilers + wheels, discarded afterwards) -------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer caching: dependencies change far less often than source.
COPY requirements.txt ./
ARG TORCH_INDEX=""
RUN pip install --upgrade pip && \
    if [ -n "$TORCH_INDEX" ]; then \
      pip install --prefix=/install -r requirements.txt \
        --extra-index-url "$TORCH_INDEX"; \
    else \
      pip install --prefix=/install -r requirements.txt; \
    fi

# ---- Stage 2: runtime (slim, non-root, health-checked) -----------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder /install /usr/local
COPY pyproject.toml README.md ./
COPY agentdrift/ agentdrift/
COPY mcp_server.py ./
COPY migrations/ migrations/

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

CMD ["sh", "-c", "uvicorn agentdrift.mcp.cloud_server:app --host 0.0.0.0 --port ${PORT:-8000}"]
