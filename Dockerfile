# Python deps (layer cache)
FROM node:20-slim AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY --from=web /app/web/dist ./web/dist

RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    ".[ui,audio-nn]"

ENV BEAT_THIS_MODEL_DIR=/models
ENV TORCH_HOME=/models
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "-m", "viral_editor", "serve", "--host", "0.0.0.0", "--port", "8765"]
