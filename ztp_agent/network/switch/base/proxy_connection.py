"""
Proxy-aware SSH connection handling for RUCKUS ICX switches.
This class can route SSH commands through an SSH proxy when configured.
"""
import logging
import asyncio
from typing import Optional, Tuple, Any, Callable
from ztp_agent.network.switch.base.connection import BaseConnection

# Set up logging
logger = logging.getLogger(__name__)


class ProxyAwareConnection(BaseConnection):
    """Proxy-aware SSH connection that can route commands through SSH proxy."""
    
    def __init__(self, ip: str, username: str, password: str, 
                 preferred_password: Optional[str] = None,
                 timeout: int = 30, debug: bool = False,
                 debug_callback: Optional[Callable[[str, str], None]] = None,
                 ssh_executor: Optional[Callable] = None):
        """
        Initialize proxy-aware switch connection.
        
        Args:
            ip: Switch IP address.
            username: SSH username.
            password: SSH password.
            preferred_password: Password to set on first login.
            timeout: Connection timeout in seconds.
            debug: Enable debug mode.
            debug_callback: Callback for debug messages.
            ssh_executor: Optional SSH executor function for proxy support.
        """
        super().__init__(ip, username, password, preferred_password, timeout, debug, debug_callback)
        self.ssh_executor = ssh_executor
        
        logger.debug(f"Created ProxyAwareConnection for {ip}, SSH executor: {ssh_executor is not None}")
    
    def run_command(self, command: str, expect_prompt: bool = True) -> Tuple[bool, str]:
        """
        Execute a command on the switch using proxy if configured.
        
        Args:
            command: Command to execute.
            expect_prompt: Whether to wait for command prompt.
            
        Returns:
            Tuple of (success, output).
        """
        if self.ssh_executor:
            # Use proxy execution
            try:
                # Run the SSH command through proxy
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an event loop, need to handle differently
                    import concurrent.futures
                    import threading
                    
                    result_container = {"success": False, "output": ""}
                    exception_container = {"exception": None}
                    
                    def run_proxy_command():
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                success, output = new_loop.run_until_complete(
                                    self.ssh_executor(self.ip, self.username, self.password, command, self.timeout)
                                )
                                result_container["success"] = success
                                result_container["output"] = output
                            finally:
                                new_loop.close()
                        except Exception as e:
                            exception_container["exception"] = e
                    
                    thread = threading.Thread(target=run_proxy_command)
                    thread.start()
                    thread.join()
                    
                    if exception_container["exception"]:
                        raise exception_container["exception"]
                    
                    return result_container["success"], result_container["output"]
                else:
                    # No event loop running, can use asyncio.run
                    success, output = asyncio.run(
                        self.ssh_executor(self.ip, self.username, self.password, command, self.timeout)
                    )
                    return success, output
                    
            except Exception as e:
                logger.error(f"Proxy SSH execution failed for {self.ip}: {e}")
                return False, f"Proxy execution error: {str(e)}"
        else:
            # Fall back to direct SSH connection
            return super().run_command(command, expect_prompt)
    
    def connect(self) -> bool:
        """
        Establish connection - for proxy mode, this is a no-op since connections are per-command.
        
        Returns:
            True if proxy executor is available or direct connection successful.
        """
        if self.ssh_executor:
            # For proxy mode, we don't maintain persistent connections
            self.connected = True
            return True
        else:
            # Use direct connection
            return super().connect()
    
    def disconnect(self) -> None:
        """Disconnect from switch - for proxy mode, this is a no-op."""
        if self.ssh_executor:
            # For proxy mode, no persistent connection to close
            self.connected = False
        else:
            # Use direct disconnection
            super().disconnect()
    
    def __enter__(self):
        """Context manager entry - connect to switch or prepare proxy."""
        if self.ssh_executor:
            # For proxy mode, just mark as connected
            self.connected = True
            return self
        else:
            # Use direct connection context manager
            return super().__enter__()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect or cleanup proxy."""
        if self.ssh_executor:
            # For proxy mode, just mark as disconnected
            self.connected = False
        else:
            # Use direct connection context manager
            return super().__exit__(exc_type, exc_val, exc_tb)