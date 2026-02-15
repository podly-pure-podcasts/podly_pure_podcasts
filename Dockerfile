# Multi-stage build for combined frontend and backend
ARG BASE_IMAGE=python:3.11-slim
FROM node:18-alpine AS frontend-build

WORKDIR /app

# Copy frontend package files
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source code
COPY frontend/ ./

# Build frontend assets with explicit error handling
RUN set -e && \
    npm run build && \
    test -d dist && \
    echo "Frontend build successful - dist directory created"

# Backend stage
FROM ${BASE_IMAGE} AS backend
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /uvx /bin/

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ARG CUDA_VERSION=12.4.1
ARG ROCM_VERSION=6.4
ARG USE_GPU=false
ARG USE_GPU_NVIDIA=${USE_GPU}
ARG USE_GPU_AMD=false
ARG LITE_BUILD=false

WORKDIR /app

# Install dependencies based on base image
RUN if [ -f /etc/debian_version ]; then \
    apt-get update && \
    apt-get install -y ca-certificates && \
    # Determine if we need to install Python 3.11
    INSTALL_PYTHON=true && \
    if command -v python3 >/dev/null 2>&1; then \
        if python3 --version 2>&1 | grep -q "3.11"; then \
            INSTALL_PYTHON=false; \
        fi; \
    fi && \
    if [ "$INSTALL_PYTHON" = "true" ]; then \
        apt-get install -y software-properties-common && \
        if ! apt-cache show python3.11 > /dev/null 2>&1; then \
            add-apt-repository ppa:deadsnakes/ppa -y && \
            apt-get update; \
        fi && \
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-distutils \
        python3.11-dev \
        python3-pip && \
        update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
        update-alternatives --set python3 /usr/bin/python3.11; \
    fi && \
    # Install other dependencies
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg \
    sqlite3 \
    libsqlite3-dev \
    build-essential \
    gosu && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* ; \
    fi

# Install python3-tomli if Python version is less than 3.11 (separate step for ARM compatibility)
RUN if [ -f /etc/debian_version ]; then \
    PYTHON_MINOR=$(python3 --version 2>&1 | grep -o 'Python 3\.[0-9]*' | cut -d '.' -f2) && \
    if [ "$PYTHON_MINOR" -lt 11 ]; then \
    apt-get update && \
    apt-get install -y python3-tomli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* ; \
    fi ; \
    fi

# Copy dependency manifests and lock files
COPY pyproject.toml pyproject.lite.toml uv.lock uv.lite.lock ./

# Remove problematic distutils-installed packages that may conflict
RUN if [ -f /etc/debian_version ]; then \
    apt-get remove -y python3-blinker 2>/dev/null || true; \
    fi

# Install dependencies conditionally based on LITE_BUILD
RUN --mount=type=cache,target=/root/.cache/uv \
    set -e && \
    if [ "${LITE_BUILD}" = "true" ]; then \
    echo "Installing lite dependencies (without Whisper)"; \
    echo "Using lite pyproject:" && \
    cp pyproject.lite.toml pyproject.toml && \
    cp uv.lite.lock uv.lock && \
    uv sync --frozen --no-dev --no-install-project; \
    else \
    echo "Installing full dependencies (including Whisper)"; \
    echo "Using full pyproject:" && \
    uv sync --frozen --no-dev --no-install-project; \
    fi

# Install PyTorch with CUDA support if using NVIDIA image (skip if LITE_BUILD)
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "${LITE_BUILD}" = "true" ]; then \
    echo "Skipping PyTorch installation in lite mode"; \
    elif [ "${USE_GPU}" = "true" ] || [ "${USE_GPU_NVIDIA}" = "true" ]; then \
    uv pip install nvidia-cudnn-cu12 torch; \
    elif [ "${USE_GPU_AMD}" = "true" ]; then \
    uv pip install torch --index-url https://download.pytorch.org/whl/rocm${ROCM_VERSION}; \
    else \
    uv pip install torch --index-url https://download.pytorch.org/whl/cpu; \
    fi

# Copy application code
COPY src/ ./src/
RUN rm -rf ./src/instance
COPY scripts/ ./scripts/
RUN chmod +x scripts/start_services.sh

# Copy built frontend assets to Flask static folder
COPY --from=frontend-build /app/dist ./src/app/static

# Create non-root user for running the application
RUN groupadd -r appuser && \
    useradd --no-log-init -r -g appuser -d /home/appuser appuser && \
    mkdir -p /home/appuser && \
    chown -R appuser:appuser /home/appuser

# Create necessary directories and set permissions (only dirs needing runtime writes)
RUN mkdir -p /app/processing /app/src/instance /app/src/instance/data /app/src/instance/data/in /app/src/instance/data/srv /app/src/instance/config /app/src/instance/db && \
    chown -R appuser:appuser /app/processing /app/src/instance

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod 755 /docker-entrypoint.sh

# Add venv to PATH so we don't need uv run at runtime
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 5001

# Run the application through the entrypoint script
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["./scripts/start_services.sh"]
