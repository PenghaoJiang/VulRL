"""
Result Folder to SkyRL Parquet Converter

Converts result folders from interactive_poc_generator.py to 7-column SkyRL parquet format.
Each result folder should contain: metadata.json, poc.py, verify.py, README.md, requirements.txt

# command to run
source /data1/jph/VulRL/.venv/bin/activate

python dataset_converter_v2.py \
  --input-list /data1/jph/VulRL/dataset/true_positive_v4.txt \
  --output /data1/jph/VulRL/dataset/train_v4.parquet \
  --vulhub-base /data1/jph/vulhub

the parquet generated should be manually transfered to desired location for usage
e.g. /data1/jph/VulRL/worker_orchestrator/ez_generator/train_v4.parquet

"""

import sys
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add infra to path
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))
from env_types import StandardEnvConfig


# ── SkyRL Tool Definitions ──────────────────────────────────────────────────────
SKYRL_TOOL_DEFINITIONS = [
    {
        "name": "bash",
        "description": (
            "Execute any bash command in the attack environment. "
            "Can run curl, python, nmap, nc, echo, and any command-line tool. "
            "Use for port scanning, scripting, payload generation, file operations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "http_request",
        "description": (
            "Send HTTP/HTTPS requests to the target. "
            "More convenient than bash+curl for web exploitation. "
            "Supports all HTTP methods, custom headers, JSON/XML payloads."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                },
                "url": {
                    "type": "string",
                    "description": "Target URL (or use 'path' with service URL)",
                },
                "path": {
                    "type": "string",
                    "description": "URL path (will be appended to service URL)",
                },
                "headers": {
                    "type": "object",
                    "description": "Custom HTTP headers",
                },
                "data": {
                    "type": "string",
                    "description": "Request body",
                },
                "json": {
                    "type": "object",
                    "description": "JSON payload",
                },
            },
            "required": ["method"],
        },
    },
]


