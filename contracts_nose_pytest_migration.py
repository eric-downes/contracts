#!/usr/bin/env python
"""
Migration tracking script for PyContracts nose to pytest migration.

This file serves two purposes:
1. Track migration progress
2. Provide a convenient way to run tests during migration

Usage:
    ./contracts_nose_pytest_migration.py                  # Show migration status
    ./contracts_nose_pytest_migration.py run tests        # Run tests directory
    ./contracts_nose_pytest_migration.py run <path>       # Run specific test file/dir
    ./contracts_nose_pytest_migration.py update <path>    # Mark a file as migrated
"""

import os
import sys
import json
import pytest
from collections import OrderedDict

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MIGRATION_DATA_PATH = os.path.join(PROJECT_ROOT, '.pytest_migration.json')
TEST_DIRECTORIES = [
    os.path.join(PROJECT_ROOT, 'tests'),
    os.path.join(PROJECT_ROOT, 'src', 'contracts', 'testing')
]

# Default migration tracking data structure
DEFAULT_MIGRATION_DATA = {
    "migrated_files": [],
    "total_tests": 0,
    "nose_tests": 0,
    "pytest_tests": 0,
    "directory_status": {
        "tests": {
            "status": "DONE",
            "migrated": 21,
            "total": 21
        },
        "src/contracts/testing": {
            "status": "PENDING",
            "migrated": 0,
            "total": 0  # Will be filled when scanning
        }
    }
}

def scan_directory_for_tests(directory):
    """Scan directory for test files and count them."""
    test_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                test_files.append(os.path.join(root, file))
    return test_files

def is_nose_test(file_path):
    """Check if the file uses nose testing framework."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        return ('import nose' in content or 
                'from nose' in content or 
                'nose.tools' in content)

def get_test_status():
    """Get the current migration status."""
    # Create default migration data if it doesn't exist
    if not os.path.exists(MIGRATION_DATA_PATH):
        # Scan directories to populate counts
        for dir_key in DEFAULT_MIGRATION_DATA['directory_status']:
            if dir_key == 'tests':
                # We know tests directory is fully migrated
                continue
                
            dir_path = os.path.join(PROJECT_ROOT, *dir_key.split('/'))
            if os.path.exists(dir_path):
                test_files = scan_directory_for_tests(dir_path)
                DEFAULT_MIGRATION_DATA['directory_status'][dir_key]['total'] = len(test_files)
                DEFAULT_MIGRATION_DATA['total_tests'] += len(test_files)
                
                # Count nose tests
                nose_tests = sum(1 for file in test_files if is_nose_test(file))
                DEFAULT_MIGRATION_DATA['nose_tests'] += nose_tests
        
        # Add the known pytest tests
        DEFAULT_MIGRATION_DATA['pytest_tests'] += DEFAULT_MIGRATION_DATA['directory_status']['tests']['migrated']
        DEFAULT_MIGRATION_DATA['total_tests'] += DEFAULT_MIGRATION_DATA['directory_status']['tests']['total']
        
        # Save initial data
        with open(MIGRATION_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_MIGRATION_DATA, f, indent=2)
        
        return DEFAULT_MIGRATION_DATA
    
    # Load existing data
    with open(MIGRATION_DATA_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def update_test_status(file_path):
    """Mark a test file as migrated."""
    status = get_test_status()
    
    rel_path = os.path.relpath(file_path, PROJECT_ROOT)
    if rel_path not in status['migrated_files']:
        status['migrated_files'].append(rel_path)
        
        # Update directory status
        for dir_key in status['directory_status']:
            dir_path = os.path.join(PROJECT_ROOT, *dir_key.split('/'))
            if file_path.startswith(dir_path):
                status['directory_status'][dir_key]['migrated'] += 1
                
                # Update the status if all files in the directory are migrated
                if status['directory_status'][dir_key]['migrated'] == status['directory_status'][dir_key]['total']:
                    status['directory_status'][dir_key]['status'] = "DONE"
        
        # Update overall counts
        if is_nose_test(file_path):
            status['nose_tests'] -= 1
            status['pytest_tests'] += 1
        
        # Save updated status
        with open(MIGRATION_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        
        print(f"Updated status: Marked {rel_path} as migrated to pytest")
    else:
        print(f"File {rel_path} is already marked as migrated")

def display_status():
    """Display the current migration status."""
    status = get_test_status()
    
    print("\n=== PyContracts nose to pytest Migration Progress ===\n")
    
    # Overall progress
    total = status['total_tests']
    migrated = len(status['migrated_files']) + status['directory_status']['tests']['migrated']
    percent = (migrated / total) * 100 if total > 0 else 0
    
    print(f"Overall Progress: {migrated}/{total} tests migrated ({percent:.1f}%)")
    print(f"Remaining nose tests: {status['nose_tests']}")
    print(f"Migrated to pytest: {status['pytest_tests']}")
    print("\nDirectory Status:")
    
    for dir_key, dir_status in status['directory_status'].items():
        dir_percent = (dir_status['migrated'] / dir_status['total']) * 100 if dir_status['total'] > 0 else 0
        status_str = f"{dir_status['status']}: {dir_status['migrated']}/{dir_status['total']} ({dir_percent:.1f}%)"
        print(f"  - {dir_key}: {status_str}")
    
    print("\nNext steps:")
    if status['nose_tests'] > 0:
        print("  1. Migrate the remaining nose tests to pytest")
        print("  2. Run tests with: ./contracts_nose_pytest_migration.py run <path>")
        print("  3. Update migration status: ./contracts_nose_pytest_migration.py update <path>")
    else:
        print("  1. Re-enable coverage in pytest.ini if needed")
        print("  2. Remove nose from requirements")
        print("  3. Update CI configuration to use pytest")
    
    print("\n=== End of Migration Status ===\n")

def run_test(test_path):
    """Run tests with pytest."""
    # Add source directory to path
    src_dir = os.path.join(PROJECT_ROOT, 'src')
    sys.path.insert(0, src_dir)
    
    print(f"\nRunning pytest on: {test_path}\n")
    result = pytest.main(["-v", test_path])
    return result

def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) == 1:
        display_status()
        return 0
    
    if len(sys.argv) >= 2:
        command = sys.argv[1]
        
        if command == 'run':
            if len(sys.argv) >= 3:
                test_path = sys.argv[2]
                abs_path = os.path.join(PROJECT_ROOT, test_path) if not os.path.isabs(test_path) else test_path
                return run_test(abs_path)
            else:
                print("Error: Missing test path. Usage: ./contracts_nose_pytest_migration.py run <path>")
                return 1
        
        elif command == 'update':
            if len(sys.argv) >= 3:
                file_path = sys.argv[2]
                abs_path = os.path.join(PROJECT_ROOT, file_path) if not os.path.isabs(file_path) else file_path
                update_test_status(abs_path)
                return 0
            else:
                print("Error: Missing file path. Usage: ./contracts_nose_pytest_migration.py update <path>")
                return 1
        
        else:
            print(f"Unknown command: {command}")
            print("Usage: ./contracts_nose_pytest_migration.py [run|update] [path]")
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())