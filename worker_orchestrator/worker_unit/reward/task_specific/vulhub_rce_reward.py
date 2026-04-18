"""
Vulhub RCE-specific reward using oracle_test.sh verification.

Executes oracle_test.sh on the host after trajectory completion to verify
if the exploit succeeded. Returns 1.0 if test passes (exit code 0), 0.0 otherwise.
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


class VulhubRCEReward:
    """
    Oracle test-based reward for Vulhub RCE challenges.
    
    This reward runs the oracle_test.sh script from the case directory
    to verify if the exploit succeeded. The test runs on the host and
    checks for observable artifacts in the target container.
    
    Reward:
        - 1.0 if oracle_test.sh exits with code 0 (exploit succeeded)
        - 0.0 otherwise (exploit failed or test not available)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize VulhubRCEReward.
        
        Args:
            config: Environment configuration. Expected keys:
                - adapter: VulhubAdapter instance (for container info)
                - vulhub_base_path: Base path to vulhub benchmark
                - vulhub_path: Relative path to the specific case
                - case_dir: Absolute path to case directory (optional, computed if not provided)
        """
        self.config = config or {}
        self.adapter = self.config.get("adapter")
        
        # Resolve case directory
        vulhub_base_path = self.config.get("vulhub_base_path", "")
        vulhub_path = self.config.get("vulhub_path", "")
        case_dir = self.config.get("case_dir")
        
        if case_dir:
            self.case_dir = Path(case_dir)
        elif vulhub_base_path and vulhub_path:
            self.case_dir = Path(vulhub_base_path) / vulhub_path
        else:
            self.case_dir = None
        
        print(f"[VulhubRCEReward] Initialized with case_dir: {self.case_dir}")

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward by running oracle_test.sh.
        
        Args:
            trajectory: List of step dicts (not used, reward based on test result)
            task_id: Vulhub task ID (e.g., "aj-report/CNVD-2024-15077")
        
        Returns:
            1.0 if oracle_test.sh passes (exit code 0), 0.0 otherwise
        """
        if not self.adapter:
            print(f"[VulhubRCEReward] No adapter provided, reward=0.0")
            return 0.0
        
        if not self.case_dir or not self.case_dir.exists():
            print(f"[VulhubRCEReward] Case directory not found: {self.case_dir}, reward=0.0")
            return 0.0
        
        oracle_test_script = self.case_dir / "oracle_test.sh"
        if not oracle_test_script.exists():
            print(f"[VulhubRCEReward] oracle_test.sh not found in {self.case_dir}, reward=0.0")
            return 0.0
        
        print(f"[VulhubRCEReward] Running oracle_test.sh for task={task_id}")
        
        # Build environment variables for oracle_test.sh (runs on host)
        env_vars = {
            "TARGET_CONTAINER": self.adapter.target_container_name or "",
            "TARGET_CONTAINER_ID": self.adapter.target_container_obj.id if self.adapter.target_container_obj else "",
            "COMPOSE_PROJECT_NAME": self.adapter.project_name or "",
            "ATTACKER_CONTAINER": self.adapter.attacker_container_name or "",
            "ORACLE_CASE_DIR": str(self.case_dir.resolve()),
        }
        
        print(f"[VulhubRCEReward] Environment: TARGET_CONTAINER={env_vars['TARGET_CONTAINER']}, "
              f"COMPOSE_PROJECT_NAME={env_vars['COMPOSE_PROJECT_NAME']}")
        
        try:
            # Run oracle_test.sh on the host
            result = subprocess.run(
                ["bash", str(oracle_test_script)],
                cwd=str(self.case_dir),
                env={**subprocess.os.environ, **env_vars},
                capture_output=True,
                text=True,
                timeout=60
            )
            
            exit_code = result.returncode
            
            # Log output for debugging
            if result.stdout:
                print(f"[VulhubRCEReward] oracle_test.sh stdout:\n{result.stdout}")
            if result.stderr:
                print(f"[VulhubRCEReward] oracle_test.sh stderr:\n{result.stderr}")
            
            # Reward based on exit code
            if exit_code == 0:
                print(f"[VulhubRCEReward] task={task_id} reward=1.0 (oracle_test PASSED)")
                return 1.0
            else:
                print(f"[VulhubRCEReward] task={task_id} reward=0.0 (oracle_test FAILED, exit_code={exit_code})")
                return 0.0
        
        except subprocess.TimeoutExpired:
            print(f"[VulhubRCEReward] oracle_test.sh timed out, reward=0.0")
            return 0.0
        except Exception as e:
            print(f"[VulhubRCEReward] Error running oracle_test.sh: {e}, reward=0.0")
            return 0.0
