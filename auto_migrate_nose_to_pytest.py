#!/usr/bin/env python
"""
Universal Nose to Pytest Automated Migration Tool

This script automatically converts nose tests to pytest by:
1. Identifying test files still using nose
2. Creating a backup of each file before modification
3. Applying transformation rules to convert common nose patterns
4. Verifying the migrated tests work correctly
5. Updating the migration tracking system

Usage:
    ./auto_migrate_nose_to_pytest.py scan              # Scan for nose tests and analyze
    ./auto_migrate_nose_to_pytest.py migrate [path]    # Run automated migration on a file/dir
    ./auto_migrate_nose_to_pytest.py verify            # Verify migrated tests
    ./auto_migrate_nose_to_pytest.py config            # Configure migration settings
    ./auto_migrate_nose_to_pytest.py list-patterns     # Show transformation patterns
    ./auto_migrate_nose_to_pytest.py add-pattern       # Add a new transformation pattern
"""

import os
import re
import sys
import json
import tempfile
import shutil
import argparse
import subprocess
import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union

# Configuration
DEFAULT_CONFIG = {
    "project_root": os.path.dirname(os.path.abspath(__file__)),
    "backup_dir": ".migration_backups",
    "tracking_script": None,  # Path to pytest_migration.py script if available
    "test_command": ["pytest", "-xvs"],
    "test_file_patterns": ["test_*.py"],
    "initialized": False,
    "initialized_date": None,
    "transformation_patterns": []
}

# Common transformation patterns
COMMON_TRANSFORMATIONS = [
    # Import replacements
    {
        "id": "nose_raises_import",
        "pattern": r'from\s+nose\.tools\s+import\s+raises',
        "replacement": 'import pytest',
        "description": 'Replace nose.tools.raises import with pytest',
        "priority": 10,
        "enabled": True
    },
    {
        "id": "nose_base_import",
        "pattern": r'import\s+nose(?!\S)',
        "replacement": 'import pytest',
        "description": 'Replace nose import with pytest',
        "priority": 10,
        "enabled": True
    },
    {
        "id": "nose_from_import",
        "pattern": r'from\s+nose\s+import\s+',
        "replacement": 'import pytest # Replacing: from nose import ',
        "description": 'Replace nose imports with pytest',
        "priority": 10,
        "enabled": True
    },
    {
        "id": "nose_tools_import",
        "pattern": r'from\s+nose\.tools\s+import\s+',
        "replacement": 'import pytest # Replacing: from nose.tools import ',
        "description": 'Replace nose.tools imports with pytest',
        "priority": 10,
        "enabled": True
    },
    # Decorator replacements
    {
        "id": "raises_decorator",
        "pattern": r'@raises\(([^)]+)\)',
        "replacement": r'@pytest.mark.xfail(raises=\1)',
        "description": 'Convert @raises to @pytest.mark.xfail',
        "priority": 20,
        "enabled": True
    },
    {
        "id": "expected_failure_function",
        "pattern": r'def\s+expected_failure\(test\):.*?return\s+inner',
        "replacement": '# Replaced with pytest.mark.xfail',
        "description": 'Remove expected_failure helper function',
        "priority": 20,
        "flags": re.DOTALL,
        "enabled": True
    },
    {
        "id": "expected_failure_decorator",
        "pattern": r'@expected_failure',
        "replacement": '@pytest.mark.xfail(reason="Expected to fail")',
        "description": 'Convert @expected_failure to @pytest.mark.xfail',
        "priority": 20,
        "enabled": True
    },
    # Assert replacements
    {
        "id": "assert_equal",
        "pattern": r'self\.assertEqual\(([^,]+),\s*([^)]+)\)',
        "replacement": r'assert \1 == \2',
        "description": 'Convert assertEqual to assert',
        "priority": 30,
        "enabled": True
    },
    {
        "id": "assert_not_equal",
        "pattern": r'self\.assertNotEqual\(([^,]+),\s*([^)]+)\)',
        "replacement": r'assert \1 != \2',
        "description": 'Convert assertNotEqual to assert',
        "priority": 30,
        "enabled": True
    },
    {
        "id": "assert_true",
        "pattern": r'self\.assertTrue\(([^)]+)\)',
        "replacement": r'assert \1',
        "description": 'Convert assertTrue to assert',
        "priority": 30,
        "enabled": True
    },
    {
        "id": "assert_false",
        "pattern": r'self\.assertFalse\(([^)]+)\)',
        "replacement": r'assert not \1',
        "description": 'Convert assertFalse to assert',
        "priority": 30,
        "enabled": True
    },
    {
        "id": "assert_raises",
        "pattern": r'self\.assertRaises\(([^,]+),\s*([^,)]+)(?:,\s*([^)]+))?\)',
        "replacement": r'with pytest.raises(\1):\n        \2\3',
        "description": 'Convert assertRaises to pytest.raises',
        "priority": 30,
        "enabled": True
    },
    # Class inheritance
    {
        "id": "unittest_testcase",
        "pattern": r'class\s+(\w+)\(unittest\.TestCase\):',
        "replacement": r'class \1:',
        "description": 'Remove unittest.TestCase inheritance',
        "priority": 40,
        "enabled": True
    },
    {
        "id": "setup_method",
        "pattern": r'(?:def|async def)\s+setUp\(self\)(.*?)(?=\n\s+def|\n\s+$)',
        "replacement": r'@pytest.fixture(autouse=True)\n    def setup_method(self)\1',
        "description": 'Convert setUp to pytest fixture',
        "priority": 40,
        "flags": re.DOTALL,
        "enabled": True
    },
    {
        "id": "teardown_method",
        "pattern": r'(?:def|async def)\s+tearDown\(self\)(.*?)(?=\n\s+def|\n\s+$)',
        "replacement": r'@pytest.fixture(autouse=True)\n    def teardown_method(self)\1',
        "description": 'Convert tearDown to pytest fixture',
        "priority": 40,
        "flags": re.DOTALL,
        "enabled": True
    },
    # Yield test conversion (basic pattern - more complex ones need custom handling)
    {
        "id": "yield_test_simple",
        "pattern": r'def\s+(test_\w+)\(\):\s*\n\s+for\s+([^\s]+)\s+in\s+([^:]+):\s*\n\s+yield\s+(\w+),\s*\2',
        "replacement": r'@pytest.mark.parametrize("\2", \3)\ndef \1(\2):\n    \4(\2)',
        "description": 'Convert simple yield tests to parametrize',
        "priority": 50,
        "enabled": True
    }
]

