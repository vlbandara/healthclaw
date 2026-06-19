# Healthclaw — common developer commands.
# Run `make help` for the list.

.DEFAULT_GOAL := help
.PHONY: help install lint test cov bridge up down doctor init-local precommit

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python deps (all extras) via uv
	uv sync --all-extras

lint: ## Lint with ruff (same rules as CI)
	uv run --extra dev ruff check nanobot tests

test: ## Run the test suite
	uv run --extra dev pytest -q

cov: ## Run tests with coverage report
	uv run --extra dev pytest -q --cov=nanobot --cov-report=term-missing

bridge: ## Install and build the WhatsApp bridge
	cd bridge && npm ci && npm run build

up: ## Start the local stack (uses .env.local)
	docker compose --env-file .env.local up

down: ## Stop the local stack
	docker compose down

doctor: ## Run local environment diagnostics
	uv run healthclaw doctor

init-local: ## Generate a local .env.local config
	uv run healthclaw init-local

precommit: ## Install and run pre-commit hooks on all files
	uv run --extra dev pre-commit install
	uv run --extra dev pre-commit run --all-files
