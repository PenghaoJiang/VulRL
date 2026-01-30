"""
数据集转换工具
将 Vulhub parquet 和 CTF 数据转换为统一的配置格式
"""

import sys
import json
import yaml
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List

# 添加 infra 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "infra"))
from env_types import StandardEnvConfig


class VulhubToUnifiedConverter:
    """将 Vulhub train.parquet 转换为统一配置格式"""

    def convert(
        self,
        parquet_path: str,
        output_dir: str,
        output_format: str = "json"
    ) -> int:
        """
        转换 Vulhub 数据集

        Args:
            parquet_path: train.parquet 路径
            output_dir: 输出目录
            output_format: 输出格式 (json/parquet)

        Returns:
            转换的样本数量
        """
        print("=" * 60)
        print("Vulhub Dataset Converter")
        print("=" * 60)
        print(f"Input: {parquet_path}")
        print(f"Output: {output_dir}")
        print(f"Format: {output_format}")
        print("=" * 60)

        # 读取 parquet
        df = pd.read_parquet(parquet_path)
        print(f"Found {len(df)} samples")

        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 转换每一行
        configs = []
        for idx, row in df.iterrows():
            config = self._convert_row(row)
            configs.append(config)

            # 保存为单独的 JSON 文件
            if output_format == "json":
                output_file = output_path / f"{row['cve_id']}.json"
                with open(output_file, 'w') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                print(f"  [{idx+1}/{len(df)}] {row['cve_id']} -> {output_file.name}")

        # 如果输出格式是 parquet，保存为单个文件
        if output_format == "parquet":
            # 添加 unified_config 列
            df["unified_config"] = [json.dumps(c, ensure_ascii=False) for c in configs]
            output_file = output_path / "train_unified.parquet"
            df.to_parquet(output_file, index=False)
            print(f"\nSaved to: {output_file}")

        print(f"\nTotal converted: {len(configs)} samples")
        return len(configs)

    def _convert_row(self, row: pd.Series) -> Dict:
        """转换单行数据"""
        # 解析 JSON 字段
        try:
            exposed_ports = json.loads(row.get("exposed_ports", "[]"))
        except:
            exposed_ports = []

        try:
            success_indicators = json.loads(row.get("success_indicators", "[]"))
        except:
            success_indicators = []

        try:
            exploitation_steps = json.loads(row.get("exploitation_steps", "[]"))
        except:
            exploitation_steps = []

        # 构建统一配置
        config = {
            "task_id": row["cve_id"],
            "task_type": "vulhub",
            "max_steps": 30,
            "timeout": 30,
            "target_host": row.get("primary_service", "target"),
            "target_port": int(row.get("primary_port", 80)),
            "target_protocol": "http",
            "evaluation_config": {
                "ground_truth_images": [],  # 需要手动添加
                "success_indicators": success_indicators,
                "expected_final_state": row.get("vulnerability_description", "")
            },
            "poc_info": {
                "exploit_steps": exploitation_steps,
                "success_indicators": success_indicators,
                "vulnerability_type": row.get("vulnerability_type", "unknown"),
                "service_name": row.get("service_name", ""),
                "service_version": row.get("service_version", ""),
                "vulnerability_description": row.get("vulnerability_description", ""),
                "poc_script": row.get("poc_script", "")
            },
            "backend_config": {
                "vulhub_path": row["vulhub_path"]
            }
        }

        return config


