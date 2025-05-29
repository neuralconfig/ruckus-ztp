"""
Base SSH connection handling for RUCKUS ICX switches.
"""
import logging
import re
import time
from typing import Optional, Tuple, Any, Callable

import paramiko

# Set up logging
logger = logging.getLogger(__name__)

class BaseConnection:
    """Base class for SSH connections to RUCKUS ICX switches."""
    
    def __init__(self, ip: str, username: str, password: str, 
                 preferred_password: Optional[str] = None,
                 timeout: int = 30, debug: bool = False,
                 debug_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize switch connection.
        
        Args:
            ip: Switch IP address.
            username: SSH username.
            password: SSH password.
            preferred_password: Password to set on first login.
            timeout: Connection timeout in seconds.
            debug: Enable debug mode.
            debug_callback: Callback for debug messages.
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.preferred_password = preferred_password or password
        self.timeout = timeout
        self.debug = debug
        self.debug_callback = debug_callback
        
        # Connection state
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.shell: Optional[paramiko.Channel] = None
        self.connected = False
        
        # Device info (will be populated)
        self.hostname: Optional[str] = None
        self.model: Optional[str] = None
        self.serial: Optional[str] = None
    
    def connect(self) -> bool:
        """
        Establish SSH connection to the switch.
        
        Returns:
            True if connection successful, False otherwise.
        """
        if self.connected:
            return True
            
        try:
            # Create SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Try connection with current password
            if self._try_connect_with_password(self.password):
                return True
                
            # If that fails, try with preferred password (might already be set)
            if self.preferred_password != self.password:
                if self._try_connect_with_password(self.preferred_password):
                    self.password = self.preferred_password  # Update current password
                    return True
            
            logger.error(f"Failed to connect to switch {self.ip}")
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False
    
    def _try_connect_with_password(self, password: str) -> bool:
        """
        Try to connect with a specific password.
        
        Args:
            password: Password to try.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Connect via SSH
            self.ssh_client.connect(
                hostname=self.ip,
                username=self.username,
                password=password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Open shell
            self.shell = self.ssh_client.invoke_shell()
            self.shell.settimeout(self.timeout)
            
            # Wait for initial prompt and handle first-time login
            time.sleep(2)  # Give time for initial output
            initial_output = ""
            
            # Read initial output
            while self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                initial_output += chunk
                time.sleep(0.1)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Initial output: {initial_output}", "cyan")
            
            # Handle first-time login if needed
            if ("Enter new password:" in initial_output or 
                "New password:" in initial_output or
                "Enter the new password" in initial_output):
                if not self._handle_first_time_login(initial_output):
                    return False
            
            # Check if we're in exec mode (prompt ends with '>')
            is_exec_prompt = re.search(r'>\s*$', initial_output, re.MULTILINE)
            
            if not is_exec_prompt:
                logger.error(f"Did not receive expected prompt from switch {self.ip}")
                return False
            
            self.connected = True
            logger.info(f"Connected to switch {self.ip}")
            return True
            
        except Exception as e:
            logger.debug(f"Connection attempt failed for {self.ip} with password: {e}")
            return False
    
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change.
        
        Args:
            initial_output: Initial output from switch.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            if self.debug and self.debug_callback:
                self.debug_callback("Handling first-time login password change", "yellow")
            
            # Send new password
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Read confirmation prompt
            output = ""
            for _ in range(10):  # Wait up to 10 seconds
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    
                    if ("Re-enter new password:" in output or 
                        "Confirm new password:" in output or
                        "Re-enter the new password" in output or
                        "Enter the reconfirm password" in output or
                        "Please confirm" in output):
                        break
                time.sleep(1)
            else:
                logger.error(f"Did not receive password confirmation prompt. Got: {output}")
                return False
            
            # Confirm new password
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(2)
            
            # Read final output and check for success
            final_output = ""
            for _ in range(10):
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    final_output += chunk
                time.sleep(1)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"First-time login result: {final_output}", "cyan")
            
            # Check if we have a valid prompt after password change
            if re.search(r'>\s*$', final_output, re.MULTILINE):
                # Update current password and combine outputs for final prompt check
                self.password = self.preferred_password
                initial_output += final_output  # Combine for final check
                logger.info(f"Successfully changed password for switch {self.ip}")
            else:
                logger.error("No valid prompt after password change")
                return False
            
        except Exception as e:
            logger.error(f"Error handling first-time login for switch {self.ip}: {e}", exc_info=True)
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch."""
        try:
            if self.shell:
                self.shell.close()
                self.shell = None
                
            if self.ssh_client:
                self.ssh_client.close()
                self.ssh_client = None
                
            self.connected = False
            logger.debug(f"Disconnected from switch {self.ip}")
            
        except Exception as e:
            logger.error(f"Error disconnecting from switch {self.ip}: {e}")
    
    def run_command(self, command: str, wait_time: float = 2.0) -> Tuple[bool, str]:
        """
        Execute a command on the switch.
        
        Args:
            command: Command to execute.
            wait_time: Time to wait for output.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected or not self.shell:
            logger.error(f"Not connected to switch {self.ip}")
            return False, "Not connected"
        
        try:
            # Send command
            self.shell.send(f"{command}\n")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Command: {command}", "yellow")
            
            # Wait for output
            time.sleep(wait_time)
            
            # Read output
            output = ""
            start_time = time.time()
            
            while time.time() - start_time < self.timeout:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    
                    # Check if we have a complete response (ends with prompt)
                    if re.search(r'[>#]\s*$', output, re.MULTILINE):
                        break
                        
                time.sleep(0.1)
            else:
                logger.warning(f"Command '{command}' timed out on switch {self.ip}")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Output: {output}", "cyan")
            
            # Check for common error patterns
            if "Invalid input" in output or "Command not found" in output:
                logger.error(f"Command '{command}' failed on switch {self.ip}: {output}")
                return False, output
            
            return True, output
            
        except Exception as e:
            logger.error(f"Error executing command '{command}' on switch {self.ip}: {e}", exc_info=True)
            return False, f"Error: {e}"
    
    def enter_config_mode(self) -> bool:
        """
        Enter configuration mode.
        
        Returns:
            True if successful, False otherwise.
        """
        success, output = self.run_command("configure terminal")
        
        if success and "(config)" in output:
            if self.debug and self.debug_callback:
                self.debug_callback("Entered configuration mode", "green")
            return True
        else:
            logger.error(f"Failed to enter config mode on switch {self.ip}: {output}")
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration mode.
        
        Args:
            save: Whether to save configuration.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Exit config mode
            success, output = self.run_command("exit")
            
            if not success:
                logger.error(f"Failed to exit config mode on switch {self.ip}: {output}")
                return False
            
            # Save configuration if requested
            if save:
                success, output = self.run_command("write memory")
                if not success:
                    logger.error(f"Failed to save configuration on switch {self.ip}: {output}")
                    return False
                    
                if self.debug and self.debug_callback:
                    self.debug_callback("Configuration saved", "green")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting config mode on switch {self.ip}: {e}", exc_info=True)
            return False
    
    def __enter__(self):
        """Context manager entry."""
        if self.connect():
            return self
        else:
            raise ConnectionError(f"Failed to connect to switch {self.ip}")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()