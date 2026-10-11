FROM node:22-bookworm-slim AS web
WORKDIR /app
COPY package.json package-lock.json ./
COPY web/package.json ./web/package.json
RUN npm ci
COPY web ./web
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libegl1 libgles2 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 courtside
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
COPY api ./api
COPY worker ./worker
COPY configs ./configs
RUN pip install --no-cache-dir -c requirements.lock -e '.[vision]' \
    && mkdir -p /app/storage /app/models && chown -R courtside:courtside /app
COPY --from=web /app/web/dist ./web/dist
ENV COURTSIDE_HOST=0.0.0.0 COURTSIDE_STORAGE=/app/storage COURTSIDE_MODEL=/app/models/pose_landmarker_full.task COURTSIDE_DEMO=0
USER courtside
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=30s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/ready', timeout=12)"
CMD ["courtside", "serve"]
