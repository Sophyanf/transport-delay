PYTHON := uv run --package transport-ml python
PLUGIN ?= catboost_residual_v1
MODEL_VERSION ?= 1.0.0

TRAIN_FEATURES := data/processed/train_features.parquet
TEST_FEATURES := data/processed/test_features.parquet
VALIDATE_FEATURES := data/processed/validate_features.parquet
VALIDATE_PREDICTIONS := data/interim/validate_predictions.parquet
SUBMISSION := data/submissions/submission.csv

.PHONY: sync lock format lint typecheck test check
.PHONY: audit baseline features-train features-test features-validate
.PHONY: train evaluate predict submission offline
.PHONY: up down logs clean-generated

sync:
	uv sync --all-packages

lock:
	uv lock

format:
	uv run ruff format .
	uv run ruff check . --fix

lint:
	uv run ruff check .
	uv run ruff format . --check

typecheck:
	uv run mypy packages ml apps

test:
	uv run pytest

check: lint typecheck test

audit:
	$(PYTHON) ml/scripts/audit_data.py \
		--data-root data/raw

baseline:
	$(PYTHON) ml/scripts/evaluate_baselines.py \
		--train-labels data/raw/labels/labels_train.csv \
		--test-labels data/raw/labels/labels_test.csv

features-train:
	$(PYTHON) ml/scripts/build_features.py \
		--points data/raw/labels/labels_train.csv \
		--traffic data/raw/train/traffic.csv \
		--schedule data/raw/train/schedule.csv \
		--output $(TRAIN_FEATURES)

features-test:
	$(PYTHON) ml/scripts/build_features.py \
		--points data/raw/labels/labels_test.csv \
		--traffic data/raw/test/traffic.csv \
		--schedule data/raw/test/schedule.csv \
		--output $(TEST_FEATURES)

features-validate:
	$(PYTHON) ml/scripts/build_features.py \
		--points data/raw/validate/points.csv \
		--traffic data/raw/validate/traffic.csv \
		--schedule data/raw/validate/schedule_plan.csv \
		--output $(VALIDATE_FEATURES)

train:
	$(PYTHON) ml/scripts/train.py \
		--plugin $(PLUGIN) \
		--version $(MODEL_VERSION) \
		--features $(TRAIN_FEATURES) \
		--labels data/raw/labels/labels_train.csv

evaluate:
	$(PYTHON) ml/scripts/evaluate.py \
		--plugin $(PLUGIN) \
		--version $(MODEL_VERSION) \
		--features $(TEST_FEATURES) \
		--labels data/raw/labels/labels_test.csv

predict:
	$(PYTHON) ml/scripts/predict_validate.py \
		--plugin $(PLUGIN) \
		--version $(MODEL_VERSION) \
		--features $(VALIDATE_FEATURES) \
		--output $(VALIDATE_PREDICTIONS)

submission:
	$(PYTHON) ml/scripts/make_submission.py \
		--template data/raw/sample_submission.csv \
		--predictions $(VALIDATE_PREDICTIONS) \
		--output $(SUBMISSION)

offline: audit baseline features-train features-test train evaluate

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs --follow

clean-generated:
	rm -f data/processed/*.parquet
	rm -f data/interim/*.parquet
	rm -f data/submissions/*.csv
