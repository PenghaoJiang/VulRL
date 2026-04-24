"""
Create Vulhub Oracle Parquet for Training

This script generates parquet files from oracle-verified Vulhub cases.
Supports both RCE and Read-based vulnerabilities with configurable difficulty levels.

Input:
    - vulhub_oracle_and_test/full_test_lists.sh: List of verified oracle cases
      - Cases using run_oracle_and_test_4_rce.sh get reward_type="vulhub_rce"
      - Cases using run_oracle_and_test_4_read.sh get reward_type="vulhub_read"
    - benchmark/vulhub/*/oracle_prompt.txt: prompt_hard/medium/easy for each case

Output:
    - train_vulhub_<difficulty>.parquet: Training data with correct reward metadata

Usage:
    # Easy prompts (default)
    python create_vulhub_rce_parquet.py \
        --input vulhub_oracle_and_test/full_test_lists.sh \
        --output dataset/train_vulhub.parquet

    # Medium or hard prompts
    python create_vulhub_rce_parquet.py \
        --input vulhub_oracle_and_test/full_test_lists.sh \
        --output dataset/train_vulhub.parquet \
        --difficulty medium
"""

import argparse
import json
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any


# Default max steps
MAX_STEPS = 30


class VulhubRCEParquetCreator:
    """
    Create parquet for Vulhub oracle training (RCE and Read-based).
    
    Path Handling:
    - Parquet stores case-specific paths: "elasticsearch/CVE-2015-1427"
    - These paths are relative to benchmark/vulhub directory
    - VulhubAdapter expects this format and constructs full paths at runtime
    """
    
    def __init__(self, benchmark_root: Path):
        """
        Initialize creator.
        
        Args:
            benchmark_root: Path to benchmark/vulhub directory
        """
        self.benchmark_root = Path(benchmark_root)
        if not self.benchmark_root.exists():
            raise FileNotFoundError(f"Benchmark root not found: {self.benchmark_root}")
    
    def parse_test_list(self, test_list_file: Path) -> List[tuple[str, str]]:
        """
        Parse full_test_lists.sh to extract case paths and reward types.
        
        Args:
            test_list_file: Path to full_test_lists.sh
            
        Returns:
            List of tuples (absolute_path, reward_type)
            - reward_type is "vulhub_rce" for run_oracle_and_test_4_rce.sh
            - reward_type is "vulhub_read" for run_oracle_and_test_4_read.sh
        """
        if not test_list_file.exists():
            raise FileNotFoundError(f"Test list file not found: {test_list_file}")
        
        print(f"Reading test list: {test_list_file}")
        
        case_info = []
        with open(test_list_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Only process lines starting with "bash"
                if not line.startswith('bash'):
                    continue
                
                # Determine reward type based on script name
                reward_type = None
                if 'run_oracle_and_test_4_rce.sh' in line:
                    reward_type = "vulhub_rce"
                elif 'run_oracle_and_test_4_read.sh' in line:
                    reward_type = "vulhub_read"
                else:
                    # Skip unknown scripts
                    continue
                
                # Extract path: bash ./run_oracle_and_test_4_*.sh /path/to/case
                parts = line.split()
                if len(parts) >= 3:
                    abs_path = parts[2]  # Third element is the path
                    case_info.append((abs_path, reward_type))
        
        print(f"Found {len(case_info)} cases ({sum(1 for _, r in case_info if r == 'vulhub_rce')} RCE, {sum(1 for _, r in case_info if r == 'vulhub_read')} Read)")
        return case_info
    
    def absolute_to_relative(self, abs_path: str) -> str:
        """
        Convert absolute path to vulhub_path (case-specific path).
        
        Extracts just the case path after 'vulhub/' directory, which is what
        VulhubAdapter expects (e.g., "elasticsearch/CVE-2015-1427").
        
        Args:
            abs_path: /data1/jph/VulRL/benchmark/vulhub/elasticsearch/CVE-2015-1427
            
        Returns:
            elasticsearch/CVE-2015-1427
        """
        # Normalize path separators
        normalized_path = abs_path.replace('\\', '/')
        parts = normalized_path.split('/')
        
        # Find the index of 'vulhub' directory
        try:
            vulhub_idx = parts.index('vulhub')
            # Take everything after 'vulhub/'
            relative_parts = parts[vulhub_idx + 1:]
            return '/'.join(relative_parts)
        except ValueError:
            # Fallback: if 'vulhub' not found, take last 2 segments (category/case)
            return '/'.join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    
    def verify_case_exists(self, vulhub_path: str) -> bool:
        """
        Verify that case directory exists in benchmark root.
        
        Args:
            vulhub_path: Case-specific path (e.g., "elasticsearch/CVE-2015-1427")
            
        Returns:
            True if case directory exists with required files
        """
        case_dir = self.benchmark_root / vulhub_path
        
        if not case_dir.exists():
            return False
        
        # Check for required oracle files
        oracle_solution = case_dir / "oracle_solution.sh"
        oracle_test = case_dir / "oracle_test.sh"
        oracle_prompt = case_dir / "oracle_prompt.txt"
        docker_compose = case_dir / "docker-compose.yml"
        
        has_compose = docker_compose.exists() or (case_dir / "docker-compose.yaml").exists()
        
        return oracle_solution.exists() and oracle_test.exists() and oracle_prompt.exists() and has_compose
    
    def read_prompt(self, vulhub_path: str, difficulty: str = "easy") -> str:
        """
        Read prompt from oracle_prompt.txt based on difficulty.
        
        Args:
            vulhub_path: Case-specific path (e.g., "elasticsearch/CVE-2015-1427")
            difficulty: Prompt difficulty level ("easy", "medium", or "hard")
            
        Returns:
            The prompt text, or default prompt if not found
        """
        case_dir = self.benchmark_root / vulhub_path
        oracle_prompt_file = case_dir / "oracle_prompt.txt"
        
        if not oracle_prompt_file.exists():
            print(f"  ⚠ Warning: oracle_prompt.txt not found for {vulhub_path}")
            return "exploit the vulnerability of given target and CREATE file /tmp/exploit.txt in target server to perform a SUCCESS exploitation"
        
        try:
            with open(oracle_prompt_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Parse the file to find the specified difficulty prompt
            prompt_key = f"prompt_{difficulty}:"
            for line in lines:
                line = line.strip()
                if line.startswith(prompt_key):
                    # Extract everything after "prompt_{difficulty}: "
                    prompt = line[len(prompt_key):].strip()
                    return prompt
            
            # If specified difficulty not found, warn and use default
            print(f"  ⚠ Warning: {prompt_key} not found in oracle_prompt.txt for {vulhub_path}")
            return "exploit the vulnerability of given target and CREATE file /tmp/exploit.txt in target server to perform a SUCCESS exploitation"
            
        except Exception as e:
            print(f"  ⚠ Error reading oracle_prompt.txt for {vulhub_path}: {e}")
            return "exploit the vulnerability of given target and CREATE file /tmp/exploit.txt in target server to perform a SUCCESS exploitation"
    
    def create_row(self, vulhub_path: str, reward_type: str, difficulty: str = "easy") -> Dict[str, Any]:
        """
        Create a single parquet row for a case.
        
        Args:
            vulhub_path: Case-specific path (e.g., "elasticsearch/CVE-2015-1427")
            reward_type: Reward type ("vulhub_rce" or "vulhub_read")
            difficulty: Prompt difficulty level ("easy", "medium", or "hard")
            
        Returns:
            Dict with parquet columns
        """
        # cve_id is the case-specific path
        cve_id = vulhub_path
        
        # Read prompt from oracle_prompt.txt based on difficulty
        prompt = self.read_prompt(vulhub_path, difficulty)
        
        # Metadata with correct reward type
        metadata = {
            "agent_type": "ctf",
            "reward_type": reward_type
        }
        
        return {
            "cve_id": cve_id,
            "vulhub_path": vulhub_path,
            "prompt": prompt,
            "max_steps": MAX_STEPS,
            "metadata": json.dumps(metadata, ensure_ascii=False)
        }
    
    def create_parquet(
        self,
        test_list_file: Path,
        output_path: Path,
        difficulty: str = "easy",
    ) -> int:
        """
        Create parquet file from test list.
        
        Args:
            test_list_file: Path to full_test_lists.sh
            output_path: Output parquet file path
            difficulty: Prompt difficulty level ("easy", "medium", or "hard")
            
        Returns:
            Number of cases converted
        """
        print("=" * 70)
        print("Vulhub Oracle Parquet Creator (RCE + Read)")
        print("=" * 70)
        print(f"Benchmark root: {self.benchmark_root}")
        print(f"Input: {test_list_file}")
        print(f"Output: {output_path}")
        print(f"Difficulty: {difficulty}")
        print("=" * 70)
        print()
        
        # Parse test list
        case_info = self.parse_test_list(test_list_file)
        
        # Convert to relative paths and create rows
        rows = []
        skipped = []
        
        for abs_path, reward_type in case_info:
            vulhub_path = self.absolute_to_relative(abs_path)
            
            # Verify case exists
            if not self.verify_case_exists(vulhub_path):
                print(f"⚠ Skipping {vulhub_path} (not found or missing oracle files)")
                skipped.append({"vulhub_path": vulhub_path, "reason": "missing files"})
                continue
            
            # Create row with correct reward type
            row = self.create_row(vulhub_path, reward_type, difficulty)
            rows.append(row)
            print(f"✓ {vulhub_path} ({reward_type})")
        
        # Create DataFrame and save
        if not rows:
            print("\n✗ No valid cases found!")
            return 0
        
        df = pd.DataFrame(rows)
        
        # Save parquet
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        
        # Count by reward type
        rce_count = sum(1 for row in rows if json.loads(row['metadata'])['reward_type'] == 'vulhub_rce')
        read_count = sum(1 for row in rows if json.loads(row['metadata'])['reward_type'] == 'vulhub_read')
        
        # Print summary
        print()
        print("=" * 70)
        print("Summary")
        print("=" * 70)
        print(f"Total cases: {len(case_info)}")
        print(f"Converted: {len(rows)} ({rce_count} RCE, {read_count} Read)")
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
            metadata = json.loads(row['metadata'])
            print(f"\n  [{idx + 1}] {row['cve_id']}")
            print(f"      vulhub_path: {row['vulhub_path']}")
            print(f"      reward_type: {metadata['reward_type']}")
            print(f"      prompt: {row['prompt'][:80]}...")
            print(f"      max_steps: {row['max_steps']}")
        
        print()
        print("=" * 70)
        print(f"✓ Created {output_path}")
        print("=" * 70)
        print()
        
        # Pretty-print all rows
        print("=" * 70)
        print("All Parquet Rows")
        print("=" * 70)
        print()
        
        for idx, row in df.iterrows():
            metadata = json.loads(row['metadata'])
            print(f"[{idx + 1}/{len(df)}] {row['cve_id']}")
            print(f"  Path:        {row['vulhub_path']}")
            print(f"  Reward Type: {metadata['reward_type']}")
            print(f"  Max Steps:   {row['max_steps']}")
            print(f"  Prompt:      {row['prompt'][:120]}{'...' if len(row['prompt']) > 120 else ''}")
            print()
        
        print("=" * 70)
        print(f"Total: {len(df)} cases")
        print("=" * 70)
        
        return len(rows)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Create Vulhub oracle parquet for training (RCE + Read-based)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create parquet with easy prompts (default)
  python create_vulhub_rce_parquet.py \\
    --input ../vulhub_oracle_and_test/full_test_lists.sh \\
    --output train_vulhub_rce.parquet
  # Output: train_vulhub_rce_easy.parquet

  # Create parquet with medium prompts
  python create_vulhub_rce_parquet.py \\
    --input ../vulhub_oracle_and_test/full_test_lists.sh \\
    --output train_vulhub_rce.parquet \\
    --difficulty medium
  # Output: train_vulhub_rce_medium.parquet

  # Create parquet with hard prompts
  python create_vulhub_rce_parquet.py \\
    --input ../vulhub_oracle_and_test/full_test_lists.sh \\
    --output train_vulhub_rce.parquet \\
    --difficulty hard \\
    --benchmark-root ../benchmark/vulhub
  # Output: train_vulhub_rce_hard.parquet
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
        help="Output parquet file path (difficulty will be auto-appended to filename)",
    )
    parser.add_argument(
        "--benchmark-root",
        type=str,
        default="../benchmark/vulhub",
        help="Path to benchmark/vulhub directory (default: ../benchmark/vulhub)",
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        choices=["easy", "medium", "hard"],
        default="easy",
        help="Prompt difficulty level to use (default: easy)",
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    input_file = Path(args.input).resolve()
    output_file = Path(args.output).resolve()
    benchmark_root = Path(args.benchmark_root).resolve()
    
    # Auto-append difficulty to output filename
    # e.g., train_vulhub_rce.parquet -> train_vulhub_rce_easy.parquet
    output_stem = output_file.stem  # filename without extension
    output_suffix = output_file.suffix  # .parquet
    output_parent = output_file.parent
    
    # Only append difficulty if not already in filename
    if not output_stem.endswith(f"_{args.difficulty}"):
        output_file = output_parent / f"{output_stem}_{args.difficulty}{output_suffix}"
    
    # Create parquet
    creator = VulhubRCEParquetCreator(benchmark_root)
    num_converted = creator.create_parquet(input_file, output_file, args.difficulty)
    
    return 0 if num_converted > 0 else 1


if __name__ == "__main__":
    exit(main())
