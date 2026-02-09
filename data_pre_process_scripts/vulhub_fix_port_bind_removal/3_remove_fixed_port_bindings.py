"""
Script to remove fixed port bindings from docker-compose.yml files.

Process:
1. Read paths from docker_compose_paths.jsonl (or use test paths)
2. For each path:
   - Check if already processed (filters)
   - Copy docker-compose.yml to docker-compose-original.yml
   - Remove fixed port bindings (e.g., "8080:8080" -> "8080")
   - Save modified docker-compose.yml

Filters to prevent re-processing:
a) Skip if docker-compose-original.yml exists AND
b) docker-compose.yml is identical to docker-compose-original.yml OR
c) docker-compose.yml has no fixed port bindings
"""

import os
import json
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any
import yaml


def load_paths_from_jsonl(jsonl_file: Path) -> List[str]:
    """Load paths from JSONL file."""
    paths = []
    if not jsonl_file.exists():
        print(f"Warning: {jsonl_file} not found")
        return paths
    
    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line.strip())
            paths.append(data["path"])
    
    return paths


def has_fixed_port_bindings(compose_data: Dict[str, Any]) -> bool:
    """
    Check if docker-compose data has any fixed port bindings.
    
    Fixed bindings look like: "8080:8080" or "127.0.0.1:8080:8080"
    Ephemeral bindings look like: "8080" or 8080
    """
    if not compose_data or "services" not in compose_data:
        return False
    
    for service_name, service_config in compose_data.get("services", {}).items():
        ports = service_config.get("ports", [])
        for port in ports:
            port_str = str(port)
            # Check if it contains a colon (fixed binding)
            if ":" in port_str:
                return True
    
    return False


