FROM node:24.8.0-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash ca-certificates curl git jq python3 python3-pip ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global \
    @anthropic-ai/claude-code@2.1.233 \
    @openai/codex@0.147.0 \
    opencode-ai@1.18.18 \
    @earendil-works/pi-coding-agent@0.84.2

COPY worker_runtime/requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

WORKDIR /runtime
COPY worker_runtime/__init__.py worker_runtime/runtime.py /runtime/worker_runtime/

RUN useradd --create-home --uid 10001 worker \
    && mkdir -p /workspace/jobs /artifacts /auth/platform \
    && chown -R worker:worker /workspace /artifacts /auth /runtime

USER worker
EXPOSE 8090
CMD ["python3", "-m", "uvicorn", "worker_runtime.runtime:app", "--host", "0.0.0.0", "--port", "8090"]
