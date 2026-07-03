COMPOSE = docker compose

.PHONY: help up down build logs restart ingest seed test lint format type-check clean install-dev eval


help:
	@echo ""
	@echo "  Autonomous Knowledge Execution Agent"
	@echo "  ─────────────────────────────────────"
	@echo "  install-dev Install dev/test dependencies"
	@echo "  up          Start all services (detached)"
	@echo "  down        Stop all services"
	@echo "  build       Rebuild all Docker images"
	@echo "  logs        Tail logs for all services"
	@echo "  restart     Restart all services"
	@echo "  ingest      Run the knowledge ingestion pipeline"
	@echo "  seed        Seed sample ticket data"
	@echo "  test        Run the full test suite"
	@echo "  eval        Run eval harness against live system"
	@echo "  lint        Lint with ruff"
	@echo "  format      Format with ruff"
	@echo "  type-check  Run mypy"
	@echo "  clean       Stop containers and delete volumes"
	@echo ""


install-dev:
	pip install -r requirements-dev.txt
	pip install -e .

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build --no-cache

logs:
	$(COMPOSE) logs -f

restart:
	$(COMPOSE) restart

ingest:
	python scripts/ingest_knowledge.py

seed:
	python scripts/seed_data.py

eval:
	python tests/evals/eval_harness.py --base-url http://localhost:8000

test:
	pytest tests/ -v --tb=short

lint:
	ruff check .

format:
	ruff format .

type-check:
	mypy shared/ services/ --ignore-missing-imports

clean:
	$(COMPOSE) down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