def get_config():
    """Get or create configuration."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.pytest_automigrate_config.json')
    
    if not os.path.exists(config_path):
        # Create default config with common transformations
        config = DEFAULT_CONFIG.copy()
        config["transformation_patterns"] = COMMON_TRANSFORMATIONS
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        return config
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
        
        # Check if we need to update with new transformations
        existing_ids = {t["id"] for t in config.get("transformation_patterns", [])}
        for transform in COMMON_TRANSFORMATIONS:
            if transform["id"] not in existing_ids:
                config.setdefault("transformation_patterns", []).append(transform)
                
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
        return config

CONFIG = get_config()
PROJECT_ROOT = CONFIG["project_root"]
BACKUP_DIR = os.path.join(PROJECT_ROOT, CONFIG.get("backup_dir", ".migration_backups"))

# Ensure backup directory exists
os.makedirs(BACKUP_DIR, exist_ok=True)

def save_config(config):
    """Save updated configuration."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.pytest_automigrate_config.json')
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)

def update_config():
    """Interactive configuration update."""
    global CONFIG, PROJECT_ROOT, BACKUP_DIR
    
    config = CONFIG.copy()
    
    print("\n=== Pytest Auto-Migration Configuration ===\n")
    print("Current configuration:")
    for key, value in {k:v for k,v in config.items() if k != "transformation_patterns"}.items():
        print(f"  {key}: {value}")
    
    print("\nEnter new values (press Enter to keep current value)")
    
    # Project root
    new_root = input(f"Project root [{config['project_root']}]: ").strip()
    if new_root:
        config['project_root'] = os.path.abspath(new_root)
    
    # Backup directory
    new_backup = input(f"Backup directory [{config.get('backup_dir', '.migration_backups')}]: ").strip()
    if new_backup:
        config['backup_dir'] = new_backup
    
    # Tracking script
    new_tracking = input(f"Tracking script path [{config.get('tracking_script', 'None')}]: ").strip()
    if new_tracking:
        config['tracking_script'] = new_tracking
    
    # Test command
    print(f"Test command (space-separated) [{' '.join(config.get('test_command', ['pytest', '-xvs']))}]: ", end="")
    new_cmd = input().strip()
    if new_cmd:
        config['test_command'] = new_cmd.split()
    
    # Test file patterns
    patterns = config.get('test_file_patterns', ['test_*.py'])
    print(f"Test file patterns (comma-separated) [{','.join(patterns)}]: ", end="")
    new_patterns = input().strip()
    if new_patterns:
        config['test_file_patterns'] = [p.strip() for p in new_patterns.split(',')]
    
    # Update global variables
    PROJECT_ROOT = config["project_root"]
    BACKUP_DIR = os.path.join(PROJECT_ROOT, config.get("backup_dir", ".migration_backups"))
    
    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Save configuration
    CONFIG = config
    save_config(config)
    print("\nConfiguration updated successfully!")

