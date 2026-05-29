.DEFAULT_GOAL := help
COMPOSE := docker compose
PROD := -f docker-compose.yml -f docker-compose.prod.yml

.PHONY: help up down logs ps build pull smoke prod-up

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start the full stack (http://localhost:8080)
	$(COMPOSE) up -d

down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: ## Tail logs from all services
	$(COMPOSE) logs -f

ps: ## Show service status
	$(COMPOSE) ps

build: ## Build the image locally instead of pulling
	$(COMPOSE) build

pull: ## Pull the published image from GHCR
	$(COMPOSE) pull

smoke: ## Run the smoke test against a running stack
	./scripts/smoke.sh

prod-up: ## Start with the TLS overlay (requires DOMAIN env var)
	$(COMPOSE) $(PROD) up -d
