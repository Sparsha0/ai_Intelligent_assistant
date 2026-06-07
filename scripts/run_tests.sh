#!/usr/bin/env bash
# run_tests.sh - Run all tests with coverage
set -e

echo "🧪 Running Engineering AI Assistant Tests"
echo "==========================================="

cd "$(dirname "$0")/.."

# Activate venv if available
if [ -f backend/venv/bin/activate ]; then
  source backend/venv/bin/activate
elif [ -f backend/venv/Scripts/activate ]; then
  source backend/venv/Scripts/activate
fi

echo ""
echo "Unit Tests:"
echo "-----------"
python -m pytest tests/unit/ -v --tb=short 2>&1

echo ""
echo "Integration Tests:"
echo "------------------"
python -m pytest tests/integration/ -v --tb=short 2>&1

echo ""
echo "✅ All tests complete!"