def remove_fixed_bindings(compose_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove fixed port bindings from docker-compose data.
    
    Converts:
    - "8080:8080" -> "8080"
    - "127.0.0.1:8080:8080" -> "8080"
    - "8080:8081" -> "8081" (uses container port)
    - 8080 -> 8080 (no change)
    """
    if not compose_data or "services" not in compose_data:
        return compose_data
    
    for service_name, service_config in compose_data.get("services", {}).items():
        if "ports" not in service_config:
            continue
        
        new_ports = []
        for port in service_config["ports"]:
            port_str = str(port)
            
            if ":" in port_str:
                # Extract container port (last part after colon)
                parts = port_str.split(":")
                container_port = parts[-1]
                
                # Keep as string if original was string, convert to int if it looks like a plain number
                if container_port.isdigit() and "/" not in container_port:
                    new_ports.append(int(container_port))
                else:
                    new_ports.append(container_port)
            else:
                # Already ephemeral or just a number
                new_ports.append(port)
        
        service_config["ports"] = new_ports
    
    return compose_data


def files_are_identical(file1: Path, file2: Path) -> bool:
    """Check if two files have identical contents."""
    if not file1.exists() or not file2.exists():
        return False
    
    with open(file1, "r", encoding="utf-8") as f1, open(file2, "r", encoding="utf-8") as f2:
        return f1.read() == f2.read()


def should_process(compose_file: Path, original_file: Path) -> tuple[bool, str]:
    """
    Determine if a docker-compose.yml should be processed.
    
    Returns: (should_process, reason)
    """
    # If original doesn't exist, we should process
    if not original_file.exists():
        return True, "No backup exists yet"
    
    # Check if compose has fixed bindings
    try:
        with open(compose_file, "r", encoding="utf-8") as f:
            compose_data = yaml.safe_load(f)
        
        if not has_fixed_port_bindings(compose_data):
            return False, "docker-compose.yml has no fixed port bindings (already processed)"
        
        # Has fixed bindings - check if it's identical to original
        if files_are_identical(compose_file, original_file):
            # Identical to original but has fixed bindings - someone reverted or first time
            # We should process it to remove the fixed bindings
            return True, "Has fixed port bindings (needs processing)"
        
        # Has fixed bindings and is different from original - also needs processing
        return True, "Has fixed port bindings and differs from original"
    
    except Exception as e:
        return False, f"Error reading compose file: {e}"


def process_compose_file(compose_path: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Process a single docker-compose.yml file.
    
    Returns: Dictionary with processing results
    """
    result = {
        "path": str(compose_path.parent),
        "status": "unknown",
        "reason": "",
        "changes_made": False
    }
    
    compose_file = compose_path
    original_file = compose_path.parent / "docker-compose-original.yml"
    
    if not compose_file.exists():
        result["status"] = "skipped"
        result["reason"] = "docker-compose.yml not found"
        return result
    
    # Check if should process
    should_proc, reason = should_process(compose_file, original_file)
    
    if not should_proc:
        result["status"] = "skipped"
        result["reason"] = reason
        return result
    
    try:
        # Read original compose file
        with open(compose_file, "r", encoding="utf-8") as f:
            original_content = f.read()
            compose_data = yaml.safe_load(original_content)
        
        # Check if has fixed bindings
        if not has_fixed_port_bindings(compose_data):
            result["status"] = "skipped"
            result["reason"] = "No fixed port bindings found"
            return result
        
        if not dry_run:
            # Create backup if it doesn't exist
            if not original_file.exists():
                shutil.copy2(compose_file, original_file)
                print(f"  [+] Created backup: {original_file.name}")
            
            # Remove fixed bindings
            modified_data = remove_fixed_bindings(compose_data)
            
            # Write modified compose file
            with open(compose_file, "w", encoding="utf-8") as f:
                yaml.dump(modified_data, f, default_flow_style=False, sort_keys=False)
            
            result["status"] = "processed"
            result["reason"] = f"Removed fixed port bindings ({reason})"
            result["changes_made"] = True
        else:
            result["status"] = "would_process"
            result["reason"] = f"DRY RUN: Would remove fixed port bindings ({reason})"
        
        return result
    
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        return result


def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Remove fixed port bindings from docker-compose.yml files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--test", action="store_true", help="Use test paths instead of full list")
    parser.add_argument("--paths", nargs="+", help="Specific paths to process (relative to repo root)")
    args = parser.parse_args()
    
    # Get repo root
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    
    # Determine which paths to process
    if args.paths:
        paths = args.paths
        print(f"Processing {len(paths)} specified path(s)...")
    elif args.test:
        # Test paths as specified
        paths = [
            r"benchmark\vulhub\apereo-cas\4.1-rce",
            r"benchmark\vulhub\apache-cxf\CVE-2024-28752"
        ]
        print("TEST MODE: Using example paths...")
    else:
        # Load from JSONL
        jsonl_file = script_dir / "docker_compose_paths.jsonl"
        paths = load_paths_from_jsonl(jsonl_file)
        print(f"Loaded {len(paths)} paths from {jsonl_file.name}")
    
    if not paths:
        print("No paths to process!")
        return
    
    # Process each path
    results = {
        "processed": [],
        "skipped": [],
        "would_process": [],
        "error": []
    }
    
    for path in paths:
        compose_path = repo_root / path / "docker-compose.yml"
        print(f"\n{'='*60}")
        print(f"Processing: {path}")
        
        result = process_compose_file(compose_path, dry_run=args.dry_run)
        results[result["status"]].append(result)
        
        # Print result
        if result["status"] == "processed":
            print(f"  [OK] {result['reason']}")
        elif result["status"] == "would_process":
            print(f"  [DRY-RUN] {result['reason']}")
        elif result["status"] == "skipped":
            print(f"  [SKIP] {result['reason']}")
        elif result["status"] == "error":
            print(f"  [ERROR] {result['reason']}")
    
    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Processed:       {len(results['processed'])}")
    print(f"Would process:   {len(results['would_process'])}")
    print(f"Skipped:         {len(results['skipped'])}")
    print(f"Errors:          {len(results['error'])}")
    print(f"Total:           {len(paths)}")
    
    if args.dry_run:
        print("\n[WARNING] This was a DRY RUN. No files were modified.")
        print("          Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
