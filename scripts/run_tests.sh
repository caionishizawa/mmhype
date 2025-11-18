#!/bin/bash
# Run all tests with coverage

set -e

echo "Running tests..."

# Run pytest with coverage
pytest tests/ \
    --cov=src \
    --cov-report=term-missing \
    --cov-report=html \
    -v

echo "Tests complete. Coverage report available in htmlcov/index.html"
