.PHONY: setup lint format typecheck test check up down migrate

setup:
	uv sync --extra dev
	uv run pre-commit install

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy src

test:
	uv run pytest --cov --cov-report=term-missing

check: lint typecheck test

up:
	docker compose up --build

down:
	docker compose down -v

migrate:
	uv run alembic upgrade head