class CTFToUnifiedConverter:
    """将 CTF 数据转换为统一配置格式"""

    def convert_cvebench(
        self,
        cvebench_dir: str,
        output_dir: str,
        variant: str = "zero_day"
    ) -> int:
        """
        转换 CVE-bench 数据

        Args:
            cvebench_dir: CVE-bench 目录路径
            output_dir: 输出目录
            variant: 变体 (zero_day/one_day)

        Returns:
            转换的样本数量
        """
        print("=" * 60)
        print("CVE-bench Dataset Converter")
        print("=" * 60)
        print(f"Input: {cvebench_dir}")
        print(f"Output: {output_dir}")
        print(f"Variant: {variant}")
        print("=" * 60)

        cvebench_path = Path(cvebench_dir).expanduser()

        # 查找所有 challenge 目录
        challenge_dirs = []
        for category_dir in (cvebench_path / "src").iterdir():
            if category_dir.is_dir():
                challenges_dir = category_dir / "challenges"
                if challenges_dir.exists():
                    for challenge_dir in challenges_dir.iterdir():
                        if challenge_dir.is_dir():
                            eval_file = challenge_dir / "eval.yml"
                            if eval_file.exists():
                                challenge_dirs.append(challenge_dir)

        print(f"Found {len(challenge_dirs)} challenges")

        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 转换每个 challenge
        configs = []
        for idx, challenge_dir in enumerate(challenge_dirs):
            try:
                config = self._convert_challenge(challenge_dir, variant)
                configs.append(config)

                # 保存为 JSON
                output_file = output_path / f"{config['task_id']}.json"
                with open(output_file, 'w') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)

                print(f"  [{idx+1}/{len(challenge_dirs)}] {config['task_id']} -> {output_file.name}")
            except Exception as e:
                print(f"  [{idx+1}/{len(challenge_dirs)}] {challenge_dir.name} FAILED: {e}")

        print(f"\nTotal converted: {len(configs)} samples")
        return len(configs)

    def _convert_challenge(self, challenge_dir: Path, variant: str) -> Dict:
        """转换单个 challenge"""
        # 读取 eval.yml
        eval_file = challenge_dir / "eval.yml"
        with open(eval_file) as f:
            eval_config = yaml.safe_load(f)

        task_name = eval_config.get("name", challenge_dir.name)
        metadata = eval_config.get("metadata", {})
        variants = eval_config.get("variants", {})
        variant_config = variants.get(variant, variants.get("zero_day", {}))

        # 解析 application_url
        app_url = metadata.get("application_url", "target:8080")
        if ":" in app_url:
            host, port = app_url.split(":")
            port = int(port)
        else:
            host = app_url
            port = 8080

        # 提取成功标志
        success_indicators = []
        if "secret_file_path" in metadata:
            success_indicators.append(f"Access file: {metadata['secret_file_path']}")
        if "unauthorized_create_file_name" in metadata:
            success_indicators.append(f"Create file: {metadata['unauthorized_create_file_name']}")
        if "secret_table_name" in metadata:
            success_indicators.append(f"Access table: {metadata['secret_table_name']}")

        # 构建统一配置
        config = {
            "task_id": task_name,
            "task_type": "ctf",
            "max_steps": 30,
            "timeout": 120,
            "target_host": host,
            "target_port": port,
            "target_protocol": "http",
            "evaluation_config": {
                "ground_truth_images": [],
                "success_indicators": success_indicators,
                "expected_final_state": variant_config.get("prompt", "")[:200]
            },
            "poc_info": {
                "exploit_steps": [],
                "success_indicators": success_indicators,
                "prompt": variant_config.get("prompt", ""),
                "metadata": metadata
            },
            "backend_config": {
                "compose_path": str(challenge_dir / "compose.yml"),
                "eval_config_path": str(eval_file)
            }
        }

        return config

    def convert_custom_ctf(
        self,
        ctf_json_path: str,
        output_dir: str
    ) -> int:
        """
        转换自定义 CTF JSON 格式

        Args:
            ctf_json_path: CTF JSON 文件路径
            output_dir: 输出目录

        Returns:
            转换的样本数量
        """
        print("=" * 60)
        print("Custom CTF Dataset Converter")
        print("=" * 60)
        print(f"Input: {ctf_json_path}")
        print(f"Output: {output_dir}")
        print("=" * 60)

        # 读取 JSON
        with open(ctf_json_path) as f:
            ctf_data = json.load(f)

        # 创建输出目录
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 转换每个 challenge
        configs = []
        for idx, challenge in enumerate(ctf_data):
            config = self._convert_custom_challenge(challenge)
            configs.append(config)

            # 保存为 JSON
            output_file = output_path / f"{config['task_id']}.json"
            with open(output_file, 'w') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            print(f"  [{idx+1}/{len(ctf_data)}] {config['task_id']} -> {output_file.name}")

        print(f"\nTotal converted: {len(configs)} samples")
        return len(configs)

    def _convert_custom_challenge(self, challenge: Dict) -> Dict:
        """转换自定义 challenge 格式"""
        config = {
            "task_id": challenge.get("id", "unknown"),
            "task_type": "ctf",
            "max_steps": challenge.get("max_steps", 20),
            "timeout": challenge.get("timeout", 30),
            "target_host": challenge.get("host", "localhost"),
            "target_port": challenge.get("port", 8080),
            "target_protocol": challenge.get("protocol", "http"),
            "evaluation_config": {
                "success_indicators": challenge.get("success_indicators", ["flag{"]),
                "expected_final_state": challenge.get("description", "")
            },
            "poc_info": {
                "description": challenge.get("description", ""),
                "category": challenge.get("category", "misc"),
                "difficulty": challenge.get("difficulty", "medium")
            },
            "backend_config": {}
        }

        # 添加启动方式
        if "dockerfile_path" in challenge:
            config["backend_config"]["dockerfile_path"] = challenge["dockerfile_path"]
        elif "image_name" in challenge:
            config["backend_config"]["image_name"] = challenge["image_name"]
        elif "compose_path" in challenge:
            config["backend_config"]["compose_path"] = challenge["compose_path"]

        return config


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert datasets to unified format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert Vulhub dataset
  python dataset_converter.py vulhub --input ~/data/cve_vulhub/train.parquet --output ~/unified_tasks/vulhub

  # Convert CVE-bench
  python dataset_converter.py cvebench --input ~/benchmark/cve-bench --output ~/unified_tasks/ctf

  # Convert custom CTF JSON
  python dataset_converter.py custom-ctf --input ~/ctf_data.json --output ~/unified_tasks/ctf
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Conversion type")

    # Vulhub 转换
    vulhub_parser = subparsers.add_parser("vulhub", help="Convert Vulhub dataset")
    vulhub_parser.add_argument("--input", required=True, help="Path to train.parquet")
    vulhub_parser.add_argument("--output", required=True, help="Output directory")
    vulhub_parser.add_argument("--format", default="json", choices=["json", "parquet"], help="Output format")

    # CVE-bench 转换
    cvebench_parser = subparsers.add_parser("cvebench", help="Convert CVE-bench")
    cvebench_parser.add_argument("--input", required=True, help="Path to cve-bench directory")
    cvebench_parser.add_argument("--output", required=True, help="Output directory")
    cvebench_parser.add_argument("--variant", default="zero_day", choices=["zero_day", "one_day"], help="Variant to convert")

    # Custom CTF 转换
    custom_parser = subparsers.add_parser("custom-ctf", help="Convert custom CTF JSON")
    custom_parser.add_argument("--input", required=True, help="Path to CTF JSON file")
    custom_parser.add_argument("--output", required=True, help="Output directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # 执行转换
    if args.command == "vulhub":
        converter = VulhubToUnifiedConverter()
        converter.convert(args.input, args.output, args.format)
    elif args.command == "cvebench":
        converter = CTFToUnifiedConverter()
        converter.convert_cvebench(args.input, args.output, args.variant)
    elif args.command == "custom-ctf":
        converter = CTFToUnifiedConverter()
        converter.convert_custom_ctf(args.input, args.output)

    return 0


if __name__ == "__main__":
    exit(main())
