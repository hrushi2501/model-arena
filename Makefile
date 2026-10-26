.PHONY: install dev infrastructure train stack stack-full stop test

MODEL_ENV = $(if $(wildcard backend/ml/models/versions.env),--env-file backend/ml/models/versions.env,)
COMPOSE = docker compose --env-file .env $(MODEL_ENV)

install:
	bun install

dev:
	bun run dev

infrastructure:
	$(COMPOSE) up -d --build postgres rabbitmq mlflow

train:
	uv run --frozen --project backend/ml python backend/ml/src/train.py

stack:
	$(COMPOSE) --profile serving up --build -d

stack-full: stack

stop:
	$(COMPOSE) --profile serving down

test:
	cd backend/control_api && uv run --frozen --group dev pytest -q
	cd backend/worker && uv run --frozen --group dev pytest -q
	cd backend/model_serving && uv run --frozen --group dev pytest -q
	uv run --frozen --project backend/control_api --group dev python -m pytest -q scripts/tests
	bun run typecheck
