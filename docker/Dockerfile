# syntax=docker/dockerfile:1.7
FROM python:3.11.13-slim-bookworm

ARG TARGETARCH
ARG CODEBASE_MEMORY_VERSION=0.8.1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/mcp \
    AGENT_CHECKPOINT_HOME=/data/checkpoint \
    CBM_CACHE_DIR=/data/codebase

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Codebase Memory publishes static Linux binaries and a checksums file for
# every release. Download and verify the architecture selected by BuildKit.
RUN set -eu; \
    case "${TARGETARCH}" in \
      amd64|arm64) cbm_arch="${TARGETARCH}" ;; \
      *) echo "unsupported Docker architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    archive="codebase-memory-mcp-linux-${cbm_arch}.tar.gz"; \
    base="https://github.com/DeusData/codebase-memory-mcp/releases/download/v${CODEBASE_MEMORY_VERSION}"; \
    mkdir -p /tmp/cbm-download; \
    cd /tmp/cbm-download; \
    curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
      --output "${archive}" "${base}/${archive}"; \
    curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
      --output checksums.txt "${base}/checksums.txt"; \
    grep "  ${archive}$" checksums.txt > selected.sha256; \
    sha256sum --check selected.sha256; \
    tar -xzf "${archive}"; \
    binary="$(find . -type f -name codebase-memory-mcp | head -n 1)"; \
    test -n "${binary}"; \
    install -m 0755 "${binary}" /usr/local/bin/codebase-memory-mcp; \
    rm -rf /tmp/cbm-download; \
    codebase-memory-mcp --version

WORKDIR /opt/agent-checkpoint-mcp
COPY docker/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --requirement /tmp/requirements.txt

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps . \
    && agent-checkpoint-mcp --version

COPY docker/entrypoint.sh /usr/local/bin/docker-mcp-entrypoint
RUN chmod 0755 /usr/local/bin/docker-mcp-entrypoint \
    && groupadd --gid 10001 mcp \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/mcp mcp \
    && mkdir -p /data/checkpoint /data/codebase /workspace \
    && chown -R 10001:10001 /data /home/mcp /workspace

USER 10001:10001
WORKDIR /workspace

ENTRYPOINT ["docker-mcp-entrypoint"]
CMD ["checkpoint"]
