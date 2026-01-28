#!/bin/bash

# MandarinOS Trace Conformance Validator (macOS / Linux)
# 
# Usage: ./validate_traces.sh /path/to/traces/directory
# 
# This script validates all *.json trace files in the given directory
# against the TurnStateTrace schema and conformance rules.

set -e

TRACES_DIR="${1:-.}"

if [ ! -d "$TRACES_DIR" ]; then
    echo "Error: Directory '$TRACES_DIR' not found"
    exit 1
fi

echo "MandarinOS Trace Conformance Validator (v1)"
echo "=========================================="
echo "Traces directory: $TRACES_DIR"
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.7+"
    exit 1
fi

# Try to detect the MandarinOS-core repository root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CORE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$CORE_ROOT/conformance/run_trace_conformance.py" ]; then
    echo "Error: Cannot find MandarinOS-core conformance runner"
    echo "Expected at: $CORE_ROOT/conformance/run_trace_conformance.py"
    exit 1
fi

echo "Running conformance checks..."
echo ""

# Run the conformance validator
python3 "$CORE_ROOT/conformance/run_trace_conformance.py" "$CORE_ROOT" --path "$TRACES_DIR"
EXIT_CODE=$?

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ All traces passed conformance validation"
else
    echo "✗ Trace validation failed (exit code: $EXIT_CODE)"
fi

exit $EXIT_CODE
