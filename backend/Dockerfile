# Multi-stage Dockerfile for Micro-SaaS Backend
# Supports: API, Generic Worker, Browser Worker, Billing Cron, Agents
#
# Build targets:
#   docker build --target api -t micro-saas/api .
#   docker build --target worker -t micro-saas/worker .
#   docker build --target browser-worker -t micro-saas/browser-worker .
#   docker build --target billing-cron -t micro-saas/billing-cron .
#   docker build --target agents -t micro-saas/agents .

# =============================================================================
# Stage 1: Base image with common dependencies
# =============================================================================
FROM python:3.11-slim AS base

# OCI Labels
LABEL org.opencontainers.image.title="micro-saas-backend"
LABEL org.opencontainers.image.description="Micro-SaaS Platform Backend Services"
LABEL org.opencontainers.image.source="https://github.com/example/micro-saas"
LABEL org.opencontainers.image.vendor="Micro-SaaS"
LABEL org.opencontainers.image.licenses="MIT"

# Security: Create non-root user
RUN groupadd -r msaas && useradd -r -g msaas msaas

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# =============================================================================
# Stage 2: API Service
# =============================================================================
FROM base AS api

LABEL com.micro-saas.service.role="api"
LABEL org.opencontainers.image.title="micro-saas-api"

# Environment
ENV SERVICE_NAME=api
ENV APP_ENV=production

# Security: Switch to non-root user
USER msaas

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/metrics || exit 1

# Start API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# =============================================================================
# Stage 3: Generic Worker
# =============================================================================
FROM base AS worker

LABEL com.micro-saas.service.role="worker"
LABEL org.opencontainers.image.title="micro-saas-worker"

# Environment
ENV SERVICE_NAME=worker-generic
ENV APP_ENV=production

# Security: Switch to non-root user
USER msaas

# Health check (worker exposes metrics on different port)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Start generic worker
CMD ["python", "-m", "app.workers.run"]

# =============================================================================
# Stage 4: Browser Worker (with Playwright)
# =============================================================================
FROM base AS browser-worker-deps

# Install Playwright and browser dependencies
RUN pip install --no-cache-dir playwright && \
    playwright install chromium && \
    playwright install-deps chromium

FROM browser-worker-deps AS browser-worker

LABEL com.micro-saas.service.role="browser-worker"
LABEL org.opencontainers.image.title="micro-saas-browser-worker"

# Environment
ENV SERVICE_NAME=worker-browser
ENV APP_ENV=production
ENV PLAYWRIGHT_BROWSERS_PATH=/home/msaas/.cache/ms-playwright

# Copy Playwright browser cache to user directory
RUN mkdir -p /home/msaas/.cache && \
    cp -r /root/.cache/ms-playwright /home/msaas/.cache/ && \
    chown -R msaas:msaas /home/msaas/.cache

# Security: Switch to non-root user
USER msaas

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Start browser worker
CMD ["python", "-m", "worker.run"]

# =============================================================================
# Stage 5: Billing Cron
# =============================================================================
FROM base AS billing-cron

LABEL com.micro-saas.service.role="billing-cron"
LABEL org.opencontainers.image.title="micro-saas-billing-cron"

# Environment
ENV SERVICE_NAME=billing-cron
ENV APP_ENV=production

# Security: Switch to non-root user
USER msaas

# No health check needed for cron jobs (they're ephemeral)

# Start billing cron
CMD ["python", "-m", "app.cron.run"]

# =============================================================================
# Stage 6: Agents
# =============================================================================
FROM base AS agents

LABEL com.micro-saas.service.role="agents"
LABEL org.opencontainers.image.title="micro-saas-agents"

# Install additional agent dependencies (Chroma, etc.)
RUN pip install --no-cache-dir chromadb langchain langchain-openai

# Environment
ENV SERVICE_NAME=agents
ENV APP_ENV=production

# Security: Switch to non-root user
USER msaas

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

# Start agents
CMD ["python", "-m", "agents.run"]
