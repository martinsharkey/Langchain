#!/usr/bin/env python3
"""
Test Runner - Executes tests and generates organized reports in test-output/

Usage:
    python run_tests.py                    # Run all tests
    python run_tests.py -k "test_discovery"  # Run specific test
    python run_tests.py -m "e2e"           # Run E2E tests only
    python run_tests.py --coverage         # Run with coverage
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_tests(args):
    """Run pytest with configured output structure."""
    
    # Ensure test-output directory exists
    test_output_dir = Path("test-output")
    test_output_dir.mkdir(exist_ok=True)
    (test_output_dir / "reports").mkdir(exist_ok=True)
    (test_output_dir / "coverage").mkdir(exist_ok=True)
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Add test path
    if args.tests:
        cmd.extend(args.tests)
    else:
        cmd.append("tests")
    
    # Verbosity
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")
    
    # Markers (e2e, unit, integration, etc.)
    if args.mark:
        cmd.extend(["-m", args.mark])
    
    # Keywords
    if args.keyword:
        cmd.extend(["-k", args.keyword])
    
    # Coverage
    if args.coverage or not args.no_coverage:
        cmd.extend([
            "--cov=src",
            "--cov-report=html:test-output/coverage/html",
            "--cov-report=term-missing"
        ])
    
    # HTML report
    cmd.extend([
        "--html=test-output/reports/index.html",
        "--self-contained-html",
        "--junit-xml=test-output/reports/junit.xml"
    ])
    
    # Strict markers
    cmd.append("--strict-markers")
    
    # Timeout
    cmd.extend(["--timeout", "300"])
    
    # Show slowest tests
    if args.durations:
        cmd.extend(["--durations", str(args.durations)])
    
    # Parallel execution
    if args.parallel:
        cmd.extend(["-n", "auto"])
    
    # Stop on first failure
    if args.exitfirst:
        cmd.append("-x")
    
    # Print command
    print("🧪 Running tests...")
    print(f"   Command: {' '.join(cmd)}\n")
    
    # Run pytest
    result = subprocess.run(cmd)
    
    # Print results location
    if result.returncode == 0:
        print("\n✅ Tests passed!")
    else:
        print("\n❌ Tests failed!")
    
    print(f"\n📊 Test reports:")
    print(f"   HTML Report: test-output/reports/index.html")
    print(f"   Coverage:    test-output/coverage/html/index.html")
    print(f"   JUnit:       test-output/reports/junit.xml")
    
    return result.returncode


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run tests with organized output structure",
        epilog="Test outputs go to: test-output/reports and test-output/coverage"
    )
    
    parser.add_argument(
        "tests",
        nargs="*",
        help="Specific test files or directories to run"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output (show all tests)"
    )
    
    parser.add_argument(
        "-m", "--mark",
        help="Run tests with specific marker (e.g., 'e2e', 'unit', 'integration')"
    )
    
    parser.add_argument(
        "-k", "--keyword",
        help="Run tests matching keyword expression"
    )
    
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Generate coverage report (default: enabled)"
    )
    
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Skip coverage report"
    )
    
    parser.add_argument(
        "-d", "--durations",
        type=int,
        default=10,
        help="Show N slowest tests (default: 10)"
    )
    
    parser.add_argument(
        "-n", "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    
    parser.add_argument(
        "-x", "--exitfirst",
        action="store_true",
        help="Stop on first failure"
    )
    
    args = parser.parse_args()
    
    sys.exit(run_tests(args))


if __name__ == "__main__":
    main()
