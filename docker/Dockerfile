# =========================
# 1️⃣ BUILD STAGE
# =========================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock /app/

# Install dependencies into local environment
RUN uv sync --frozen

# Copy source + protos
COPY src/ /app/src/
COPY protos/ /app/protos/

# Ensure generated folder exists
RUN mkdir -p /app/src/energy_server/generated \
    && touch /app/src/energy_server/generated/__init__.py

# Generate gRPC code
RUN uv run gen-protos

# Install your package into a clean location
RUN uv pip install --system .

---

# =========================
# 2️⃣ RUNTIME STAGE
# =========================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy only runtime code (optional but good practice)
COPY src/ /app/src/

# Run server
CMD ["energy-server"]