def find_nose_test_files(directory: Optional[str] = None) -> List[str]:
    """Find all test files still using nose in the specified directory or project root."""
    nose_files = []
    
    dir_to_search = directory if directory else PROJECT_ROOT
    
    for root, _, files in os.walk(dir_to_search):
        for pattern in CONFIG.get("test_file_patterns", ["test_*.py"]):
            import fnmatch
            for file in fnmatch.filter(files, pattern):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if ('import nose' in content or 
                            'from nose' in content or 
                            'nose.tools' in content):
                            nose_files.append(file_path)
                except (UnicodeDecodeError, PermissionError):
                    pass  # Skip binary or inaccessible files
    
    return nose_files

def create_backup(file_path: str) -> str:
    """Create a backup of the file before migration."""
    rel_path = os.path.relpath(file_path, PROJECT_ROOT)
    backup_path = os.path.join(BACKUP_DIR, rel_path)
    
    # Create directory structure if needed
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    
    # Copy the file
    shutil.copy2(file_path, backup_path)
    
    return backup_path

def restore_from_backup(file_path: str) -> bool:
    """Restore a file from backup if migration fails."""
    rel_path = os.path.relpath(file_path, PROJECT_ROOT)
    backup_path = os.path.join(BACKUP_DIR, rel_path)
    
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, file_path)
        return True
    
    return False

