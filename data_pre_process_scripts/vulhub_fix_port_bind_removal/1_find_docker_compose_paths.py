"""
Script to find all docker-compose.yml files in benchmark/vulhub/ and output JSONL with directory paths.

Output format: [{"path": "benchmark\\vulhub\\xstream\\CVE-2021-21351"}, ...]
"""

import os
import json
from pathlib import Path


def find_docker_compose_dirs(root_dir: str = "benchmark/vulhub") -> list:
    """
    Find all directories containing docker-compose.yml files.
    
    Args:
        root_dir: Root directory to search in
        
    Returns:
        List of relative paths to directories containing docker-compose.yml
    """
    compose_dirs = []
    
    # Get the repository root (3 levels up from this script)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    search_path = repo_root / root_dir
    
    if not search_path.exists():
        print(f"Warning: {search_path} does not exist")
        return compose_dirs
    
    # Walk through all subdirectories
    for dirpath, dirnames, filenames in os.walk(search_path):
        if "docker-compose.yml" in filenames:
            # Convert absolute path to relative path from repo root
            rel_path = Path(dirpath).relative_to(repo_root)
            # Convert to Windows path format with backslashes
            compose_dirs.append(str(rel_path).replace("/", "\\"))
    
    return sorted(compose_dirs)


def main():
    """Main function to generate JSONL output."""
    print("Searching for docker-compose.yml files in benchmark/vulhub/...")
    
    compose_dirs = find_docker_compose_dirs()
    
    print(f"Found {len(compose_dirs)} directories with docker-compose.yml")
    
    # Write to JSONL file
    output_file = Path(__file__).parent / "docker_compose_paths.jsonl"
    
    with open(output_file, "w", encoding="utf-8") as f:
        for path in compose_dirs:
            json.dump({"path": path}, f)
            f.write("\n")
    
    print(f"Output written to: {output_file}")
    print(f"\nFirst 5 entries:")
    for path in compose_dirs[:5]:
        print(f"  - {path}")
    
    if len(compose_dirs) > 5:
        print(f"  ... and {len(compose_dirs) - 5} more")


if __name__ == "__main__":
    main()
