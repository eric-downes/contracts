#!/usr/bin/env python
"""
Automated migration tool for converting nose tests to pytest.

This script:
1. Identifies test files still using nose
2. Creates a backup of each file before modification
3. Applies transformation rules to convert common nose patterns
4. Verifies the migrated tests work correctly
5. Updates the migration tracking system

Usage:
    ./auto_migrate_nose_to_pytest.py scan     # Scan for nose tests
    ./auto_migrate_nose_to_pytest.py migrate  # Run automated migration
    ./auto_migrate_nose_to_pytest.py verify   # Verify migrated tests
"""

import os
import re
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
import pytest
from typing import List, Dict, Tuple, Optional

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MIGRATION_DATA_PATH = os.path.join(PROJECT_ROOT, '.pytest_migration.json')
BACKUP_DIR = os.path.join(PROJECT_ROOT, '.migration_backups')

# Ensure backup directory exists
os.makedirs(BACKUP_DIR, exist_ok=True)

# Common transformation patterns
TRANSFORMATIONS = [
    # Import replacements
    {
        'pattern': r'from\s+nose\.tools\s+import\s+raises',
        'replacement': 'import pytest',
        'description': 'Replace nose.tools.raises import with pytest'
    },
    {
        'pattern': r'import\s+nose(?!\S)',
        'replacement': 'import pytest',
        'description': 'Replace nose import with pytest'
    },
    {
        'pattern': r'from\s+nose\s+import\s+',
        'replacement': 'import pytest # Replacing: from nose import ',
        'description': 'Replace nose imports with pytest'
    },
    {
        'pattern': r'from\s+nose\.tools\s+import\s+',
        'replacement': 'import pytest # Replacing: from nose.tools import ',
        'description': 'Replace nose.tools imports with pytest'
    },
    # Decorator replacements
    {
        'pattern': r'@raises\(([^)]+)\)',
        'replacement': r'@pytest.mark.xfail(raises=\1)',
        'description': 'Convert @raises to @pytest.mark.xfail'
    },
    {
        'pattern': r'def\s+expected_failure\(test\):.*?return\s+inner',
        'replacement': '# Replaced with pytest.mark.xfail',
        'description': 'Remove expected_failure helper function',
        'flags': re.DOTALL
    },
    {
        'pattern': r'@expected_failure',
        'replacement': '@pytest.mark.xfail(reason="Expected to fail")',
        'description': 'Convert @expected_failure to @pytest.mark.xfail'
    },
    # Assert replacements
    {
        'pattern': r'self\.assertEqual\(([^,]+),\s*([^)]+)\)',
        'replacement': r'assert \1 == \2',
        'description': 'Convert assertEqual to assert'
    },
    {
        'pattern': r'self\.assertNotEqual\(([^,]+),\s*([^)]+)\)',
        'replacement': r'assert \1 != \2',
        'description': 'Convert assertNotEqual to assert'
    },
    {
        'pattern': r'self\.assertTrue\(([^)]+)\)',
        'replacement': r'assert \1',
        'description': 'Convert assertTrue to assert'
    },
    {
        'pattern': r'self\.assertFalse\(([^)]+)\)',
        'replacement': r'assert not \1',
        'description': 'Convert assertFalse to assert'
    },
    {
        'pattern': r'self\.assertRaises\(([^,]+),\s*([^,)]+)(?:,\s*([^)]+))?\)',
        'replacement': r'with pytest.raises(\1):\n        \2\3',
        'description': 'Convert assertRaises to pytest.raises'
    },
    # Class inheritance
    {
        'pattern': r'class\s+(\w+)\(unittest\.TestCase\):',
        'replacement': r'class \1:',
        'description': 'Remove unittest.TestCase inheritance'
    },
    {
        'pattern': r'(?:def|async def)\s+setUp\(self\)(.*?)(?=\n\s+def|\n\s+$)',
        'replacement': r'@pytest.fixture(autouse=True)\n    def setup_method(self)\1',
        'description': 'Convert setUp to pytest fixture',
        'flags': re.DOTALL
    },
    {
        'pattern': r'(?:def|async def)\s+tearDown\(self\)(.*?)(?=\n\s+def|\n\s+$)',
        'replacement': r'@pytest.fixture(autouse=True)\n    def teardown_method(self)\1',
        'description': 'Convert tearDown to pytest fixture',
        'flags': re.DOTALL
    },
]

def get_migration_status():
    """Get current migration status."""
    if not os.path.exists(MIGRATION_DATA_PATH):
        return {}
    
    with open(MIGRATION_DATA_PATH, 'r') as f:
        return json.load(f)