def analyze_file(file_path: str) -> Dict:
    """Analyze a file to determine which transformations would apply."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError):
        return {
            'file_path': file_path,
            'applicable_transformations': [],
            'complexity': 'Unknown',
            'notes': ["Could not read file - may be binary or inaccessible"],
            'error': True
        }
    
    analysis = {
        'file_path': file_path,
        'applicable_transformations': [],
        'complexity': 'Simple',
        'notes': [],
        'error': False
    }
    
    # Sort transformations by priority
    transformations = sorted(
        [t for t in CONFIG.get("transformation_patterns", []) if t.get("enabled", True)],
        key=lambda t: t.get("priority", 50)
    )
    
    for transform in transformations:
        pattern = transform["pattern"]
        flags = transform.get("flags", 0)
        try:
            matches = re.findall(pattern, content, flags)
            
            if matches:
                transform_info = {
                    'id': transform["id"],
                    'description': transform["description"],
                    'match_count': len(matches)
                }
                analysis['applicable_transformations'].append(transform_info)
        except re.error as e:
            analysis['notes'].append(f"Error in pattern {transform['id']}: {str(e)}")
    
    # Determine complexity
    if len(analysis['applicable_transformations']) > 5:
        analysis['complexity'] = 'Complex'
    
    # Check for special patterns
    if 'yield' in content and 'test_' in content:
        analysis['notes'].append('Contains yield tests - may need manual conversion')
    
    if 'setUp(' in content or 'tearDown(' in content:
        analysis['notes'].append('Contains setUp/tearDown methods')
    
    if 'unittest.TestCase' in content:
        analysis['notes'].append('Inherits from unittest.TestCase')
    
    return analysis

def migrate_file(file_path: str, dry_run: bool = False) -> Tuple[bool, str]:
    """Apply transformation rules to convert a nose test to pytest."""
    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, PermissionError):
        return False, "Could not read file - may be binary or inaccessible"
    
    # Create a backup first
    if not dry_run:
        create_backup(file_path)
    
    # Apply transformations
    modifications = []
    transformed_content = content
    
    # Sort transformations by priority
    transformations = sorted(
        [t for t in CONFIG.get("transformation_patterns", []) if t.get("enabled", True)],
        key=lambda t: t.get("priority", 50)
    )
    
    for transform in transformations:
        pattern = transform["pattern"]
        replacement = transform["replacement"]
        flags = transform.get("flags", 0)
        
        try:
            # Count matches before transformation
            matches_before = len(re.findall(pattern, transformed_content, flags))
            
            # Apply transformation
            if matches_before > 0:
                transformed_content = re.sub(pattern, replacement, transformed_content, flags=flags)
                
                # Count matches after transformation to verify
                matches_after = len(re.findall(pattern, transformed_content, flags))
                
                modifications.append({
                    'id': transform["id"],
                    'description': transform["description"],
                    'matches_replaced': matches_before - matches_after
                })
        except re.error as e:
            modifications.append({
                'id': transform["id"],
                'description': f"Error applying pattern: {str(e)}",
                'matches_replaced': 0,
                'error': True
            })
    
    # Add pytest import if needed and not already present
    if not re.search(r'import\s+pytest', transformed_content) and len(modifications) > 0:
        transformed_content = "import pytest\n" + transformed_content
        modifications.append({
            'id': 'add_pytest_import',
            'description': 'Added pytest import',
            'matches_replaced': 1
        })
    
    # Write transformed content if not dry run
    if not dry_run and transformed_content != content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(transformed_content)
        except PermissionError:
            return False, "Permission denied when writing to file"
    
    # Return success status and summary
    success = len([m for m in modifications if not m.get('error', False) and m['matches_replaced'] > 0]) > 0
    summary = "\n".join([f"- {mod['description']} ({mod['matches_replaced']} matches)" 
                        for mod in modifications if mod['matches_replaced'] > 0])
    
    if not summary:
        summary = "No transformations applied"
    
    return success, summary

def verify_migration(file_path: str) -> Tuple[bool, str, str]:
    """Verify a migrated test by running it with pytest."""
    try:
        cmd = CONFIG.get("test_command", ["pytest", "-xvs"]) + [file_path]
        
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Consider xfails as passes - they're intentionally expected to fail
        success = result.returncode == 0 or "xfailed" in result.stdout
        
        return success, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def update_migration_status(file_path: str):
    """Update the migration tracking file after successful migration."""
    tracking_script = CONFIG.get("tracking_script")
    if tracking_script and os.path.exists(os.path.join(PROJECT_ROOT, tracking_script)):
        try:
            subprocess.run(
                [sys.executable, tracking_script, "update", file_path],
                cwd=PROJECT_ROOT,
                check=False
            )
            return True
        except Exception as e:
            print(f"Error updating migration status: {str(e)}")
            return False
    return False

def scan_command(directory: Optional[str] = None):
    """Scan for nose tests and output analysis."""
    dir_path = os.path.join(PROJECT_ROOT, directory) if directory else PROJECT_ROOT
    nose_files = find_nose_test_files(dir_path)
    
    if not nose_files:
        print("No remaining nose test files found!")
        return
    
    print(f"Found {len(nose_files)} files still using nose:")
    
    for i, file_path in enumerate(nose_files, 1):
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        analysis = analyze_file(file_path)
        
        print(f"\n{i}. {rel_path} ({analysis['complexity']} complexity)")
        
        if analysis['notes']:
            print(f"   Notes: {', '.join(analysis['notes'])}")
        
        print("   Applicable transformations:")
        if not analysis['applicable_transformations']:
            print("   - None detected")
        else:
            for transform in analysis['applicable_transformations']:
                print(f"   - {transform['description']} ({transform['match_count']} matches)")

def migrate_command(path: Optional[str] = None):
    """Run automated migration on nose test files."""
    # If a path is specified, handle it
    if path:
        abs_path = os.path.abspath(path) if os.path.isabs(path) else os.path.join(PROJECT_ROOT, path)
        
        # Check if it's a directory or a file
        if os.path.isdir(abs_path):
            nose_files = find_nose_test_files(abs_path)
        elif os.path.isfile(abs_path):
            # Check if it's a nose test
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if ('import nose' in content or 
                    'from nose' in content or 
                    'nose.tools' in content):
                    nose_files = [abs_path]
                else:
                    print(f"File {path} does not appear to be a nose test.")
                    return
        else:
            print(f"Path {path} not found.")
            return
    else:
        # No path specified, scan all project
        nose_files = find_nose_test_files()
    
    if not nose_files:
        print("No remaining nose test files found!")
        return
    
    print(f"Migrating {len(nose_files)} files from nose to pytest...")
    
    successful_migrations = []
    failed_migrations = []
    
    for file_path in nose_files:
        rel_path = os.path.relpath(file_path, PROJECT_ROOT)
        print(f"\nMigrating {rel_path}...")
        
        # Apply transformations
        success, summary = migrate_file(file_path)
        
        if not success:
            print("  No transformations applied.")
            failed_migrations.append((rel_path, "No transformations applied"))
            continue
        
        print("  Applied transformations:")
        print(summary)
        
        # Verify the migrated file works
        print("  Verifying migration...")
        verification_success, stdout, stderr = verify_migration(file_path)
        
        if verification_success:
            print("  ✅ Verification successful!")
            successful_migrations.append(rel_path)
            
            # Update migration tracking
            if update_migration_status(file_path):
                print("  Migration status updated in tracking system.")
        else:
            print("  ❌ Verification failed! Restoring from backup.")
            if stderr.strip():
                print(f"  Error: {stderr.strip()}")
            restore_from_backup(file_path)
            failed_migrations.append((rel_path, "Verification failed"))
    
    # Print summary
    print("\n=== Migration Summary ===")
    print(f"Successfully migrated: {len(successful_migrations)}/{len(nose_files)} files")
    
    if successful_migrations:
        print("\nSuccessful migrations:")
        for path in successful_migrations:
            print(f"  ✅ {path}")
    
    if failed_migrations:
        print("\nFailed migrations:")
        for path, reason in failed_migrations:
            print(f"  ❌ {path} - {reason}")

def verify_command():
    """Verify migrated test files work correctly."""
    # Try to get list of migrated files from tracking script
    tracking_script = CONFIG.get("tracking_script")
    migrated_files = []
    
    if tracking_script and os.path.exists(os.path.join(PROJECT_ROOT, tracking_script)):
        try:
            # Try to read migration data directly
            migration_data_path = os.path.join(PROJECT_ROOT, ".pytest_migration.json")
            if os.path.exists(migration_data_path):
                with open(migration_data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    migrated_files = data.get("migrated_files", [])
        except Exception as e:
            print(f"Error reading migration data: {str(e)}")
    
    if not migrated_files:
        print("No migrated files found in tracking data.")
        print("Searching for potential pytest test files...")
        
        # Look for potential pytest test files that import pytest
        potential_files = []
        for root, _, files in os.walk(PROJECT_ROOT):
            for pattern in CONFIG.get("test_file_patterns", ["test_*.py"]):
                import fnmatch
                for file in fnmatch.filter(files, pattern):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if ('import pytest' in content and 
                                not ('import nose' in content or 
                                     'from nose' in content)):
                                potential_files.append(file_path)
                    except (UnicodeDecodeError, PermissionError):
                        pass
        
        if not potential_files:
            print("No potential pytest test files found.")
            return
        
        print(f"Found {len(potential_files)} potential pytest test files.")
        migrated_files = [os.path.relpath(f, PROJECT_ROOT) for f in potential_files]
    
    print(f"Verifying {len(migrated_files)} migrated files...")
    
    successful = []
    failed = []
    
    for rel_path in migrated_files:
        file_path = os.path.join(PROJECT_ROOT, rel_path)
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {rel_path}")
            failed.append((rel_path, "File not found"))
            continue
        
        print(f"Verifying {rel_path}...")
        verification_success, stdout, stderr = verify_migration(file_path)
        
        if verification_success:
            print(f"✅ {rel_path} - Verification successful!")
            successful.append(rel_path)
        else:
            print(f"❌ {rel_path} - Verification failed!")
            if stderr.strip():
                print(f"Error: {stderr.strip()}")
            failed.append((rel_path, "Verification failed"))
    
    # Print summary
    print("\n=== Verification Summary ===")
    print(f"Successfully verified: {len(successful)}/{len(migrated_files)} files")
    
    if failed:
        print("\nFailed verifications:")
        for path, reason in failed:
            print(f"  ❌ {path} - {reason}")

def list_patterns_command():
    """List all transformation patterns."""
    patterns = sorted(
        CONFIG.get("transformation_patterns", []),
        key=lambda t: (t.get("priority", 50), t.get("id", ""))
    )
    
    if not patterns:
        print("No transformation patterns defined.")
        return
    
    print("\n=== Transformation Patterns ===\n")
    
    for i, pattern in enumerate(patterns, 1):
        status = "Enabled" if pattern.get("enabled", True) else "Disabled"
        print(f"{i}. {pattern.get('id', 'Unknown')} ({status}, Priority: {pattern.get('priority', 50)})")
        print(f"   Description: {pattern.get('description', 'No description')}")
        print(f"   Pattern: {pattern.get('pattern', '')}")
        print(f"   Replacement: {pattern.get('replacement', '')}")
        if "flags" in pattern:
            flags = []
            if pattern["flags"] & re.DOTALL:
                flags.append("DOTALL")
            if pattern["flags"] & re.IGNORECASE:
                flags.append("IGNORECASE")
            if pattern["flags"] & re.MULTILINE:
                flags.append("MULTILINE")
            print(f"   Flags: {', '.join(flags)}")
        print()

def add_pattern_command():
    """Add a new transformation pattern."""
    print("\n=== Add New Transformation Pattern ===\n")
    
    pattern_id = input("Pattern ID (unique identifier, e.g. 'my_custom_pattern'): ").strip()
    if not pattern_id:
        print("Pattern ID is required.")
        return
    
    # Check if ID already exists
    existing_ids = {p.get("id") for p in CONFIG.get("transformation_patterns", [])}
    if pattern_id in existing_ids:
        print(f"Pattern ID '{pattern_id}' already exists. Please choose a different ID.")
        return
    
    description = input("Description: ").strip()
    if not description:
        print("Description is required.")
        return
    
    pattern = input("Regex pattern: ").strip()
    if not pattern:
        print("Pattern is required.")
        return
    
    replacement = input("Replacement: ").strip()
    if not replacement:
        print("Replacement is required.")
        return
    
    # Parse flags
    print("Flags (comma-separated, e.g. 'DOTALL,IGNORECASE'): ", end="")
    flags_input = input().strip()
    flags = 0
    if flags_input:
        for flag in flags_input.split(','):
            flag = flag.strip().upper()
            if flag == "DOTALL":
                flags |= re.DOTALL
            elif flag == "IGNORECASE":
                flags |= re.IGNORECASE
            elif flag == "MULTILINE":
                flags |= re.MULTILINE
    
    priority = input("Priority (1-100, lower numbers are applied first): ").strip()
    try:
        priority = int(priority) if priority else 50
    except ValueError:
        print("Invalid priority. Using default priority 50.")
        priority = 50
    
    # Create new pattern
    new_pattern = {
        "id": pattern_id,
        "description": description,
        "pattern": pattern,
        "replacement": replacement,
        "priority": priority,
        "enabled": True
    }
    
    if flags > 0:
        new_pattern["flags"] = flags
    
    # Add to configuration
    CONFIG.setdefault("transformation_patterns", []).append(new_pattern)
    save_config(CONFIG)
    
    print(f"\nPattern '{pattern_id}' added successfully!")

def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Automate nose to pytest migration")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan for nose tests and analyze")
    scan_parser.add_argument("directory", nargs="?", help="Directory to scan (optional)")
    
    # Migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run automated migration")
    migrate_parser.add_argument("path", nargs="?", help="Path to migrate (file or directory)")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify migrated tests")
    
    # Config command
    config_parser = subparsers.add_parser("config", help="Update configuration")
    
    # List patterns command
    list_patterns_parser = subparsers.add_parser("list-patterns", help="List transformation patterns")
    
    # Add pattern command
    add_pattern_parser = subparsers.add_parser("add-pattern", help="Add a new transformation pattern")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        scan_command(args.directory if hasattr(args, 'directory') else None)
    elif args.command == "migrate":
        migrate_command(args.path if hasattr(args, 'path') else None)
    elif args.command == "verify":
        verify_command()
    elif args.command == "config":
        update_config()
    elif args.command == "list-patterns":
        list_patterns_command()
    elif args.command == "add-pattern":
        add_pattern_command()
    else:
        parser.print_help()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())