#!/usr/bin/env python
"""
Universal nose to pytest migration tracking script.

This script helps track the progress of migrating from nose to pytest
and provides tools to assist with the migration process.

This file serves two purposes:
1. Track migration progress
2. Provide a convenient way to run tests during migration

Usage:
    ./pytest_migration.py init                    # Initialize migration tracking
    ./pytest_migration.py                         # Show migration status
    ./pytest_migration.py run tests               # Run tests directory
    ./pytest_migration.py run <path>              # Run specific test file/dir
    ./pytest_migration.py update <path>           # Mark a file as migrated
    ./pytest_migration.py scan [directory]        # Scan for test files
    ./pytest_migration.py config                  # Update configuration
"""

import os
import sys
import json
import re
import argparse
import datetime
import subprocess
from collections import OrderedDict
from typing import List, Dict, Tuple, Optional, Any

# Default configuration - will be updated during initialization
DEFAULT_CONFIG = {
    "project_root": os.path.dirname(os.path.abspath(__file__)),
    "test_directories": ["tests"],
    "migration_data_path": ".pytest_migration.json",
    "python_path_additions": [],
    "test_command": ["pytest", "-xvs"],
    "initialized": False,
    "initialized_date": None
}

def get_config():
    """Get or create configuration."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.pytest_migration_config.json')
    
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

CONFIG = get_config()
PROJECT_ROOT = CONFIG["project_root"]
MIGRATION_DATA_PATH = os.path.join(PROJECT_ROOT, CONFIG["migration_data_path"])
TEST_DIRECTORIES = [os.path.join(PROJECT_ROOT, directory) for directory in CONFIG["test_directories"]]

def save_config(config):
    """Save updated configuration."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.pytest_migration_config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def update_config():
    """Interactive configuration update."""
    global CONFIG, PROJECT_ROOT, MIGRATION_DATA_PATH, TEST_DIRECTORIES
    
    config = CONFIG.copy()
    
    print("\n=== Pytest Migration Configuration ===\n")
    print("Current configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    print("\nEnter new values (press Enter to keep current value)")
    
    # Project root
    new_root = input(f"Project root [{config['project_root']}]: ").strip()
    if new_root:
        config['project_root'] = os.path.abspath(new_root)
    
    # Test directories
    print(f"Test directories (comma-separated) [{','.join(config['test_directories'])}]: ", end="")
    new_dirs = input().strip()
    if new_dirs:
        config['test_directories'] = [d.strip() for d in new_dirs.split(',')]
    
    # Migration data path
    new_data_path = input(f"Migration data path [{config['migration_data_path']}]: ").strip()
    if new_data_path:
        config['migration_data_path'] = new_data_path
    
    # Python path additions
    print(f"Python path additions (comma-separated) [{','.join(config['python_path_additions'])}]: ", end="")
    new_paths = input().strip()
    if new_paths:
        config['python_path_additions'] = [p.strip() for p in new_paths.split(',')]
    
    # Test command
    print(f"Test command (space-separated) [{' '.join(config['test_command'])}]: ", end="")
    new_cmd = input().strip()
    if new_cmd:
        config['test_command'] = new_cmd.split()
    
    # Update global variables
    CONFIG = config
    PROJECT_ROOT = config["project_root"]
    MIGRATION_DATA_PATH = os.path.join(PROJECT_ROOT, config["migration_data_path"])
    TEST_DIRECTORIES = [os.path.join(PROJECT_ROOT, directory) for directory in config["test_directories"]]
    
    # Save configuration
    save_config(config)
    print("\nConfiguration updated successfully!")

# Default migration tracking data structure
def create_default_migration_data():
    """Create default migration tracking data structure based on config."""
    data = {
        "migrated_files": [],
        "total_tests": 0,
        "nose_tests": 0,
        "pytest_tests": 0,
        "directory_status": {},
        "last_updated": datetime.datetime.now().isoformat()
    }
    
    # Add directory status for each test directory
    for test_dir in CONFIG["test_directories"]:
        rel_path = os.path.relpath(os.path.join(PROJECT_ROOT, test_dir), PROJECT_ROOT)
        data["directory_status"][rel_path] = {
            "status": "PENDING",
            "migrated": 0,
            "total": 0
        }
    
    return data

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
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            return ('import nose' in content or 
                    'from nose' in content or 
                    'nose.tools' in content)
    except UnicodeDecodeError:
        # Skip binary files
        return False

def get_test_status():
    """Get the current migration status."""
    # Create default migration data if it doesn't exist
    if not os.path.exists(MIGRATION_DATA_PATH):
        # Scan directories to populate counts
        default_data = create_default_migration_data()
        
        for dir_key in default_data['directory_status']:
            dir_path = os.path.join(PROJECT_ROOT, dir_key)
            if os.path.exists(dir_path):
                test_files = scan_directory_for_tests(dir_path)
                default_data['directory_status'][dir_key]['total'] = len(test_files)
                default_data['total_tests'] += len(test_files)
                
                # Count nose tests
                nose_tests = sum(1 for file in test_files if is_nose_test(file))
                default_data['nose_tests'] += nose_tests
                
                # Test files that aren't nose tests are assumed to be pytest compatible
                pytest_tests = len(test_files) - nose_tests
                default_data['pytest_tests'] += pytest_tests
                default_data['directory_status'][dir_key]['migrated'] = pytest_tests
                
                # Update status if all files are already migrated
                if nose_tests == 0:
                    default_data['directory_status'][dir_key]['status'] = "DONE"
        
        # Save initial data
        with open(MIGRATION_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=2)
        
        return default_data
    
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
            dir_path = os.path.join(PROJECT_ROOT, dir_key)
            if file_path.startswith(dir_path):
                status['directory_status'][dir_key]['migrated'] += 1
                
                # Update the status if all files in the directory are migrated
                if status['directory_status'][dir_key]['migrated'] == status['directory_status'][dir_key]['total']:
                    status['directory_status'][dir_key]['status'] = "DONE"
        
        # Update overall counts
        if is_nose_test(file_path):
            status['nose_tests'] -= 1
            status['pytest_tests'] += 1
        
        # Update last updated timestamp
        status['last_updated'] = datetime.datetime.now().isoformat()
        
        # Save updated status
        with open(MIGRATION_DATA_PATH, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2)
        
        print(f"Updated status: Marked {rel_path} as migrated to pytest")
    else:
        print(f"File {rel_path} is already marked as migrated")

def rescan_tests(directory=None):
    """Rescan test directories and update counts."""
    status = get_test_status()
    
    # Reset counts
    status['total_tests'] = 0
    status['nose_tests'] = 0
    status['pytest_tests'] = 0
    
    # Function to scan a specific directory
    def scan_and_update(dir_key):
        dir_path = os.path.join(PROJECT_ROOT, dir_key)
        if os.path.exists(dir_path):
            test_files = scan_directory_for_tests(dir_path)
            status['directory_status'][dir_key]['total'] = len(test_files)
            status['total_tests'] += len(test_files)
            
            # Count nose tests
            nose_tests = sum(1 for file in test_files if is_nose_test(file))
            status['nose_tests'] += nose_tests
            
            # Calculate migrated tests
            migrated_files = [f for f in test_files if os.path.relpath(f, PROJECT_ROOT) in status['migrated_files']]
            status['directory_status'][dir_key]['migrated'] = len(migrated_files)
            
            # Update directory status
            if len(migrated_files) == len(test_files):
                status['directory_status'][dir_key]['status'] = "DONE"
            else:
                status['directory_status'][dir_key]['status'] = "PENDING"
    
    # Scan specified directory or all directories
    if directory:
        rel_dir = os.path.relpath(directory, PROJECT_ROOT)
        if rel_dir in status['directory_status']:
            scan_and_update(rel_dir)
        else:
            print(f"Warning: {rel_dir} is not registered as a test directory")
    else:
        for dir_key in status['directory_status']:
            scan_and_update(dir_key)
    
    # Update overall count of pytest tests
    status['pytest_tests'] = status['total_tests'] - status['nose_tests']
    
    # Update last updated timestamp
    status['last_updated'] = datetime.datetime.now().isoformat()
    
    # Save updated status
    with open(MIGRATION_DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=2)
    
    print(f"Rescanned {directory or 'all directories'} - found {status['total_tests']} tests ({status['nose_tests']} using nose)")

def display_status():
    """Display the current migration status."""
    status = get_test_status()
    
    print("\n=== Nose to Pytest Migration Progress ===\n")
    
    # Overall progress
    total = status['total_tests'] 
    migrated = status['pytest_tests']
    percent = (migrated / total) * 100 if total > 0 else 0
    
    last_updated = status.get('last_updated', 'unknown')
    if isinstance(last_updated, str) and last_updated.startswith('20'):
        try:
            dt = datetime.datetime.fromisoformat(last_updated)
            last_updated = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    print(f"Overall Progress: {migrated}/{total} tests migrated ({percent:.1f}%)")
    print(f"Remaining nose tests: {status['nose_tests']}")
    print(f"Migrated to pytest: {status['pytest_tests']}")
    print(f"Last updated: {last_updated}")
    print("\nDirectory Status:")
    
    for dir_key, dir_status in status['directory_status'].items():
        dir_percent = (dir_status['migrated'] / dir_status['total']) * 100 if dir_status['total'] > 0 else 0
        status_str = f"{dir_status['status']}: {dir_status['migrated']}/{dir_status['total']} ({dir_percent:.1f}%)"
        print(f"  - {dir_key}: {status_str}")
    
    print("\nNext steps:")
    if status['nose_tests'] > 0:
        print("  1. Migrate the remaining nose tests to pytest")
        print("  2. Run tests with: ./pytest_migration.py run <path>")
        print("  3. Update migration status: ./pytest_migration.py update <path>")
    else:
        print("  1. Re-enable coverage in pytest.ini if needed")
        print("  2. Remove nose from requirements")
        print("  3. Update CI configuration to use pytest")
    
    print("\n=== End of Migration Status ===\n")

def run_test(test_path):
    """Run tests with pytest."""
    # Add source directories to path
    for path in CONFIG.get("python_path_additions", []):
        sys.path.insert(0, os.path.join(PROJECT_ROOT, path))
    
    # Check if test_path is a file or directory
    abs_path = os.path.abspath(test_path) if os.path.isabs(test_path) else os.path.join(PROJECT_ROOT, test_path)
    
    print(f"\nRunning pytest on: {test_path}\n")
    
    # Use subprocess to ensure proper environment
    cmd = CONFIG.get("test_command", ["pytest", "-xvs"]) + [abs_path]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode

def initialize_migration():
    """Initialize migration tracking."""
    # First, update configuration
    update_config()
    
    # Set initialized flag
    CONFIG["initialized"] = True
    CONFIG["initialized_date"] = datetime.datetime.now().isoformat()
    save_config(CONFIG)
    
    # Create initial migration data
    status = get_test_status()
    
    print("\n=== Migration Initialized ===\n")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Test directories: {', '.join(CONFIG['test_directories'])}")
    print(f"Migration data: {MIGRATION_DATA_PATH}")
    print(f"Found {status['total_tests']} test files")
    print(f"  - {status['nose_tests']} using nose")
    print(f"  - {status['pytest_tests']} ready for pytest")
    
    print("\nMigration tracking is set up! Run without parameters to see status.")

def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Track and assist with nose to pytest migration")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize migration tracking")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run tests with pytest")
    run_parser.add_argument("path", help="Path to test file or directory")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Mark a file as migrated")
    update_parser.add_argument("path", help="Path to migrated test file")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for test files")
    scan_parser.add_argument("directory", nargs="?", help="Directory to scan (optional)")
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Update configuration")
    
    args = parser.parse_args()
    
    if args.command == "init":
        initialize_migration()
    elif args.command == "run":
        return run_test(args.path)
    elif args.command == "update":
        abs_path = os.path.abspath(args.path) if os.path.isabs(args.path) else os.path.join(PROJECT_ROOT, args.path)
        update_test_status(abs_path)
    elif args.command == "scan":
        if args.directory:
            dir_path = os.path.abspath(args.directory) if os.path.isabs(args.directory) else os.path.join(PROJECT_ROOT, args.directory)
            rescan_tests(dir_path)
        else:
            rescan_tests()
    elif args.command == "config":
        update_config()
    else:
        display_status()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())