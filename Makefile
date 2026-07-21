```makefile
SHELL := /bin/sh

.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

HASSFEST_IMAGE ?= ghcr.io/home-assistant/hassfest
TEST_REQUIREMENTS ?= tests/requirements_test.txt

.PHONY: \
	help \
	setup_test_env \
	check_python_env \
	check_hassfest_env \
	test \
	test-unit \
	test-repository \
	test-hassfest \
	clean_test_env

help: ## Display available Makefile commands
	@printf "\nAvailable commands:\n\n"
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\n"

setup_test_env: ## Create the test virtual environment and download Hassfest
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { \
		echo "Error: $(PYTHON) is not installed."; \
		exit 1; \
	}
	@command -v docker >/dev/null 2>&1 || { \
		echo "Error: Docker is not installed."; \
		exit 1; \
	}
	@docker info >/dev/null 2>&1 || { \
		echo "Error: Docker is installed, but the daemon is unavailable."; \
		exit 1; \
	}
	@test -f "$(TEST_REQUIREMENTS)" || { \
		echo "Error: $(TEST_REQUIREMENTS) does not exist."; \
		exit 1; \
	}
	@test -d "$(VENV)" || "$(PYTHON)" -m venv "$(VENV)"
	@"$(VENV_PYTHON)" -m pip install --upgrade pip
	@"$(VENV_PYTHON)" -m pip install -r "$(TEST_REQUIREMENTS)"
	@docker pull "$(HASSFEST_IMAGE)"
	@echo
	@echo "Test environment is ready."
	@echo "Run all tests with: make test"

check_python_env:
	@test -x "$(VENV_PYTHON)" || { \
		echo "Error: test environment is missing."; \
		echo "Run: make setup_test_env"; \
		exit 1; \
	}

check_hassfest_env:
	@command -v docker >/dev/null 2>&1 || { \
		echo "Error: Docker is not installed."; \
		exit 1; \
	}
	@docker info >/dev/null 2>&1 || { \
		echo "Error: Docker daemon is unavailable."; \
		exit 1; \
	}
	@docker image inspect "$(HASSFEST_IMAGE)" >/dev/null 2>&1 || { \
		echo "Error: Hassfest image is missing."; \
		echo "Run: make setup_test_env"; \
		exit 1; \
	}

test: check_python_env check_hassfest_env ## Run all pytest and Hassfest tests
	@REQUIRE_HASSFEST=1 \
	HASSFEST_IMAGE="$(HASSFEST_IMAGE)" \
	"$(VENV_PYTHON)" -m pytest -v

test-unit: check_python_env ## Run behavioral tests, excluding repository validation
	@"$(VENV_PYTHON)" -m pytest \
		-m "not repository_validation" \
		-v

test-repository: check_python_env ## Run local repository and metadata validation
	@"$(VENV_PYTHON)" -m pytest \
		-m "repository_validation and not hassfest" \
		-v

test-hassfest: check_python_env check_hassfest_env ## Run only Hassfest validation
	@REQUIRE_HASSFEST=1 \
	HASSFEST_IMAGE="$(HASSFEST_IMAGE)" \
	"$(VENV_PYTHON)" -m pytest \
		-m hassfest \
		-v

clean_test_env: ## Remove the Python test environment and caches
	@rm -rf "$(VENV)"
	@rm -rf .pytest_cache
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@echo "Local Python test environment removed."
```
