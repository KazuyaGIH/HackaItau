# Imagem única: frontend (Vite) compilado + FastAPI servindo API e estáticos.
# A chave do LLM entra por variável de ambiente (LLM_API_KEY), nunca na imagem.

FROM node:22-alpine AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY backend/pyproject.toml backend/
COPY backend/app backend/app
RUN pip install --no-cache-dir ./backend
COPY --from=web /src/frontend/dist frontend/dist
ENV PORT=8000
EXPOSE 8000
WORKDIR /srv/backend
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
