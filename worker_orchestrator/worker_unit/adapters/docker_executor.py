"""
Docker command execution primitives.
Extracted from VulhubAdapter to be reusable by multiple agents.
"""

import subprocess
import json
from typing import Dict, Any, Optional
import docker


class DockerExecutor:
    """
    Handles command execution inside Docker containers.
    
    Supports both Docker SDK (container object) and subprocess (container name).
    This allows flexibility for different adapter implementations.
    """
    
    def __init__(self, container_obj: Optional[docker.models.containers.Container] = None,
                 container_name: Optional[str] = None,
                 timeout: int = 30):
        """
        Initialize executor.
        
        Args:
            container_obj: Docker SDK container object (preferred)
            container_name: Container name (fallback for subprocess)
            timeout: Default timeout for commands
        """
        self.container_obj = container_obj
        self.container_name = container_name or (container_obj.name if container_obj else None)
        self.timeout = timeout
        
        if not self.container_obj and not self.container_name:
            raise ValueError("Either container_obj or container_name must be provided")
    
    def execute_bash(self, command: str, timeout: Optional[int] = None) -> str:
        """
        Execute bash command in container.
        
        Args:
            command: Bash command to execute
            timeout: Command timeout (uses default if None)
            
        Returns:
            Formatted output string with exit code, stdout, stderr
        """
        if not command:
            return "Error: No command provided"
        
        # Limit command length
        if len(command) > 5000:
            return "Error: Command too long (max 5000 characters)"
        
        timeout = timeout or self.timeout
        
        try:
            if self.container_obj:
                # Use Docker SDK (preferred)
                exec_result = self.container_obj.exec_run(
                    ["bash", "-c", command],
                    demux=True
                )
                
                stdout = exec_result.output[0].decode() if exec_result.output[0] else ""
                stderr = exec_result.output[1].decode() if exec_result.output[1] else ""
                exit_code = exec_result.exit_code
                
            else:
                # Fallback to subprocess
                exec_result = subprocess.run(
                    ["docker", "exec", self.container_name, "bash", "-c", command],
                    capture_output=True,
                    timeout=timeout
                )
                
                stdout = exec_result.stdout.decode() if exec_result.stdout else ""
                stderr = exec_result.stderr.decode() if exec_result.stderr else ""
                exit_code = exec_result.returncode
            
            # Limit output length
            if len(stdout) > 10000:
                stdout = stdout[:10000] + "\n... (output truncated)"
            if len(stderr) > 10000:
                stderr = stderr[:10000] + "\n... (output truncated)"
            
            output = f"Exit: {exit_code}\n"
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}"
            
            return output
            
        except subprocess.TimeoutExpired:
            return "Error: Command timeout"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def execute_http(self, url: str, method: str = "GET", headers: Optional[Dict] = None,
                    data: Optional[str] = None, json_data: Optional[Dict] = None,
                    timeout: Optional[int] = None) -> str:
        """
        Execute HTTP request using curl in container.
        
        Args:
            url: Target URL
            method: HTTP method (GET, POST, etc.)
            headers: Request headers
            data: Form data
            json_data: JSON data
            timeout: Request timeout
            
        Returns:
            HTTP response as string
        """
        if not url:
            return "Error: No URL provided"
        
        method = method.upper()
        headers = headers or {}
        timeout = timeout or self.timeout
        
        try:
            # Build curl command
            curl_cmd = f"curl -X {method} -i --max-time {timeout}"
            
            for k, v in headers.items():
                curl_cmd += f" -H '{k}: {v}'"
            
            if json_data:
                json_str = json.dumps(json_data).replace("'", "'\\''")
                curl_cmd += f" -H 'Content-Type: application/json' -d '{json_str}'"
            elif data:
                data_str = str(data).replace("'", "'\\''")
                curl_cmd += f" -d '{data_str}'"
            
            curl_cmd += f" '{url}'"
            
            if self.container_obj:
                # Use Docker SDK
                exec_result = self.container_obj.exec_run(
                    ["bash", "-c", curl_cmd],
                    demux=True
                )
                stdout = exec_result.output[0].decode() if exec_result.output[0] else ""
            else:
                # Use subprocess
                exec_result = subprocess.run(
                    ["docker", "exec", self.container_name, "bash", "-c", curl_cmd],
                    capture_output=True,
                    timeout=timeout
                )
                stdout = exec_result.stdout.decode() if exec_result.stdout else ""
            
            # Limit output length
            if len(stdout) > 3000:
                stdout = stdout[:3000] + "\n... (output truncated)"
            
            return f"Response:\n{stdout}"
            
        except Exception as e:
            return f"HTTP Error: {str(e)}"
    
    def execute_python(self, code: str, timeout: Optional[int] = None) -> str:
        """
        Execute Python code in container.
        
        Args:
            code: Python code to execute
            timeout: Execution timeout
            
        Returns:
            Formatted output with exit code, stdout, stderr
        """
        if not code:
            return "Error: No code provided"
        
        # Limit code length
        if len(code) > 5000:
            return "Error: Code too long (max 5000 characters)"
        
        timeout = timeout or self.timeout
        
        try:
            if self.container_obj:
                # Use Docker SDK
                exec_result = self.container_obj.exec_run(
                    ["python3", "-c", code],
                    demux=True
                )
                
                stdout = exec_result.output[0].decode() if exec_result.output[0] else ""
                stderr = exec_result.output[1].decode() if exec_result.output[1] else ""
                exit_code = exec_result.exit_code
                
            else:
                # Use subprocess
                exec_result = subprocess.run(
                    ["docker", "exec", self.container_name, "python3", "-c", code],
                    capture_output=True,
                    timeout=timeout
                )
                
                stdout = exec_result.stdout.decode() if exec_result.stdout else ""
                stderr = exec_result.stderr.decode() if exec_result.stderr else ""
                exit_code = exec_result.returncode
            
            # Limit output length
            if len(stdout) > 10000:
                stdout = stdout[:10000] + "\n... (output truncated)"
            if len(stderr) > 10000:
                stderr = stderr[:10000] + "\n... (output truncated)"
            
            output = f"Exit: {exit_code}\n"
            if stdout:
                output += f"STDOUT:\n{stdout}\n"
            if stderr:
                output += f"STDERR:\n{stderr}"
            
            return output
            
        except subprocess.TimeoutExpired:
            return "Error: Code execution timeout"
        except Exception as e:
            return f"Error: {str(e)}"
