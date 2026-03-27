"""
Convert VulRL training data to Parquet format for SkyRL.

This script converts VulRL task data (CVE IDs, Vulhub paths, prompts) into
a Parquet file that can be consumed by SkyRL's training pipeline.

Expected input format (JSON/CSV/dict):
    - cve_id: str (e.g., "CVE-2024-28752")
    - vulhub_path: str (absolute path to Vulhub directory)
    - prompt: str (exploitation prompt)
    - max_steps: int (optional, default 20)

Output format (Parquet):
    Pandas DataFrame with columns matching input, ready for SkyRL training.

Usage:
    python create_parquet.py \
        --input tasks.json \
        --output train.parquet \
        --data-source json

    # Or create minimal test data:
    python create_parquet.py --create-test --output test.parquet
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any


def load_json_data(input_path: str) -> List[Dict[str, Any]]:
    """Load tasks from JSON file."""
    with open(input_path, "r") as f:
        data = json.load(f)
    
    # Handle both list of dicts and single dict
    if isinstance(data, dict):
        data = [data]
    
    return data


def load_csv_data(input_path: str) -> List[Dict[str, Any]]:
    """Load tasks from CSV file."""
    df = pd.read_csv(input_path)
    return df.to_dict("records")


def create_test_data() -> List[Dict[str, Any]]:
    """Create minimal test data for workflow testing."""
    return [
        {
            "cve_id": "CVE-2024-28752",
            "vulhub_path": "/data1/jph/vulhub/apache-cxf/CVE-2024-28752",
            "prompt": "Exploit the Apache CXF vulnerability to gain remote code execution. Start by analyzing the service and identifying the attack vector.",
            "max_steps": 10,
        },
        {
            "cve_id": "CVE-2023-12345",
            "vulhub_path": "/data1/jph/vulhub/test-app/CVE-2023-12345",
            "prompt": "Test SQL injection vulnerability in the authentication system. Attempt to bypass login and extract sensitive data.",
            "max_steps": 15,
        },
        {
            "cve_id": "CVE-2023-54321",
            "vulhub_path": "/data1/jph/vulhub/test-web/CVE-2023-54321",
            "prompt": "Identify and exploit XSS vulnerability in the web application. Try to inject JavaScript that can steal cookies.",
            "max_steps": 8,
        },
    ]


def validate_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and normalize task data.
    
    Required fields:
        - cve_id: str
        - vulhub_path: str (absolute path)
        - prompt: str
    
    Optional fields:
        - max_steps: int (default 20)
    """
    validated = []
    
    for i, task in enumerate(data):
        # Check required fields
        if "cve_id" not in task:
            raise ValueError(f"Task {i} missing required field: cve_id")
        if "vulhub_path" not in task:
            raise ValueError(f"Task {i} missing required field: vulhub_path")
        if "prompt" not in task:
            raise ValueError(f"Task {i} missing required field: prompt")
        
        # Validate vulhub_path is absolute
        vulhub_path = task["vulhub_path"]
        if not Path(vulhub_path).is_absolute():
            raise ValueError(f"Task {i}: vulhub_path must be absolute, got: {vulhub_path}")
        
        # Add defaults
        normalized = {
            "cve_id": str(task["cve_id"]),
            "vulhub_path": str(task["vulhub_path"]),
            "prompt": str(task["prompt"]),
            "max_steps": int(task.get("max_steps", 20)),
        }
        
        validated.append(normalized)
    
    return validated


def create_parquet(
    data: List[Dict[str, Any]],
    output_path: str,
) -> None:
    """
    Create Parquet file from task data.
    
    Args:
        data: List of task dictionaries
        output_path: Path to output Parquet file
    """
    # Validate data
    data = validate_data(data)
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Add SkyRL-specific columns if needed
    # For VulRL, we use the cve_id as both task_id and instance_id
    df["task_id"] = df["cve_id"]
    df["instance_id"] = df["cve_id"]
    
    # Save to Parquet
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    
    print(f"✓ Created Parquet file: {output_path}")
    print(f"  Total tasks: {len(df)}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst 3 rows:")
    print(df.head(3).to_string(index=False))


def main():
    parser = argparse.ArgumentParser(
        description="Convert VulRL task data to Parquet format for SkyRL training"
    )
    
    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--input",
        type=str,
        help="Input file path (JSON or CSV)",
    )
    input_group.add_argument(
        "--create-test",
        action="store_true",
        help="Create minimal test data instead of loading from file",
    )
    
    # Output
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output Parquet file path",
    )
    
    # Data source
    parser.add_argument(
        "--data-source",
        type=str,
        choices=["json", "csv"],
        default="json",
        help="Input file format (default: json)",
    )
    
    args = parser.parse_args()
    
    # Load or create data
    if args.create_test:
        print("Creating minimal test data...")
        data = create_test_data()
    else:
        print(f"Loading data from {args.input}...")
        if args.data_source == "json":
            data = load_json_data(args.input)
        elif args.data_source == "csv":
            data = load_csv_data(args.input)
        else:
            raise ValueError(f"Unsupported data source: {args.data_source}")
    
    print(f"Loaded {len(data)} tasks")
    
    # Create Parquet
    create_parquet(data, args.output)
    
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
