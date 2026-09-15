.PHONY: setup lint format typecheck test check up down migrate demo

DEMO_DIR := .demo

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

# Seeds a fleet, drifts it, shows the report. `check` and `sync` exit non-zero on
# a drifted fleet -- that's the point -- so their exit codes are printed, not fatal.
demo:
	uv run python -m ansari.demo $(DEMO_DIR)/fleet
	@printf '\n$$ ansari check --fleet $(DEMO_DIR)/fleet\n'
	@uv run ansari check --fleet $(DEMO_DIR)/fleet; echo "(exit $$?)"
	@printf '\n$$ ansari sync --fleet --dry-run $(DEMO_DIR)/fleet\n'
	@uv run ansari sync --fleet --dry-run $(DEMO_DIR)/fleet; echo "(exit $$?)"
	@printf '\n$$ ansari dashboard $(DEMO_DIR)/fleet --output $(DEMO_DIR)/dashboard.html\n'
	@uv run ansari dashboard $(DEMO_DIR)/fleet --output $(DEMO_DIR)/dashboard.html
