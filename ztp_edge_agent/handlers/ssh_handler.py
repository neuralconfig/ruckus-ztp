"""SSH command execution handler."""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
import paramiko
from concurrent.futures import ThreadPoolExecutor


class SSHHandler:
    """Handler for SSH command execution."""
    
    def __init__(self, command_timeout: int = 60):
        """Initialize SSH handler.
        
        Args:
            command_timeout: Default timeout for SSH commands in seconds
        """
        self.command_timeout = command_timeout
        self.logger = logging.getLogger(__name__)
        self._executor = ThreadPoolExecutor(max_workers=1)
    
    async def execute_command(
        self,
        host: str,
        username: str,
        password: str,
        command: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """Execute SSH command on remote host.
        
        Args:
            host: Target host IP address
            username: SSH username
            password: SSH password
            command: Command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Dictionary with execution results
        """
        timeout = timeout or self.command_timeout
        start_time = time.time()
        
        try:
            # Run SSH command in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._execute_ssh_command,
                host, username, password, command, timeout
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return {
                "output": result,
                "execution_time_ms": execution_time
            }
            
        except Exception as e:
            self.logger.error(f"SSH command execution failed: {e}")
            raise
    
    def _execute_ssh_command(
        self,
        host: str,
        username: str,
        password: str,
        command: str,
        timeout: int
    ) -> str:
        """Execute SSH command synchronously.
        
        This follows the pattern from the existing RUCKUS ZTP codebase.
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Connect to host
            self.logger.debug(f"Connecting to {host}...")
            ssh.connect(
                hostname=host,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            
            # Execute command
            self.logger.debug(f"Executing command: {command}")
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            
            # Read output
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            
            if error:
                self.logger.warning(f"Command stderr: {error}")
            
            return output
            
        finally:
            ssh.close()
    
    def __del__(self):
        """Cleanup thread pool on deletion."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)