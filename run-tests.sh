#!/bin/bash
# Quick test runner script for USB Enforcer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  USB Enforcer Test Suite"
echo "=================================================="
echo

# Check if we're running as root for integration tests
if [ "$EUID" -eq 0 ]; then
    IS_ROOT=true
    echo -e "${YELLOW}Running as root - integration tests will be executed${NC}"
else
    IS_ROOT=false
    echo -e "${YELLOW}Not running as root - only unit tests will be executed${NC}"
    echo -e "${YELLOW}Run with 'sudo' to include integration tests${NC}"
fi
echo

# Parse command line arguments
RUN_UNIT=true
RUN_INTEGRATION=false
RUN_COVERAGE=false
RUN_LINT=false

if [ $# -eq 0 ]; then
    # Default: run unit tests
    :
else
    RUN_UNIT=false
    for arg in "$@"; do
        case $arg in
            unit)
                RUN_UNIT=true
                ;;
            integration)
                RUN_INTEGRATION=true
                ;;
            coverage)
                RUN_UNIT=true
                RUN_COVERAGE=true
                ;;
            lint)
                RUN_LINT=true
                ;;
            all)
                RUN_UNIT=true
                RUN_INTEGRATION=true
                RUN_COVERAGE=true
                ;;
            *)
                echo "Usage: $0 [unit|integration|coverage|lint|all]"
                echo
                echo "  unit         - Run unit tests (default)"
                echo "  integration  - Run integration tests (requires root)"
                echo "  coverage     - Run unit tests with coverage report"
                echo "  lint         - Run code quality checks"
                echo "  all          - Run all tests and checks"
                exit 1
                ;;
        esac
    done
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not found${NC}"
    echo "Install test dependencies: pip install -r requirements-test.txt"
    exit 1
fi

FAILED=0

# Run unit tests
if [ "$RUN_UNIT" = true ]; then
    echo "=================================================="
    echo "  Running Unit Tests"
    echo "=================================================="
    echo
    
    if [ "$RUN_COVERAGE" = true ]; then
        pytest tests/unit/ -v --cov=src/usb_enforcer --cov-report=html --cov-report=term || FAILED=1
        echo
        echo -e "${GREEN}Coverage report generated: htmlcov/index.html${NC}"
    else
        pytest tests/unit/ -v || FAILED=1
    fi
    echo
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    if [ "$IS_ROOT" = false ]; then
        echo -e "${RED}Error: Integration tests require root privileges${NC}"
        echo "Run with: sudo $0 integration"
        exit 1
    fi
    
    echo "=================================================="
    echo "  Running Integration Tests"
    echo "=================================================="
    echo
    
    # Check for required commands
    MISSING_DEPS=false
    for cmd in cryptsetup parted mkfs.ext4 losetup; do
        if ! command -v $cmd &> /dev/null; then
            echo -e "${RED}Error: Required command '$cmd' not found${NC}"
            MISSING_DEPS=true
        fi
    done
    
    if [ "$MISSING_DEPS" = true ]; then
        echo
        echo "Install system dependencies:"
        echo "  Debian/Ubuntu: sudo apt-get install cryptsetup parted e2fsprogs"
        echo "  Fedora/RHEL:   sudo dnf install cryptsetup parted e2fsprogs"
        exit 1
    fi
    
    pytest tests/integration/ -v -m integration || FAILED=1
    echo
fi

# Run linting
if [ "$RUN_LINT" = true ]; then
    echo "=================================================="
    echo "  Running Code Quality Checks"
    echo "=================================================="
    echo
    
    echo "Checking code formatting with black..."
    if command -v black &> /dev/null; then
        black --check src/ tests/ || FAILED=1
    else
        echo -e "${YELLOW}Warning: black not installed, skipping${NC}"
    fi
    echo
    
    echo "Checking import sorting with isort..."
    if command -v isort &> /dev/null; then
        isort --check-only src/ tests/ || FAILED=1
    else
        echo -e "${YELLOW}Warning: isort not installed, skipping${NC}"
    fi
    echo
    
    echo "Linting with flake8..."
    if command -v flake8 &> /dev/null; then
        flake8 src/ tests/ || FAILED=1
    else
        echo -e "${YELLOW}Warning: flake8 not installed, skipping${NC}"
    fi
    echo
    
    echo "Type checking with mypy..."
    if command -v mypy &> /dev/null; then
        mypy src/ || echo -e "${YELLOW}Warning: mypy found issues (non-fatal)${NC}"
    else
        echo -e "${YELLOW}Warning: mypy not installed, skipping${NC}"
    fi
    echo
fi

# Summary
echo "=================================================="
echo "  Test Summary"
echo "=================================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi
