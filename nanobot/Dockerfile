FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install nanobot from GitHub
RUN uv pip install --system git+https://github.com/HKUDS/nanobot.git

# Install additional dependencies for custom tools
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy custom tools and skills
COPY tools/ /app/tools/
COPY skills/ /app/skills/

# Create nanobot workspace
RUN mkdir -p /root/.nanobot/workspace/skills

# Link our skills to nanobot workspace (will be populated at runtime if skills exist)
RUN if [ -d /app/skills ] && [ "$(ls -A /app/skills 2>/dev/null)" ]; then \
        ln -sf /app/skills/* /root/.nanobot/workspace/skills/ 2>/dev/null || true; \
    fi

EXPOSE 8100

ENTRYPOINT ["nanobot"]
CMD ["gateway", "--port", "8100"]
