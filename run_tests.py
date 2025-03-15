#!/usr/bin/env python3
import subprocess
import sys
import os

# ANSI color codes for better readability
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"

# List of the first 17 tests needed for March 16th deadline
TESTS = [
    # partie 1
    "test_write_integer",
    "test_write_string",
    "test_get_size",
    # partie 2
    "test_create_db",
    "test_field_types",
    "test_list_table",
    "test_create_table",
    "test_create_table_alreay_exists",
    "test_delete_non_existing_table",
    "test_get_signature_non_existing_table",
    "test_create_table_twice",
    "test_delete_table",
    # partie 3
    "test_insert_in_table",
    "test_get_table_signature",
    "test_size_on_creation",
    "test_in_non_existing_table",
    "test_get_complete_table"
]

def run_test(test_name):
    """Run a single test and return whether it passed"""
    print(f"{BLUE}{BOLD}Running test: {test_name}{RESET}")
    
    # Run the test using pytest
    result = subprocess.run(
        ["python3", "-m", "pytest", f"test.py::{test_name}", "-v"],
        capture_output=True,
        text=True
    )
    
    # Print the output
    if result.returncode == 0:
        print(f"{GREEN}✓ PASSED{RESET}")
        return True
    else:
        print(f"{RED}✗ FAILED{RESET}")
        # Print the error message
        for line in result.stdout.split('\n'):
            if "FAILED" in line or "ERROR" in line:
                print(f"{RED}{line}{RESET}")
        return False

def main():
    """Run all tests and summarize results"""
    print(f"{YELLOW}{BOLD}Running the 17 tests required for March 16th deadline{RESET}")
    print(f"{YELLOW}=================================================={RESET}")
    
    passed = 0
    failed = []
    
    for test in TESTS:
        if run_test(test):
            passed += 1
        else:
            failed.append(test)
        print("-" * 50)
    
    # Print summary
    print(f"{YELLOW}{BOLD}Summary:{RESET}")
    print(f"Passed: {GREEN}{passed}/{len(TESTS)}{RESET}")
    
    if failed:
        print(f"Failed: {RED}{len(failed)}/{len(TESTS)}{RESET}")
        print(f"{RED}The following tests failed:{RESET}")
        for test in failed:
            print(f"{RED}- {test}{RESET}")
        
        if passed < len(TESTS):
            print(f"\n{RED}{BOLD}Warning: You need to pass all 17 tests by March 16th!{RESET}")
    else:
        print(f"{GREEN}{BOLD}Congratulations! All tests passed. You're ready for the March 16th deadline!{RESET}")

if __name__ == "__main__":
    main() 