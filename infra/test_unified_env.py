"""
统一环境测试脚本
用于验证 SecurityEnv 和适配器的基本功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from infra.env_types import StandardAction, ActionType, StandardEnvConfig
from infra.security_env import SecurityEnv


def test_vulhub_adapter():
    """测试 VulhubAdapter"""
    print("\n" + "=" * 70)
    print("测试 VulhubAdapter")
    print("=" * 70)

    # 配置（需要实际的 vulhub 路径）
    config = StandardEnvConfig(
        task_id="TEST-VULHUB-001",
        task_type="vulhub",
        max_steps=5,
        timeout=30,
        target_host="target",
        target_port=80,
        target_protocol="http",
        backend_config={
            "vulhub_path": "apache/CVE-2024-1234"  # 需要替换为实际路径
        }
    )

    try:
        # 创建环境
        print("\n1. 创建环境...")
        env = SecurityEnv(config=config)
        print("✓ 环境创建成功")

        # Reset
        print("\n2. Reset 环境...")
        observation, info = env.reset()
        print(f"✓ Reset 成功")
        print(f"  Observation type: {type(observation).__name__}")
        print(f"  Info type: {type(info).__name__}")
        print(f"  Task ID: {info.task_id}")
        print(f"  Step: {info.step}/{info.max_steps}")

        # Step - bash
        print("\n3. 测试 bash 命令...")
        action = StandardAction(
            action_type=ActionType.BASH,
            arguments={"command": "echo 'Hello from bash'"}
        )
        obs, reward, term, trunc, info = env.step(action)
        print(f"✓ Bash 命令执行成功")
        print(f"  Output preview: {obs.to_text()[:100]}...")
        print(f"  Reward: {reward}")
        print(f"  Done: {term or trunc}")

        # Step - http_request
        print("\n4. 测试 HTTP 请求...")
        action = StandardAction(
            action_type=ActionType.HTTP_REQUEST,
            arguments={"method": "GET", "path": "/"}
        )
        obs, reward, term, trunc, info = env.step(action)
        print(f"✓ HTTP 请求执行成功")
        print(f"  Output preview: {obs.to_text()[:100]}...")

        # Close
        print("\n5. 关闭环境...")
        env.close()
        print("✓ 环境关闭成功")

        print("\n" + "=" * 70)
        print("VulhubAdapter 测试通过！")
        print("=" * 70)
        return True

    except FileNotFoundError as e:
        print(f"\n✗ 测试跳过: {e}")
        print("  提示：需要设置实际的 vulhub_path")
        return False
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ctf_adapter():
    """测试 CTFAdapter"""
    print("\n" + "=" * 70)
    print("测试 CTFAdapter")
    print("=" * 70)

    # 配置（需要实际的 compose 路径）
    config = StandardEnvConfig(
        task_id="TEST-CTF-001",
        task_type="ctf",
        max_steps=5,
        timeout=30,
        target_host="target",
        target_port=9090,
        target_protocol="http",
        backend_config={
            "compose_path": Path.home() / "benchmark/cve-bench/src/critical/challenges/CVE-2024-2624/compose.yml",
            "eval_config_path": Path.home() / "benchmark/cve-bench/src/critical/challenges/CVE-2024-2624/eval.yml"
        }
    )

    # 检查文件是否存在
    compose_path = Path(config.backend_config["compose_path"]).expanduser()
    if not compose_path.exists():
        print(f"\n✗ 测试跳过: Compose 文件不存在")
        print(f"  路径: {compose_path}")
        print("  提示：需要先安装 CVE-bench")
        return False

    try:
        # 创建环境
        print("\n1. 创建环境...")
        env = SecurityEnv(config=config)
        print("✓ 环境创建成功")

        # Reset
        print("\n2. Reset 环境...")
        observation, info = env.reset()
        print(f"✓ Reset 成功")
        print(f"  Task ID: {info.task_id}")
        print(f"  Task Type: {info.task_type}")

        # Step
        print("\n3. 测试命令执行...")
        action = StandardAction(
            action_type=ActionType.BASH,
            arguments={"command": "curl -s http://target:9090/"}
        )
        obs, reward, term, trunc, info = env.step(action)
        print(f"✓ 命令执行成功")
        print(f"  Output length: {len(obs.to_text())}")

        # Close
        print("\n4. 关闭环境...")
        env.close()
        print("✓ 环境关闭成功")

        print("\n" + "=" * 70)
        print("CTFAdapter 测试通过！")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_action_parsing():
    """测试动作解析"""
    print("\n" + "=" * 70)
    print("测试动作解析")
    print("=" * 70)

    # 测试 1: 从字典解析
    print("\n1. 测试从字典解析...")
    action_dict = {
        "tool": "bash",
        "arguments": {"command": "ls -la"}
    }
    action = StandardAction.from_dict(action_dict)
    print(f"✓ 解析成功: {action.action_type.value}")

    # 测试 2: 不同的字段名
    print("\n2. 测试不同字段名...")
    action_dict = {
        "name": "http_request",
        "args": {"method": "GET", "url": "http://example.com"}
    }
    action = StandardAction.from_dict(action_dict)
    print(f"✓ 解析成功: {action.action_type.value}")

    # 测试 3: JSON 字符串
    print("\n3. 测试 JSON 字符串解析...")
    import json
    json_str = json.dumps({"tool": "bash", "arguments": {"command": "pwd"}})
    action = StandardAction.from_json(json_str)
    print(f"✓ 解析成功: {action.action_type.value}")

    print("\n" + "=" * 70)
    print("动作解析测试通过！")
    print("=" * 70)
    return True


def test_adapter_registration():
    """测试适配器注册"""
    print("\n" + "=" * 70)
    print("测试适配器注册")
    print("=" * 70)

    # 列出已注册的适配器
    print("\n1. 列出已注册的适配器...")
    adapters = SecurityEnv.list_adapters()
    print(f"✓ 已注册的适配器: {adapters}")

    # 验证必需的适配器
    print("\n2. 验证必需的适配器...")
    required = ["vulhub", "ctf"]
    for adapter_type in required:
        if adapter_type in adapters:
            print(f"✓ {adapter_type} 已注册")
        else:
            print(f"✗ {adapter_type} 未注册")
            return False

    print("\n" + "=" * 70)
    print("适配器注册测试通过！")
    print("=" * 70)
    return True


def test_config_parsing():
    """测试配置解析"""
    print("\n" + "=" * 70)
    print("测试配置解析")
    print("=" * 70)

    # 测试 1: 从字典创建
    print("\n1. 测试从字典创建配置...")
    config_dict = {
        "task_id": "TEST-001",
        "task_type": "vulhub",
        "max_steps": 10,
        "backend_config": {"vulhub_path": "test/path"}
    }
    config = StandardEnvConfig.from_dict(config_dict)
    print(f"✓ 配置创建成功: {config.task_id}")

    # 测试 2: 转换为字典
    print("\n2. 测试转换为字典...")
    config_dict_out = config.to_dict()
    print(f"✓ 转换成功, keys: {list(config_dict_out.keys())}")

    # 测试 3: JSON 序列化
    print("\n3. 测试 JSON 序列化...")
    json_str = config.to_json()
    print(f"✓ JSON 序列化成功, length: {len(json_str)}")

    # 测试 4: 从 JSON 恢复
    print("\n4. 测试从 JSON 恢复...")
    config2 = StandardEnvConfig.from_json(json_str)
    print(f"✓ 恢复成功: {config2.task_id}")

    print("\n" + "=" * 70)
    print("配置解析测试通过！")
    print("=" * 70)
    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("VulRL 统一环境测试套件")
    print("=" * 70)

    results = {}

    # 基础测试（不需要 Docker）
    print("\n\n### 基础功能测试 ###\n")
    results["action_parsing"] = test_action_parsing()
    results["adapter_registration"] = test_adapter_registration()
    results["config_parsing"] = test_config_parsing()

    # Docker 测试（可能跳过）
    print("\n\n### Docker 环境测试 ###\n")
    results["vulhub_adapter"] = test_vulhub_adapter()
    results["ctf_adapter"] = test_ctf_adapter()

    # 总结
    print("\n\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL/SKIP"
        print(f"{status}: {test_name}")

    print(f"\n总计: {passed}/{total} 测试通过")
    print("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
