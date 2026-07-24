VENV := .venv/bin
DB := lighthouse

.PHONY: help install dev test lint fmt migrate revision db-reset

help:
	@echo "Lighthouse targets:"
	@echo "  install    Install the backend in editable mode with dev+resume extras"
	@echo "  dev        Run the API with autoreload on :8000"
	@echo "  test       Run the pytest suite"
	@echo "  lint       Run ruff check"
	@echo "  fmt        Run ruff format"
	@echo "  migrate    Apply migrations (alembic upgrade head)"
	@echo "  revision   Autogenerate a migration: make revision m=\"add jobs table\""
	@echo "  db-reset   Drop, recreate, extension-install, and migrate $(DB)"

install:
	$(VENV)/pip install -e "backend[dev,resume]"

dev:
	$(VENV)/uvicorn lighthouse.api:app --reload --app-dir backend

test:
	$(VENV)/pytest backend/tests

lint:
	$(VENV)/ruff check backend

fmt:
	$(VENV)/ruff format backend

migrate:
	$(VENV)/alembic upgrade head

revision:
	@test -n "$(m)" || (echo 'usage: make revision m="message"' && exit 1)
	$(VENV)/alembic revision --autogenerate -m "$(m)"

db-reset:
	dropdb --if-exists $(DB)
	createdb $(DB)
	psql $(DB) -c "CREATE EXTENSION IF NOT EXISTS vector;"
	$(VENV)/alembic upgrade head
