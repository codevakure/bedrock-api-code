#!/bin/bash

# Exit on errors (except for the linting step which we handle specially)
set -e

echo "Running pre-commit checks..."

# Run auto-formatting (this should always happen)
echo "Formatting code..."
make format

# Run auto-fix for linting issues
echo "Auto-fixing linting issues..."
make lint-fix

# Run linting check but do not fail on errors
echo "Checking for remaining linting issues..."
make lint

# Store the exit code from linting
LINT_EXIT_CODE=$?

# Run type checking (will exit on failure)
echo "Type checking..."
make type-check

# If linting had issues
if [ $LINT_EXIT_CODE -ne 0 ]; then
    echo "âš ï¸ Linting issues were found!"
    echo "These issues could not be automatically fixed."
    
    # Ask the user if they want to proceed
    read -p "Do you want to commit anyway? (y/n) " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Commit aborted. Please fix the linting issues before committing."
        exit 1
    fi
    
    echo "Proceeding with commit despite linting issues..."
fi

echo "Pre-commit checks completed successfully!"
