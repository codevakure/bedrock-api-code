# Main commands:
# - make init: Full setup (venv, dependencies, and database initialization)
# - make backend: Start the API server
# - make clean: Clean up temporary files and virtual environment

# Configuration
PYTHON := python
VENV := venv
PORT := 5000
HOST := 0.0.0.0
APP := main:app
REQUIREMENTS := requirements.txt
INIT_SCRIPT := scripts/init_dynamodb.py

# Check for MINGW specifically
ifneq (,$(findstring MINGW,$(shell uname -s)))
    # MINGW (Git Bash on Windows)
    VENV_PYTHON := $(VENV)/Scripts/python
    VENV_PIP := $(VENV)/Scripts/pip
    RM_VENV := rm -rf $(VENV)
    RM_CACHE := find . -type d -name "__pycache__" -exec rm -rf {} \; 2>/dev/null || true
else ifeq ($(OS),Windows_NT)
    # Regular Windows (cmd.exe)
    VENV_PYTHON := $(VENV)\Scripts\python
    VENV_PIP := $(VENV)\Scripts\pip
    RM_VENV := rmdir /s /q $(VENV)
    RM_CACHE := for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
else
    # Unix-like systems
    VENV_PYTHON := $(VENV)/bin/python
    VENV_PIP := $(VENV)/bin/pip
    RM_VENV := rm -rf $(VENV)
    RM_CACHE := find . -type d -name "__pycache__" -exec rm -rf {} \; 2>/dev/null || true
endif

# Main initialization
.PHONY: init
init: clean
	# Create venv if it doesn't exist
	@echo "Creating virtual environment..."
	@$(PYTHON) -m venv $(VENV)
	# Install dependencies
	@echo "Installing dependencies..."
	@$(VENV_PYTHON) -m pip install --upgrade pip
	@$(VENV_PIP) install -r $(REQUIREMENTS)
	# Install dev tools (with error handling)
	@echo "Installing development tools..."
	@$(VENV_PIP) install black isort flake8 pytest autoflake || echo "Warning: Some dev tools couldn't be installed"
	# Initialize database
	@echo "Initializing database..."
	@$(VENV_PYTHON) $(INIT_SCRIPT)
	# Install pre-commit hook
	@echo "Setting up pre-commit hook..."
	@mkdir -p .git/hooks
	@echo '#!/bin/bash' > .git/hooks/pre-commit
	@echo 'echo "Running formatter..."' >> .git/hooks/pre-commit
	@echo 'make format || true' >> .git/hooks/pre-commit
	@echo 'echo "Pre-commit completed"' >> .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Initialization complete!"

# Start the backend server
.PHONY: backend
backend:
	@echo "Starting backend server..."
	@$(VENV_PYTHON) -m uvicorn $(APP) --host=$(HOST) --port=$(PORT) --reload

# Format code
.PHONY: format
format:
	@echo "Formatting code..."
	@$(VENV_PYTHON) -m black . || echo "Warning: black formatting had issues"
	@$(VENV_PYTHON) -m isort . || echo "Warning: import sorting had issues"
	@echo "Formatting complete"

# Auto-fix linting issues
.PHONY: lint-fix
lint-fix:
	@echo "Auto-fixing linting issues..."
	@$(VENV_PYTHON) -m autoflake --in-place --remove-all-unused-imports --remove-unused-variables --recursive . || echo "Warning: autoflake had issues"
	@echo "Auto-fix complete"

# Lint code
.PHONY: lint
lint:
	@echo "Linting code..."
	@$(VENV_PYTHON) -m flake8 || echo "Linting found issues (shown above)"
	@echo "Linting check complete"

# Run tests
.PHONY: test
test:
	@echo "Running tests..."
	@$(VENV_PYTHON) -m pytest

# Clean everything
.PHONY: clean
clean:
	@echo "Cleaning up..."
	@echo "Removing virtual environment..."
	-@$(RM_VENV) 2>/dev/null || true
	@echo "Removing cache files..."
	-@$(RM_CACHE)
	@echo "Removing temp_docs_src directory if it exists..."
	-@rm -rf temp_docs_src 2>/dev/null || true
	@echo "Cleanup complete"

# Show help
.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make init     - Setup everything (venv, dependencies, database, git hooks)"
	@echo "  make backend  - Start the backend server"
	@echo "  make format   - Format code with black and isort"
	@echo "  make lint-fix - Auto-fix linting issues where possible"
	@echo "  make lint     - Check code with flake8"
	@echo "  make test     - Run tests"
	@echo "  make clean    - Remove virtual environment and cache files"
	@echo "  make help     - Show this help message"

# Default target
.DEFAULT_GOAL := help