# ── Stage 1: Builder (deps + compile translations) ────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Layer 1 — pip dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2 — application code
COPY . .

# Compile gettext .mo translation files
RUN pybabel compile -d translations

# ── Stage 2: Test (blocks build if tests fail) ──────────────────────────────
FROM builder AS test

RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov
ENV DB_PASSWORD=fake DB_USER=test DB_NAME=testdb
RUN python -m pytest tests/ --tb=short -q

# ── Stage 3: Runtime (lean, no tests/docs/scripts) ──────────────────────────
FROM python:3.11-slim AS runtime

ENV PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app code from builder (excluding tests/docs via .dockerignore)
COPY --from=builder /app /app

# Force test stage to execute — build fails if any test fails
COPY --from=test /app/pytest.ini /tmp/.tests-passed

# Remove test/dev files that slipped through
RUN rm -rf tests/ scripts/ docs/ migrations/ data/ \
    requirements-dev.txt pytest.ini .coverage .pytest_cache \
    SEO_*.md AUDIT_*.md *.sql

# Security: non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 2 --proxy-headers --forwarded-allow-ips='*'
