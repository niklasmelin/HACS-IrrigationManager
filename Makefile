SHELL := /bin/sh

.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

HASSFEST_IMAGE ?= ghcr.io/home-assistant/hassfest
TEST_REQUIREMENTS ?= tests/requirements_test.txt
COVERAGE_MIN ?= 85

.PHONY: \
	help \
	setup_test_env \
	check_python_env \
	check_hassfest_env \
	test \
	test-strict \
	test-unit \
	test-repository \
	test-hassfest \
	test-coverage \
	clean_test_env

help: ## Display available Makefile commands
	@printf "\nAvailable commands:\n\n"
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\n"

setup_test_env: ## Create the isolated Python test environment and pull Hassfest
	@command -v "$(PYTHON)" >/dev/null 2>&1 || { \
		echo "Error: $(PYTHON) is not installed."; \
		exit 1; \
	}
	@test -f "$(TEST_REQUIREMENTS)" || { \
		echo "Error: $(TEST_REQUIREMENTS) does not exist."; \
		exit 1; \
	}
	@test -d "$(VENV)" || "$(PYTHON)" -m venv "$(VENV)"
	@"$(VENV_PYTHON)" -m pip install --upgrade pip
	@"$(VENV_PYTHON)" -m pip install -r "$(TEST_REQUIREMENTS)"
	@command -v docker >/dev/null 2>&1 || { \
		echo "Error: Docker is required for Hassfest but is not installed."; \
		exit 1; \
	}
	@docker info >/dev/null 2>&1 || { \
		echo "Error: Docker is installed, but the daemon is unavailable."; \
		exit 1; \
	}
	@docker pull "$(HASSFEST_IMAGE)"
	@printf "\nTest environment is ready.\n"
	@printf "Run all tests with: make test\n"

check_python_env:
	@test -x "$(VENV_PYTHON)" || { \
		echo "Error: Python test environment is missing."; \
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

test: check_python_env check_hassfest_env ## Run all tests and report coverage
	@REQUIRE_HASSFEST=1 \
	HASSFEST_IMAGE="$(HASSFEST_IMAGE)" \
	"$(VENV_PYTHON)" -m pytest \
		--cov=custom_components.solar_irrigation \
		--cov-report=term-missing \
		--cov-branch \
		-v

test-strict: check_python_env check_hassfest_env ## Run all tests with 85 percent coverage required
	@REQUIRE_HASSFEST=1 \
	HASSFEST_IMAGE="$(HASSFEST_IMAGE)" \
	"$(VENV_PYTHON)" -m pytest \
		--cov=custom_components.solar_irrigation \
		--cov-report=term-missing \
		--cov-branch \
		--cov-fail-under=85 \
		-v

test-unit: check_python_env ## Run behavioral tests without repository validators
	@"$(VENV_PYTHON)" -m pytest \
		-m "not repository_validation" \
		-v

test-repository: check_python_env ## Run local repository checks without Hassfest
	@"$(VENV_PYTHON)" -m pytest \
		tests/test_repository_validation.py \
		-m "repository_validation and not hassfest" \
		-v

test-hassfest: check_python_env check_hassfest_env ## Run Hassfest in its isolated Docker container
	@REQUIRE_HASSFEST=1 \
	HASSFEST_IMAGE="$(HASSFEST_IMAGE)" \
	"$(VENV_PYTHON)" -m pytest \
		tests/test_repository_validation.py \
		-m hassfest \
		-v

test-coverage: check_python_env ## Run behavioral tests with branch coverage enforcement
	@"$(VENV_PYTHON)" -m pytest \
		-m "not repository_validation" \
		--cov=custom_components.solar_irrigation \
		--cov-branch \
		--cov-report=term-missing \
		--cov-fail-under="$(COVERAGE_MIN)" \
		-v

clean_test_env: ## Remove the local Python test environment and generated caches
	@rm -rf "$(VENV)" .pytest_cache .coverage htmlcov
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@echo "Local test environment and caches removed."