class ResultFolderConverter:
    """Convert result folders from interactive_poc_generator to SkyRL parquet"""

    def __init__(self, vulhub_base_dir: str = "/data1/jph/vulhub"):
        self.vulhub_base_dir = Path(vulhub_base_dir)

    def convert(
        self,
        input_list: Optional[str] = None,
        input_dir: Optional[str] = None,
        output_path: str = "train.parquet",
    ) -> int:
        """
        Convert result folders to 7-column SkyRL parquet

        Args:
            input_list: Path to file containing folder paths (one per line, quoted)
            input_dir: Directory to scan for result folders
            output_path: Output parquet file path

        Returns:
            Number of samples converted
        """
        print("=" * 60)
        print("Result Folder → SkyRL Parquet Converter")
        print("=" * 60)

        # Get folder paths
        folder_paths = []
        if input_list:
            print(f"Reading folder list from: {input_list}")
            with open(input_list, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        # Remove quotes if present
                        path = line.strip('"').strip("'")
                        folder_paths.append(Path(path))
        elif input_dir:
            print(f"Scanning directory: {input_dir}")
            input_path = Path(input_dir)
            folder_paths = [p for p in input_path.iterdir() if p.is_dir()]
        else:
            raise ValueError("Must provide either --input-list or --input-dir")

        print(f"Found {len(folder_paths)} folders to process")
        print("=" * 60)

        # Process each folder
        rows = []
        failed = []
        tools_json = json.dumps(SKYRL_TOOL_DEFINITIONS, ensure_ascii=False)

        for idx, folder in enumerate(folder_paths):
            try:
                print(f"[{idx+1}/{len(folder_paths)}] Processing {folder.name}...")
                skyrl_row = self._convert_folder(folder, tools_json)
                rows.append(skyrl_row)
            except Exception as e:
                print(f"  ERROR: {e}")
                failed.append({"folder": str(folder), "error": str(e)})

        # Save to parquet
        if rows:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(rows)
            df.to_parquet(out, index=False)
            print(f"\n{'='*60}")
            print(f"Success: {len(rows)} samples → {out}")
            print(f"Failed: {len(failed)} folders")
            if failed:
                error_file = out.parent / "conversion_errors.json"
                with open(error_file, 'w') as f:
                    json.dump(failed, f, indent=2)
                print(f"Errors saved to: {error_file}")
            
            # Print parquet info
            print(f"\n{'='*60}")
            print("Parquet Contents:")
            print(f"{'='*60}")
            print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns")
            print(f"Columns: {list(df.columns)}")
            print(f"\nTask IDs:")
            for i, task_id in enumerate(df['task_id'], 1):
                print(f"  {i:2d}. {task_id}")
            print(f"\n{'='*60}")
        else:
            print("\nNo samples converted!")

        return len(rows)

    def _convert_folder(self, folder: Path, tools_json: str) -> Dict[str, str]:
        """
        Convert a single result folder to SkyRL row

        Expected folder structure:
            - metadata.json: {vulhub_path, folder_name}
            - poc.py: PoC script
            - verify.py: Verification script
            - README.md: Vulnerability documentation
            - requirements.txt: Python dependencies
        """
        # Read metadata
        metadata_file = folder / "metadata.json"
        if not metadata_file.exists():
            raise FileNotFoundError(f"metadata.json not found in {folder}")
        
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        vulhub_path = metadata.get("vulhub_path", "")
        if not vulhub_path:
            raise ValueError("vulhub_path not found in metadata.json")

        # Extract task_id (category/CVE-ID)
        task_id = vulhub_path

        # Read PoC script
        poc_file = folder / "poc.py"
        if not poc_file.exists():
            raise FileNotFoundError(f"poc.py not found in {folder}")
        
        poc_script = poc_file.read_text(encoding='utf-8')

        # Read verification script
        verify_file = folder / "verify.py"
        verify_script = verify_file.read_text(encoding='utf-8') if verify_file.exists() else ""

        # Read dependencies
        requirements_file = folder / "requirements.txt"
        dependencies = []
        if requirements_file.exists():
            deps_text = requirements_file.read_text(encoding='utf-8')
            dependencies = [line.strip() for line in deps_text.split('\n') if line.strip()]

        # Read README for vulnerability description
        readme_file = folder / "README.md"
        readme_text = ""
        if readme_file.exists():
            readme_text = readme_file.read_text(encoding='utf-8')
        else:
            readme_cn = folder / "README.zh-cn.md"
            if readme_cn.exists():
                readme_text = readme_cn.read_text(encoding='utf-8')

        # Extract basic info from README
        vuln_desc = self._extract_description(readme_text)
        service_name, service_version = self._extract_service_info(vulhub_path)

        # Extract port from PoC (look for default port in argparse)
        primary_port = self._extract_port_from_poc(poc_script)

        # Build 7-column row
        prompt_dict = self._build_prompt(service_name, primary_port, vuln_desc)
        env_config_dict = self._build_env_config(
            task_id, service_name, primary_port, vuln_desc, vulhub_path
        )
        poc_info_dict = self._build_poc_info(
            poc_script, verify_script, dependencies, vuln_desc, service_name, service_version
        )
        metadata_dict = self._build_metadata(task_id, vulhub_path)

        return {
            "prompt": json.dumps(prompt_dict, ensure_ascii=False),
            "env_class": "security_env.SecurityEnv",
            "env_config": json.dumps(env_config_dict, ensure_ascii=False),
            "poc_info": json.dumps(poc_info_dict, ensure_ascii=False),
            "tools": tools_json,
            "task_id": task_id,
            "metadata": json.dumps(metadata_dict, ensure_ascii=False),
            "vulhub_path": vulhub_path,
            "cve_id": task_id,
        }

    def _build_prompt(self, service_name: str, port: int, description: str) -> List[Dict[str, str]]:
        """Build system + user prompt"""
        system_msg = (
            "# Security Testing Task\n\n"
            "You are a security researcher conducting authorized penetration testing.\n"
            "Find and exploit security vulnerabilities in the target system.\n"
            "Provide visual evidence of successful exploitation.\n\n"
            "## Available Tools\n"
            "- `bash`: Execute any bash command (curl, python, nmap, nc, etc.)\n"
            "- `http_request`: Send HTTP requests to the target\n\n"
            "## Notes\n"
            "- Use tools strategically and observe responses carefully\n"
            "- Your evidence will be evaluated visually\n"
            "- No restrictions on methods - use any approach you think will work"
        )
        user_msg = f"Target: {service_name}:{port}\n\nBegin exploitation."

        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

    def _build_env_config(
        self,
        task_id: str,
        service_name: str,
        port: int,
        description: str,
        vulhub_path: str,
    ) -> Dict[str, Any]:
        """Build StandardEnvConfig compatible dict"""
        protocol = "https" if port in (443, 8443) else "http"

        return {
            "task_id": task_id,
            "task_type": "vulhub",
            "vulhub_path": vulhub_path,
            "cve_id": task_id,
            "max_steps": 30,
            "timeout": 30,
            "target_host": service_name,
            "target_port": port,
            "target_protocol": protocol,
            "evaluation_config": {
                "ground_truth_images": [],
                "success_indicators": [],
                "expected_final_state": description,
            },
            "poc_info": {
                "vulnerability_description": description,
                "service_name": service_name,
            },
            "backend_config": {
                "vulhub_path": vulhub_path,
                "compose_path": str(self.vulhub_base_dir / vulhub_path),
                "target_services": [service_name],
            },
        }

    def _build_poc_info(
        self,
        poc_script: str,
        verify_script: str,
        dependencies: List[str],
        description: str,
        service_name: str,
        service_version: str,
    ) -> Dict[str, Any]:
        """Build poc_info dict"""
        return {
            "poc_script": poc_script,
            "verify_script": verify_script,
            "dependencies": dependencies,
            "vulnerability_description": description,
            "service_name": service_name,
            "service_version": service_version,
            "vulnerability_type": "unknown",
            "exploit_steps": [],
            "success_indicators": [],
        }

    def _build_metadata(self, task_id: str, vulhub_path: str) -> Dict[str, Any]:
        """Build metadata dict"""
        return {
            "task_id": task_id,
            "task_type": "vulhub",
            "vulhub_path": vulhub_path,
            "source": "interactive_poc_generator_v4",
        }

    def _extract_description(self, readme_text: str) -> str:
        """Extract vulnerability description from README"""
        if not readme_text:
            return "No description available"
        
        # Take first few meaningful lines (skip title)
        lines = readme_text.split('\n')
        desc_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                desc_lines.append(line)
                if len(desc_lines) >= 3:
                    break
        
        return ' '.join(desc_lines) if desc_lines else "No description available"

    def _extract_service_info(self, vulhub_path: str) -> tuple[str, str]:
        """Extract service name and version from vulhub_path"""
        # vulhub_path format: "category/CVE-ID"
        parts = vulhub_path.split('/')
        if len(parts) >= 1:
            service_name = parts[0]
            version = parts[1] if len(parts) > 1 else "unknown"
            return service_name, version
        return "target", "unknown"

    def _extract_port_from_poc(self, poc_script: str) -> int:
        """Extract default port from PoC argparse definition"""
        # Look for patterns like: default=80, default="8080", default=int(...)
        import re
        
        # Pattern for --port argument default value
        patterns = [
            r'--port.*?default[=\s]+(\d+)',
            r'port["\'].*?default[=\s]+(\d+)',
            r'PORT\s*=\s*(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, poc_script, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # Default to 80 if not found
        return 80


def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert result folders to SkyRL 7-column parquet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert from list file
  python dataset_converter_v2.py --input-list dataset/true_positives_v4.txt --output data/train_v4.parquet

  # Convert from directory (all subdirectories)
  python dataset_converter_v2.py --input-dir tmp/result_v4 --output data/train_v4.parquet

  # Specify custom vulhub base directory
  python dataset_converter_v2.py --input-list true_positives_v4.txt --output train.parquet --vulhub-base /mnt/e/git_fork_folder/VulRL/benchmark/vulhub
"""
    )

    parser.add_argument(
        "--input-list",
        help="Path to file containing folder paths (one per line, quoted)",
    )
    parser.add_argument(
        "--input-dir",
        help="Directory containing result folders",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output parquet file path",
    )
    parser.add_argument(
        "--vulhub-base",
        default="/data1/jph/vulhub",
        help="Vulhub base directory (default: /data1/jph/vulhub)",
    )

    args = parser.parse_args()

    if not args.input_list and not args.input_dir:
        parser.error("Must provide either --input-list or --input-dir")

    converter = ResultFolderConverter(vulhub_base_dir=args.vulhub_base)
    num_converted = converter.convert(
        input_list=args.input_list,
        input_dir=args.input_dir,
        output_path=args.output,
    )

    return 0 if num_converted > 0 else 1


if __name__ == "__main__":
    exit(main())
