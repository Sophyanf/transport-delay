FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_LINK_MODE=copy

WORKDIR /workspace

RUN pip install --no-cache-dir uv==0.5.14

# 1. Копируем корневой манифест и lock-файл
COPY pyproject.toml uv.lock ./

# 2. Копируем pyproject.toml для ВСЕХ workspace-членов
# Это обязательно, иначе uv не сможет собрать зависимости
COPY packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY packages/feature_pipeline/pyproject.toml packages/feature_pipeline/pyproject.toml
COPY packages/model_core/pyproject.toml packages/model_core/pyproject.toml
COPY ml/pyproject.toml ml/pyproject.toml
COPY apps/gateway/pyproject.toml apps/gateway/pyproject.toml
COPY apps/feature_worker/pyproject.toml apps/feature_worker/pyproject.toml
COPY apps/ml_service/pyproject.toml apps/ml_service/pyproject.toml
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

# 3. Теперь копируем код пакетов и приложения
COPY packages/contracts packages/contracts
COPY packages/feature_pipeline packages/feature_pipeline
COPY packages/model_core packages/model_core
COPY ml ml
COPY apps/gateway apps/gateway
COPY apps/feature_worker apps/feature_worker
COPY apps/ml_service apps/ml_service
COPY apps/backend apps/backend

# 4. Синхронизируем зависимости (теперь это сработает)
RUN uv sync \
    --frozen \
    --package transport-backend \
    --no-dev

EXPOSE 8000

CMD ["uv", "run", "--frozen", \
     "--package", "transport-backend", \
     "uvicorn", "transport_backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
