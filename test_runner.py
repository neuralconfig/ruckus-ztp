#!/usr/bin/env python3
"""
Test runner script for ZTP Agent.

This script provides easy ways to run different types of tests:
- Unit tests (fast, no hardware required)
- Integration tests (require real switch)
- All tests
"""
import os
import sys
import subprocess
import argparse

def run_command(cmd, description):
    """Run a command and handle the result."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    result = subprocess.run(cmd, capture_output=False, text=True)
    
    if result.returncode == 0:
        print(f"✅ {description} completed successfully")
    else:
        print(f"❌ {description} failed with exit code {result.returncode}")
    
    return result.returncode == 0

def check_dependencies():
    """Check if required dependencies are installed."""
    print("Checking dependencies...")
    
    try:
        import pytest
        print(f"✅ pytest {pytest.__version__} installed")
    except ImportError:
        print("❌ pytest not installed. Run: pip install pytest")
        return False
    
    try:
        import ztp_agent
        print("✅ ztp_agent package available")
    except ImportError:
        print("❌ ztp_agent package not installed. Run: pip install -e .")
        return False
    
    return True

def run_unit_tests():
    """Run unit tests only."""
    cmd = ["python", "-m", "pytest", "tests/unit/", "-v", "-m", "not integration"]
    return run_command(cmd, "Unit Tests")

def run_integration_tests():
    """Run integration tests with real hardware."""
    # Check for required environment variables
    switch_ip = os.getenv('SWITCH_IP')
    if not switch_ip:
        print("❌ SWITCH_IP environment variable not set")
        print("Set it to the IP address of your test switch:")
        print("export SWITCH_IP=192.168.1.100")
        return False
    
    print(f"Using test switch: {switch_ip}")
    print(f"Username: {os.getenv('SWITCH_USER', 'super')}")
    print(f"Password: {'*' * len(os.getenv('SWITCH_PASS', 'sp-admin'))}")
    
    cmd = ["python", "-m", "pytest", "tests/integration/", "-v", "-m", "integration", "-s"]
    return run_command(cmd, "Integration Tests")

def run_all_tests():
    """Run all tests."""
    cmd = ["python", "-m", "pytest", "tests/", "-v"]
    return run_command(cmd, "All Tests")

def run_test_installation():
    """Run the installation test."""
    cmd = ["python", "test_installation.py"]
    return run_command(cmd, "Installation Test")

def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="ZTP Agent Test Runner")
    parser.add_argument(
        "test_type",
        choices=["unit", "integration", "all", "install"],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--switch-ip",
        help="IP address of test switch (for integration tests)"
    )
    parser.add_argument(
        "--switch-user",
        default="super",
        help="Switch username (default: super)"
    )
    parser.add_argument(
        "--switch-pass",
        default="sp-admin", 
        help="Switch password (default: sp-admin)"
    )
    
    args = parser.parse_args()
    
    # Set environment variables for integration tests
    if args.switch_ip:
        os.environ['SWITCH_IP'] = args.switch_ip
    if args.switch_user:
        os.environ['SWITCH_USER'] = args.switch_user
    if args.switch_pass:
        os.environ['SWITCH_PASS'] = args.switch_pass
    
    print("ZTP Agent Test Runner")
    print("=" * 60)
    
    if not check_dependencies():
        sys.exit(1)
    
    success = False
    
    if args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "integration":
        success = run_integration_tests()
    elif args.test_type == "all":
        # Run installation test first
        if not run_test_installation():
            print("❌ Installation test failed, skipping other tests")
            sys.exit(1)
        
        # Run unit tests
        if not run_unit_tests():
            print("❌ Unit tests failed")
            sys.exit(1)
        
        # Run integration tests if switch is available
        if os.getenv('SWITCH_IP'):
            success = run_integration_tests()
        else:
            print("ℹ️  Skipping integration tests (no SWITCH_IP set)")
            success = True
    elif args.test_type == "install":
        success = run_test_installation()
    
    if success:
        print(f"\n✅ {args.test_type.title()} tests completed successfully!")
        sys.exit(0)
    else:
        print(f"\n❌ {args.test_type.title()} tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()