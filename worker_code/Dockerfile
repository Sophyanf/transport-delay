FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /workspace

RUN pip install --no-cache-dir uv==0.5.14

# 1. Корневой манифест и lock-файл
COPY pyproject.toml uv.lock ./

# 2. pyproject.toml ВСЕХ workspace-членов (обязательно для --frozen)
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/feature_pipeline/pyproject.toml packages/feature_pipeline/pyproject.toml
COPY packages/model_core/pyproject.toml packages/model_core/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
COPY apps/gateway/pyproject.toml apps/gateway/pyproject.toml
COPY apps/feature_worker/pyproject.toml apps/feature_worker/pyproject.toml
COPY apps/ml_service/pyproject.toml apps/ml_service/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

# 3. Код нужных пакетов
COPY packages/contracts packages/contracts
COPY packages/feature_pipeline packages/feature_pipeline
COPY apps/feature_worker apps/feature_worker

# 4. Синхронизация зависимостей
RUN uv sync \
    --frozen \
    --package transport-feature-worker \
    --no-dev

CMD ["uv", "run", "--frozen", \
     "--package", "transport-feature-worker", \
     "python", "-m", "transport_feature_worker.main"]
