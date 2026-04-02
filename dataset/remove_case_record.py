#!/usr/bin/env python3
"""
Remove Case Record Script
Removes a vulnerability test case folder from the result directory.

Usage:
    python remove_case_record.py <folder_name>
    python remove_case_record.py --vulhub-path <vulhub_path>

Examples:
    python remove_case_record.py activemq_CVE-2016-3088
    python remove_case_record.py --vulhub-path activemq/CVE-2016-3088
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def get_result_dir():
    """Get the result directory from environment or use default."""
    return os.environ.get("RESULT_DIR", "/data1/jph/tmp/result_v4")


def folder_name_from_vulhub_path(vulhub_path):
    """Convert vulhub_path to folder_name format."""
    return vulhub_path.replace("/", "_")


def find_folder_by_vulhub_path(result_dir, vulhub_path):
    """Find folder by checking metadata.json files."""
    result_path = Path(result_dir)
    if not result_path.exists():
        return None
    
    for folder in result_path.iterdir():
        if not folder.is_dir():
            continue
        
        metadata_file = folder / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    if metadata.get("vulhub_path") == vulhub_path:
                        return folder.name
            except (json.JSONDecodeError, IOError):
                continue
    
    return None


def remove_case_folder(result_dir, folder_name):
    """Remove the specified case folder."""
    folder_path = Path(result_dir) / folder_name
    
    if not folder_path.exists():
        print(f"Error: Folder does not exist: {folder_path}")
        return False
    
    if not folder_path.is_dir():
        print(f"Error: Path is not a directory: {folder_path}")
        return False
    
    try:
        shutil.rmtree(folder_path)
        print(f"✓ Successfully removed: {folder_path}")
        return True
    except Exception as e:
        print(f"Error: Failed to remove {folder_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Remove vulnerability test case folder from result directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python remove_case_record.py activemq_CVE-2016-3088
  python remove_case_record.py --vulhub-path activemq/CVE-2016-3088
  RESULT_DIR=/custom/path python remove_case_record.py activemq_CVE-2016-3088
        """
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "folder_name",
        nargs="?",
        help="Folder name to remove (e.g., activemq_CVE-2016-3088)"
    )
    group.add_argument(
        "--vulhub-path",
        help="Vulhub path to remove (e.g., activemq/CVE-2016-3088)"
    )
    
    parser.add_argument(
        "--result-dir",
        help="Result directory (defaults to RESULT_DIR env var or /data1/jph/tmp/result_v4)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually removing"
    )
    
    args = parser.parse_args()
    
    result_dir = args.result_dir or get_result_dir()
    
    if args.vulhub_path:
        folder_name = find_folder_by_vulhub_path(result_dir, args.vulhub_path)
        if not folder_name:
            print(f"Error: Could not find folder for vulhub_path: {args.vulhub_path}")
            sys.exit(1)
        print(f"Found folder: {folder_name} for vulhub_path: {args.vulhub_path}")
    else:
        folder_name = args.folder_name
    
    folder_path = Path(result_dir) / folder_name
    
    if args.dry_run:
        if folder_path.exists():
            print(f"[DRY RUN] Would remove: {folder_path}")
            sys.exit(0)
        else:
            print(f"[DRY RUN] Folder does not exist: {folder_path}")
            sys.exit(1)
    
    success = remove_case_folder(result_dir, folder_name)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
