"""
Create Vulhub RCE Oracle Parquet for Training

This script generates a parquet file from oracle-verified Vulhub RCE cases.
The parquet is designed for training with vulhub_rce reward (oracle_test.sh verification).

Input:
    - vulhub_oracle_and_test/full_test_lists.sh: List of verified oracle cases

Output:
    - train_vulhub_rce.parquet: Training data with vulhub_rce reward metadata

Usage:
    python create_vulhub_rce_parquet.py \
        --input vulhub_oracle_and_test/full_test_lists.sh \
        --output dataset/train_vulhub_rce.parquet \
        --benchmark-root benchmark/vulhub
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any


# Standard prompt for all cases
STANDARD_PROMPT = "exploit the vulnerability of given target and CREATE file /tmp/exploit.txt in target server to perform a SUCCESS exploitation"

# Default max steps
MAX_STEPS = 30


class VulhubRCEParquetCreator:
    """Create parquet for Vulhub RCE oracle training"""
    
    def __init__(self, benchmark_root: Path):
        """
        Initialize creator.
        
        Args:
            benchmark_root: Path to benchmark/vulhub directory
        """
        self.benchmark_root = Path(benchmark_root)
        if not self.benchmark_root.exists():
            raise FileNotFoundError(f"Benchmark root not found: {self.benchmark_root}")
    
    def parse_test_list(self, test_list_file: Path) -> List[str]:
        """
        Parse full_test_lists.sh to extract case paths.
        
        Args:
            test_list_file: Path to full_test_lists.sh
            
        Returns:
            List of absolute paths from the script
        """
        if not test_list_file.exists():
            raise FileNotFoundError(f"Test list file not found: {test_list_file}")
        
        print(f"Reading test list: {test_list_file}")
        
        case_paths = []
        with open(test_list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Extract path from: bash ./run_oracle_and_test.sh /path/to/case
                if 'run_oracle_and_test.sh' in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        abs_path = parts[2]  # Third element is the path
                        case_paths.append(abs_path)
        
        print(f"Found {len(case_paths)} cases")
        return case_paths
    
    def absolute_to_relative(self, abs_path: str) -> str:
        """
        Convert absolute path to relative vulhub_path.
        
        Args:
            abs_path: /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077
            
        Returns:
            aj-report/CNVD-2024-15077
        """
        # Find 'vulhub/' in the path and take everything after it
        parts = abs_path.replace('\\', '/').split('/')
        
        # Find the index of 'vulhub' directory
        try:
            vulhub_idx = parts.index('vulhub')
            # Take everything after 'vulhub/'
            relative_parts = parts[vulhub_idx + 1:]
            return '/'.join(relative_parts)
        except ValueError:
            # If 'vulhub' not found, try to extract last 2 segments
            return '/'.join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    
    def verify_case_exists(self, vulhub_path: str) -> bool:
        """
        Verify that case directory exists in benchmark root.
        
        Args:
            vulhub_path: Relative path (e.g., "aj-report/CNVD-2024-15077")
            
        Returns:
            True if case directory exists with required files
        """
        case_dir = self.benchmark_root / vulhub_path
        
        if not case_dir.exists():
            return False
        
        # Check for required oracle files
        oracle_solution = case_dir / "oracle_solution.sh"
        oracle_test = case_dir / "oracle_test.sh"
        docker_compose = case_dir / "docker-compose.yml"
        
        has_compose = docker_compose.exists() or (case_dir / "docker-compose.yaml").exists()
        
        return oracle_solution.exists() and oracle_test.exists() and has_compose
    
    def create_row(self, vulhub_path: str) -> Dict[str, Any]:
        """
        Create a single parquet row for a case.
        
        Args:
            vulhub_path: Relative path (e.g., "aj-report/CNVD-2024-15077")
            
        Returns:
            Dict with parquet columns
        """
        # cve_id is the full path segment
        cve_id = vulhub_path
        
        # Standard metadata for all cases
        metadata = {
            "agent_type": "ctf",
            "reward_type": "vulhub_rce"
        }
        
        return {
            "cve_id": cve_id,
            "vulhub_path": vulhub_path,
            "prompt": STANDARD_PROMPT,
            "max_steps": MAX_STEPS,
            "metadata": json.dumps(metadata, ensure_ascii=False)
        }
    
    def create_parquet(
        self,
        test_list_file: Path,
        output_path: Path,
    ) -> int:
        """
        Create parquet file from test list.
        
        Args:
            test_list_file: Path to full_test_lists.sh
            output_path: Output parquet file path
            
        Returns:
            Number of cases converted
        """
        print("=" * 70)
        print("Vulhub RCE Oracle Parquet Creator")
        print("=" * 70)
        print(f"Benchmark root: {self.benchmark_root}")
        print(f"Input: {test_list_file}")
        print(f"Output: {output_path}")
        print("=" * 70)
        print()
        
        # Parse test list
        case_paths = self.parse_test_list(test_list_file)
        
        # Convert to relative paths and create rows
        rows = []
        skipped = []
        
        for abs_path in case_paths:
            vulhub_path = self.absolute_to_relative(abs_path)
            
            # Verify case exists
            if not self.verify_case_exists(vulhub_path):
                print(f"⚠ Skipping {vulhub_path} (not found or missing oracle files)")
                skipped.append({"vulhub_path": vulhub_path, "reason": "missing files"})
                continue
            
            # Create row
            row = self.create_row(vulhub_path)
            rows.append(row)
            print(f"✓ {vulhub_path}")
        
        # Create DataFrame and save
        if not rows:
            print("\n✗ No valid cases found!")
            return 0
        
        df = pd.DataFrame(rows)
        
        # Save parquet
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        
        # Print summary
        print()
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total cases: {len(case_paths)}")
        print(f"Converted: {len(rows)}")
        print(f"Skipped: {len(skipped)}")
        print()
        
        if skipped:
            print("Skipped cases:")
            for item in skipped:
                print(f"  - {item['vulhub_path']}: {item['reason']}")
            print()
        
        print(f"Output parquet: {output_path}")
        print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
        print(f"Columns: {list(df.columns)}")
        print()
        
        print("Sample rows (first 3):")
        for idx, row in df.head(3).iterrows():
            print(f"\n  [{idx + 1}] {row['cve_id']}")
            print(f"      vulhub_path: {row['vulhub_path']}")
            print(f"      prompt: {row['prompt'][:60]}...")
            print(f"      max_steps: {row['max_steps']}")
            metadata = json.loads(row['metadata'])
            print(f"      metadata: {metadata}")
        
        print()
        print("=" * 70)
        print(f"✓ Created {output_path}")
        print("=" * 70)
        
        return len(rows)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Create Vulhub RCE oracle parquet for training",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create parquet from test list
  python create_vulhub_rce_parquet.py \\
    --input ../vulhub_oracle_and_test/full_test_lists.sh \\
    --output train_vulhub_rce.parquet

  # Specify custom benchmark root
  python create_vulhub_rce_parquet.py \\
    --input ../vulhub_oracle_and_test/full_test_lists.sh \\
    --output train_vulhub_rce.parquet \\
    --benchmark-root ../benchmark/vulhub
"""
    )
    
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to full_test_lists.sh",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output parquet file path",
    )
    parser.add_argument(
        "--benchmark-root",
        type=str,
        default="../benchmark/vulhub",
        help="Path to benchmark/vulhub directory (default: ../benchmark/vulhub)",
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    input_file = Path(args.input).resolve()
    output_file = Path(args.output).resolve()
    benchmark_root = Path(args.benchmark_root).resolve()
    
    # Create parquet
    creator = VulhubRCEParquetCreator(benchmark_root)
    num_converted = creator.create_parquet(input_file, output_file)
    
    return 0 if num_converted > 0 else 1


if __name__ == "__main__":
    exit(main())