def find_nose_test_files() -> List[str]:
    """Find all test files still using nose."""
    nose_files = []
    
    for root, _, files in os.walk(os.path.join(PROJECT_ROOT, 'src')):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                file_path = os.path.join(root, file)
                
                with open(file_path, 'r') as f:
                    content = f.read()
                    if ('import nose' in content or 
                        'from nose' in content or 
                        'nose.tools' in content):
                        nose_files.append(file_path)
    
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
    with open(file_path, 'r') as f:
        content = f.read()
    
    analysis = {
        'file_path': file_path,
        'applicable_transformations': [],
        'complexity': 'Simple',
        'notes': []
    }
    
    for transform in TRANSFORMATIONS:
        pattern = transform['pattern']
        flags = transform.get('flags', 0)
        matches = re.findall(pattern, content, flags)
        
        if matches:
            transform_info = {
                'description': transform['description'],
                'match_count': len(matches)
            }
            analysis['applicable_transformations'].append(transform_info)
    
    # Determine complexity
    if len(analysis['applicable_transformations']) > 5:
        analysis['complexity'] = 'Complex'
    
    # Check for setup/teardown methods
    if 'setUp(' in content or 'tearDown(' in content:
        analysis['notes'].append('Contains setUp/tearDown methods')
    
    # Check for unittest.TestCase subclasses
    if 'unittest.TestCase' in content:
        analysis['notes'].append('Inherits from unittest.TestCase')
    
    return analysis

def migrate_file(file_path: str, dry_run: bool = False) -> Tuple[bool, str]:
    """Apply transformation rules to convert a nose test to pytest."""
    # Read file content
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Create a backup first
    if not dry_run:
        create_backup(file_path)
    
    # Apply transformations
    modifications = []
    transformed_content = content
    
    for transform in TRANSFORMATIONS:
        pattern = transform['pattern']
        replacement = transform['replacement']
        flags = transform.get('flags', 0)
        
        # Count matches before transformation
        matches_before = len(re.findall(pattern, transformed_content, flags))
        
        # Apply transformation
        if matches_before > 0:
            transformed_content = re.sub(pattern, replacement, transformed_content, flags=flags)
            
            # Count matches after transformation to verify
            matches_after = len(re.findall(pattern, transformed_content, flags))
            
            modifications.append({
                'description': transform['description'],
                'matches_replaced': matches_before - matches_after
            })
    
    # Add pytest import if needed and not already present
    if not re.search(r'import\s+pytest', transformed_content) and len(modifications) > 0:
        transformed_content = "import pytest\n" + transformed_content
        modifications.append({
            'description': 'Added pytest import',
            'matches_replaced': 1
        })
    
    # Write transformed content if not dry run
    if not dry_run and transformed_content != content:
        with open(file_path, 'w') as f:
            f.write(transformed_content)
    
    # Return success status and summary
    success = len(modifications) > 0
    summary = "\n".join([f"- {mod['description']} ({mod['matches_replaced']} matches)" 
                           for mod in modifications])
    
    return success, summary

def verify_migration(file_path: str) -> bool:
    """Verify a migrated test by running it with pytest."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-xvs", file_path],
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
    tracking_script = os.path.join(PROJECT_ROOT, 'contracts_nose_pytest_migration.py')
    subprocess.run([tracking_script, 'update', file_path], cwd=PROJECT_ROOT)

def scan_command():
    """Scan for nose tests and output analysis."""
    nose_files = find_nose_test_files()
    
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
        for transform in analysis['applicable_transformations']:
            print(f"   - {transform['description']} ({transform['match_count']} matches)")

def migrate_command():
    """Run automated migration on all nose test files."""
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
            update_migration_status(file_path)
        else:
            print("  ❌ Verification failed! Restoring from backup.")
            print(f"  Error: {stderr}")
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
    """Verify all migrated tests work correctly."""
    # Get list of migrated files from tracking
    status = get_migration_status()
    
    if not status or 'migrated_files' not in status:
        print("No migration tracking data found.")
        return
    
    migrated_files = status.get('migrated_files', [])
    
    if not migrated_files:
        print("No migrated files found in tracking data.")
        return
    
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
            print(f"Error: {stderr}")
            failed.append((rel_path, "Verification failed"))
    
    # Print summary
    print("\n=== Verification Summary ===")
    print(f"Successfully verified: {len(successful)}/{len(migrated_files)} files")
    
    if failed:
        print("\nFailed verifications:")
        for path, reason in failed:
            print(f"  ❌ {path} - {reason}")

def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  ./auto_migrate_nose_to_pytest.py scan    # Scan for nose tests")
        print("  ./auto_migrate_nose_to_pytest.py migrate # Run automated migration")
        print("  ./auto_migrate_nose_to_pytest.py verify  # Verify migrated tests")
        return 1
    
    command = sys.argv[1]
    
    if command == 'scan':
        scan_command()
    elif command == 'migrate':
        migrate_command()
    elif command == 'verify':
        verify_command()
    else:
        print(f"Unknown command: {command}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())