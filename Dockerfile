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
# Used by run_podly_docker.sh for the NVIDIA *base image* tag
# (still nvidia/cuda:12.4.1-cudnn-devel). Pip torch 2.13 bundles CUDA 13.
# ROCm: torch 2.13.0 has no wheel on the rocm6.4 index (only 2.8/2.9).
# 2.13.0+rocm7.1 exists; keep the base image and this ARG in lockstep.
ARG CUDA_VERSION=12.4.1
ARG ROCM_VERSION=7.1
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

# Install Python deps and the variant-specific torch wheel in ONE layer.
# uv.lock pins torch 2.13.0, whose default Linux wheels pull CUDA 13
# (nvidia-cudnn-cu13, not cu12). If we uv-sync that into a CPU image and
# then swap torch in a later layer, the CUDA 13 wheels stay in the image.
# Skip installing torch during sync for CPU/ROCm, then install the matching
# wheel (CPU index, or rocm${ROCM_VERSION} which must publish torch 2.13.0).
# NVIDIA GPU keeps the lockfile CUDA 13 stack (do not install
# nvidia-cudnn-cu12 — it is incompatible with torch 2.13).
RUN --mount=type=cache,target=/root/.cache/uv \
    set -e && \
    if [ "${LITE_BUILD}" = "true" ]; then \
    echo "Installing lite dependencies (without Whisper/torch)"; \
    cp pyproject.lite.toml pyproject.toml && \
    cp uv.lite.lock uv.lock && \
    uv sync --frozen --no-dev --no-install-project; \
    echo "Skipping PyTorch installation in lite mode"; \
    elif [ "${USE_GPU}" = "true" ] || [ "${USE_GPU_NVIDIA}" = "true" ]; then \
    echo "Installing full dependencies with lockfile torch 2.13.0 (CUDA 13 / nvidia-cudnn-cu13)"; \
    uv sync --frozen --no-dev --no-install-project; \
    elif [ "${USE_GPU_AMD}" = "true" ]; then \
    echo "Installing full dependencies without CUDA torch; installing ROCm torch 2.13.0"; \
    uv sync --frozen --no-dev --no-install-project --no-install-package torch; \
    # --no-deps: lockfile already supplied torch's Python deps. A full resolve
    # against the PyTorch wheel index (index-url replaces PyPI) hangs for a
    # long time; CI previously failed even earlier because 2.13.0 is absent
    # from rocm6.4.
    uv pip install --no-deps "torch==2.13.0" --index-url "https://download.pytorch.org/whl/rocm${ROCM_VERSION}"; \
    uv pip freeze | awk -F== 'tolower($1) ~ /^(nvidia-|cuda-)/ {print $1}' | xargs -r uv pip uninstall; \
    else \
    echo "Installing full dependencies without CUDA torch; installing CPU torch 2.13.0"; \
    uv sync --frozen --no-dev --no-install-project --no-install-package torch; \
    uv pip install --no-deps "torch==2.13.0" --index-url https://download.pytorch.org/whl/cpu; \
    uv pip freeze | awk -F== 'tolower($1) ~ /^(nvidia-|cuda-)/ {print $1}' | xargs -r uv pip uninstall; \
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
