FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY frontend/ ./
ENV REACT_APP_BACKEND_URL="" GENERATE_SOURCEMAP=false CI=false
RUN npm run build

FROM node:22-bookworm-slim AS whatsapp
WORKDIR /build
COPY whatsapp/package*.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NODE_ENV=production
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libatomic1 && rm -rf /var/lib/apt/lists/*
COPY --from=whatsapp /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY whatsapp/ ./whatsapp/
COPY --from=whatsapp /build/node_modules ./whatsapp/node_modules
COPY --from=frontend /build/build ./frontend/build
COPY scripts/ ./scripts/
RUN useradd --system --uid 10001 appuser && chown -R appuser /app
USER appuser
EXPOSE 10000
CMD ["python", "scripts/start_render.py"]
