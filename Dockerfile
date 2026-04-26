FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Optional: skip building the WhatsApp bridge (useful for CI/platform testing).
ARG NANOBOT_BUILD_BRIDGE=1

# Install Node.js 20 for the WhatsApp bridge
RUN if [ "$NANOBOT_BUILD_BRIDGE" = "1" ]; then \
      apt-get update && \
      apt-get install -y --no-install-recommends curl ca-certificates gnupg git bubblewrap openssh-client && \
      mkdir -p /etc/apt/keyrings && \
      curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
      echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
      apt-get update && \
      apt-get install -y --no-install-recommends nodejs && \
      apt-get purge -y gnupg && \
      apt-get autoremove -y && \
      rm -rf /var/lib/apt/lists/*; \
    else \
      apt-get update && \
      apt-get install -y --no-install-recommends curl ca-certificates git bubblewrap openssh-client && \
      rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot bridge && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot bridge

# Copy the full source and install
COPY alembic.ini alembic.ini
COPY alembic/ alembic/
COPY nanobot/ nanobot/
COPY bridge/ bridge/
RUN uv pip install --system --no-cache .

# Build the WhatsApp bridge
WORKDIR /app/bridge
RUN if [ "$NANOBOT_BUILD_BRIDGE" = "1" ]; then \
      git config --global --add url."https://github.com/".insteadOf ssh://git@github.com/ && \
      git config --global --add url."https://github.com/".insteadOf git@github.com: && \
      npm ci && npm run build; \
    else \
      echo "Skipping WhatsApp bridge build"; \
    fi
WORKDIR /app

# Create non-root user and config directory
RUN useradd -m -u 1000 -s /bin/bash nanobot && \
    mkdir -p /home/nanobot/.nanobot && \
    chown -R nanobot:nanobot /home/nanobot /app

USER nanobot
ENV HOME=/home/nanobot

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["status"]
