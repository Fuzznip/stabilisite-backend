#!/bin/bash
# Test runner for event system tests

echo "🧪 Event System Test Runner"
echo "=============================="
echo ""

# Set PYTHONPATH to include current directory
export PYTHONPATH=.

if [ -z "$1" ]; then
    echo "Usage: ./run_tests.sh [test_name]"
    echo ""
    echo "Available tests:"
    echo "  simple       - Run simplified bingo test (OR, AND, multi-task)"
    echo "  parent       - Run parent challenge test"
    echo "  all          - Run all event system tests"
    echo ""
    echo "Example: ./run_tests.sh parent"
    exit 1
fi

case "$1" in
    simple)
        echo "Running simplified bingo test..."
        .venv/bin/python tests/test_bingo_simple.py
        ;;
    parent)
        echo "Running parent challenge test..."
        .venv/bin/python tests/test_parent_challenges.py
        ;;
    all)
        echo "Running all event system tests..."
        echo ""
        echo "Test 1: Simplified Bingo"
        echo "------------------------"
        .venv/bin/python tests/test_bingo_simple.py
        echo ""
        echo "Test 2: Parent Challenges"
        echo "------------------------"
        .venv/bin/python tests/test_parent_challenges.py
        ;;
    *)
        echo "Unknown test: $1"
        echo "Run './run_tests.sh' for usage"
        exit 1
        ;;
esac
