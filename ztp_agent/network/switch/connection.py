"""
Connection management module for interacting with RUCKUS ICX switches.
"""
import logging
import time
import paramiko
import re
import socket
from typing import Dict, List, Optional, Any, Tuple

from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

from ztp_agent.network.switch.base import SwitchConnection

class SwitchOperation(SwitchConnection):
    """Class for interacting with RUCKUS ICX switches via SSH"""
    
    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = 30,
        preferred_password: str = None,
        debug: bool = False,
        debug_callback = None
    ):
        """
        Initialize switch operation.
        
        Args:
            ip: IP address of the switch.
            username: Username for SSH connection.
            password: Password for SSH connection (initial password).
            timeout: Command timeout in seconds.
            preferred_password: Password to set during first-time login (if None, use password).
            debug: Whether to enable debug mode.
            debug_callback: Function to call with debug messages.
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.preferred_password = preferred_password or password
        self.timeout = timeout
        self.client = None
        self.connected = False
        self.debug = debug
        self.debug_callback = debug_callback
        self.hostname = f"switch-{ip.replace('.', '-')}"  # Default hostname until we get the real one
        self.model = None
        self.serial = None
        
    def _debug_message(self, message: str, color: str = "yellow") -> None:
        """Helper method to print debug messages"""
        if self.debug and self.debug_callback:
            self.debug_callback(message, color=color)
    
    def _try_connect_with_password(self, password: str, password_desc: str) -> tuple:
        """Try to connect with the given password
        
        Args:
            password: Password to try
            password_desc: Description of the password (for logging)
            
        Returns:
            Tuple of (success, error), where success is True if connected and error is the exception if failed
        """
        try:
            self._debug_message(f"Trying {password_desc} password for {self.ip} (attempt {self.connection_attempts}/{self.max_connection_attempts})")
            
            self.client.connect(
                hostname=self.ip,
                username=self.username,
                password=password,
                timeout=self.timeout,
                allow_agent=False,  # Don't use SSH agent
                look_for_keys=False  # Don't look for SSH keys
            )
            
            if password_desc != "default":
                logger.info(f"Connected to {self.ip} using {password_desc} password")
                self._debug_message(f"Connected using {password_desc} password", color="green")
                
            return True, None
            
        except paramiko.ssh_exception.AuthenticationException as e:
            logger.warning(f"Authentication failed with {password_desc} password for {self.ip}: {e}")
            return False, e
            
        except (paramiko.ssh_exception.SSHException, TimeoutError) as e:
            logger.warning(f"Connection issue to {self.ip} with {password_desc} password: {e}")
            self._debug_message(f"Connection issue: {e}, will retry...", color="yellow")
            
            # Close and recreate the client
            if self.client:
                self.client.close()
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            return False, e
    
    def __enter__(self):
        """Enter context manager"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager"""
        self.disconnect()
    
    def connect(self) -> bool:
        """
        Connect to the switch via SSH.
        
        Returns:
            True if successful, False otherwise.
        """
        if self.connected:
            return True
        
        try:
            # Print debug message if debug mode is enabled
            self._debug_message(f"Connecting to switch {self.ip} with username {self.username}")
            
            # Test if the SSH port is open
            try:
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(5)
                test_socket.connect((self.ip, 22))
                test_socket.close()
                self._debug_message(f"SSH port is open on {self.ip}", color="green")
            except Exception as e:
                self._debug_message(f"SSH port test failed on {self.ip}: {e}", color="red")
                logger.error(f"SSH port (22) is not accessible on {self.ip}: {e}")
                raise paramiko.ssh_exception.NoValidConnectionsError({(self.ip, 22): e})
            
            # Use Transport instead of SSHClient for better control
            transport = paramiko.Transport((self.ip, 22))
            
            if self.debug:
                transport.set_log_channel("paramiko")
                self._debug_message(f"Starting SSH transport", color="yellow")
                
            transport.start_client()
            
            # Authenticate with username and password
            self._debug_message(f"Authenticating with username {self.username}", color="yellow")
            transport.auth_password(username=self.username, password=self.password)
            self._debug_message(f"Authentication successful", color="green")
            
            # Open a channel and get a shell
            channel = transport.open_session()
            channel.set_combine_stderr(True)
            channel.get_pty()
            channel.invoke_shell()
            
            # Save references
            self.transport = transport
            self.channel = channel
            
            # Wait for initial output (2 seconds should be enough)
            time.sleep(2)
            output = ""
            if channel.recv_ready():
                output = channel.recv(4096).decode('utf-8', errors='replace')
                if self.debug:
                    self._debug_message(f"Initial output: {output}", color="yellow")
            
            # Check for first-time login password change prompt
            if "Please change the password" in output or "Enter the new password" in output:
                logger.info(f"First-time login detected for {self.ip}, handling password change")
                self._debug_message(f"First-time login detected, will change password", color="yellow")
                return self._handle_first_time_login(output)
            
            # Send a newline to get a prompt
            channel.send("\n")
            time.sleep(1)
            if channel.recv_ready():
                new_output = channel.recv(4096).decode('utf-8', errors='replace')
                output += new_output
                if self.debug:
                    self._debug_message(f"After newline: {new_output}", color="yellow")
            
            # Check if we're at any command prompt (either exec '>' or enable '#')
            if not (re.search(r'[>#]', output) or re.search(r'\w+\s*[>#]', output)):
                # Try sending a newline again
                channel.send("\n")
                time.sleep(1)
                if channel.recv_ready():
                    new_output = channel.recv(4096).decode('utf-8', errors='replace')
                    output += new_output
                    if self.debug:
                        self._debug_message(f"After second newline: {new_output}", color="yellow")
                        
                if not (re.search(r'[>#]', output) or re.search(r'\w+\s*[>#]', output)):
                    logger.error(f"Did not receive prompt from switch {self.ip}. Output: {output}")
                    self.disconnect()
                    return False
            
            # Check if we're in exec mode (prompt ends with '>')
            is_exec_prompt = re.search(r'>\s*
            
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change prompt.
        
        Args:
            initial_output: Initial output from the shell.
            
        Returns:
            True if successfully handled password change, False otherwise.
        """
        try:
            # Print debug message
            if self.debug and self.debug_callback:
                self.debug_callback("First-time login detected, handling password change", color="yellow")
            
            # Check where we are in the password change process
            if "Enter the new password" not in initial_output:
                # Wait for the new password prompt
                self._wait_for_pattern("Enter the new password")
            
            # Send new password (using the preferred password)
            logger.debug(f"Sending new password: {self.preferred_password}")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending new password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for reconfirm prompt and send password again
            self._wait_for_pattern("Enter the reconfirm password")
            logger.debug("Sending reconfirm password")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending reconfirm password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for confirmation
            output = self._wait_for_pattern("Password modified successfully")
            if not output:
                logger.error("Password change failed")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Password change failed", color="red")
                    
                return False
                
            logger.info("Password changed successfully on first login")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Password changed successfully", color="green")
            
            # Wait for command prompt
            output = self._wait_for_pattern(r"[>#]")
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug("Entering enable mode after password change")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Entering enable mode after password change", color="yellow")
                
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    # After password change, we need to use the preferred password
                    if self.debug and self.debug_callback:
                        self.debug_callback("Sending preferred password for enable mode", color="yellow")
                        
                    self.shell.send(f"{self.preferred_password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error("Failed to enter enable mode after password change")
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback("Failed to enter enable mode after password change", color="red")
                        
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Successfully connected to switch {self.ip} after password change")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Successfully connected to switch {self.ip} after password change", color="green")
            
            # Disable pagination to avoid --More-- prompts
            success, output = self.run_command("skip-page-display")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Disabled pagination with skip-page-display", color="green")
            else:
                logger.warning("Failed to disable pagination with skip-page-display")
                
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Switch identified as {self.hostname}", color="yellow")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip} after password change")
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling first-time login: {e}", exc_info=True)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Error handling first-time login: {e}", color="red")
                
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
        
    def _wait_for_pattern(self, pattern: str, timeout: int = 30, send_newline_after: int = 0) -> str:
        """
        Wait for a specific pattern in the output.
        
        Args:
            pattern: Pattern to wait for (string or regex pattern).
            timeout: Timeout in seconds.
            send_newline_after: Send a newline after this many seconds if no output is received
                                (helps with some switches that need an initial prompt).
            
        Returns:
            Output received or empty string if timeout.
        """
        start_time = time.time()
        buffer = ""
        last_output_time = time.time()
        newline_sent = False
        newlines_sent = 0
        max_newlines = 3  # Maximum number of newlines to send
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Waiting for pattern: {pattern}", color="yellow")
        
        while (time.time() - start_time) < timeout:
            # Check if data is available
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='replace')  # Increased buffer size
                buffer += chunk
                last_output_time = time.time()
                
                # Debug output for received chunks
                if self.debug and self.debug_callback and chunk.strip():
                    self.debug_callback(f"RECV: {chunk}", color="yellow")
                
                # Check if pattern is found
                if isinstance(pattern, str) and pattern in buffer:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Pattern found: {pattern}", color="green")
                    return buffer
                elif not isinstance(pattern, str) and re.search(pattern, buffer):
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Regex pattern found: {pattern}", color="green")
                    return buffer
            
            # If send_newline_after is set and we haven't received output for that duration,
            # send newlines periodically to help prompt a response
            if send_newline_after > 0 and (time.time() - last_output_time) > send_newline_after:
                # Only send a limited number of newlines
                if newlines_sent < max_newlines:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"No output received for {send_newline_after}s, sending newline ({newlines_sent+1}/{max_newlines})", color="yellow")
                    self.shell.send("\n")
                    newlines_sent += 1
                    last_output_time = time.time()  # Reset the timer
                    time.sleep(1)  # Wait a bit after sending newline
            
            # If we haven't received any output after half the timeout, try sending a newline once
            if not buffer and not newline_sent and (time.time() - start_time) > (timeout / 2):
                if self.debug and self.debug_callback:
                    self.debug_callback("No output received after half timeout, sending newline", color="yellow")
                self.shell.send("\n")
                newline_sent = True
                time.sleep(1)  # Wait a bit after sending newline
            
            time.sleep(0.1)
        
        # If we've gotten some output but not the exact pattern, try
        # checking for common shell prompts in case we missed the pattern
        if buffer:
            # Check for common command prompts that might indicate success
            if re.search(r'[\w\-\.]+[#>]\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found command prompt instead of exact pattern: {pattern}", color="yellow")
                return buffer
            
            # For enable mode check, consider hash prompt at the end as a success
            if pattern == r'#\s*$' and re.search(r'#\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found enable prompt (#) at the end of buffer", color="green")
                return buffer
        
        logger.error(f"Timeout waiting for pattern: {pattern}. Buffer: {buffer[:100]}...")
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Timeout waiting for pattern: {pattern}. Buffer received: {buffer}", color="red")
            
        return ""
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            timeout: Override the default timeout value.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            
            # Print command in debug mode
            if self.debug and self.debug_callback:
                self.debug_callback(f"SEND: {command}", color="yellow")
            
            # Clear any pending output before sending command
            if self.shell.recv_ready():
                self.shell.recv(4096)
                
            # Send the command
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Wait for command output and command prompt
            start_time = time.time()
            output = ""
            cmd_timeout = timeout or self.timeout
            prompt_found = False
            
            # Wait until we see a command prompt or timeout
            while (time.time() - start_time) < cmd_timeout and not prompt_found:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Debug output
                    if self.debug and self.debug_callback and chunk.strip():
                        self.debug_callback(f"RECV: {chunk}", color="yellow")
                    
                    # Check if we've reached the command prompt
                    if re.search(r'[\w\-\.]+[#>]\s*$', chunk.strip()) or re.search(r'[#>]\s*$', chunk.strip()):
                        prompt_found = True
                        break
                
                time.sleep(0.1)
            
            # If after timeout we haven't found a prompt, send a newline and try to get one
            if not prompt_found:
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected after command, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Try to get the final prompt
                if self.shell.recv_ready():
                    final_chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += final_chunk
            
            # Debug full output
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete command output: {output}", color="yellow")
            
            # Check for common errors in command output
            if 'Invalid input' in output or 'Error:' in output or 'Incomplete command' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            # Filter the command echo from output if present
            # This pattern looks for the command followed by a linebreak
            cmd_echo_pattern = f"^{command}\r\n"
            output = re.sub(cmd_echo_pattern, "", output, flags=re.MULTILINE)
            
            # Remove the prompt at the end
            output = re.sub(r'[\w\-\.]+[#>]\s*$', "", output)
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
            
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First ensure we're in enable mode
            if not self.connected:
                if not self.connect():
                    logger.error(f"Failed to connect to switch {self.ip}")
                    return False
            
            # Send the configure terminal command
            if self.debug and self.debug_callback:
                self.debug_callback("Entering configuration mode", color="yellow")
            
            success, output = self.run_command("configure terminal", wait_time=2.0)
            
            # Check if we're in config mode
            if not success or "Error" in output:
                logger.error(f"Failed to enter configuration mode: {output}")
                return False
            
            # Verify by looking for (config)# prompt in the next command output
            verify_success, verify_output = self.run_command("\n", wait_time=1.0)
            if "(config)" not in verify_output and not re.search(r'\(config\)[#>]', verify_output):
                logger.error(f"Failed to verify configuration mode: {verify_output}")
                return False
                
            logger.debug("Successfully entered configuration mode")
            return True
            
        except Exception as e:
            logger.error(f"Error entering configuration mode: {e}", exc_info=True)
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First send exit to leave config mode
            success, _ = self.run_command("exit", wait_time=1.0)
            
            if self.debug and self.debug_callback:
                self.debug_callback("Exiting configuration mode", color="yellow")
            
            # If requested, save configuration
            if save:
                save_success, save_output = self.run_command("write memory", wait_time=2.0)
                if not save_success:
                    logger.error(f"Failed to save configuration: {save_output}")
                    return False
                logger.info("Configuration saved with write memory")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting configuration mode: {e}", exc_info=True)
            return False
    
    def get_model(self) -> Optional[str]:
        """
        Get the switch model.
        
        Returns:
            Switch model string or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch model...", color="yellow")
            
        # First try with full show version
        success, output = self.run_command("show version")
        
        if success:
            # Look for HW line
            if self.debug and self.debug_callback:
                self.debug_callback(f"Got version output: {output[:200]}...", color="yellow")
                
            hw_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if hw_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {hw_match.group(1)}", color="green")
                return hw_match.group(1)
                
            # Look for ICX model in the output
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from regex: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # If we couldn't get it from show version, try more specific commands
        success, output = self.run_command("show version | include HW:")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"HW line output: {output}", color="yellow")
                
            # Parse output - should contain something like "HW: Stackable ICX8200-C08PF-POE"
            model_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # Try directly searching for ICX
        success, output = self.run_command("show version | include ICX")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"ICX line output: {output}", color="yellow")
                
            # Parse output - should contain something like "ICX6450-24" or "ICX7150-48P"
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from ICX line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch model", color="red")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get the switch serial number.
        
        Returns:
            Switch serial number or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch serial number...", color="yellow")
            
        # First try with full show version to avoid multiple commands
        if hasattr(self, '_version_output') and self._version_output:
            # Use cached output if available
            output = self._version_output
            if self.debug and self.debug_callback:
                self.debug_callback("Using cached version output", color="yellow")
        else:
            # Get full output
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
        
        if hasattr(self, '_version_output') and self._version_output:
            # Look for Serial in the full output
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from full output: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Try with specific grep for Serial (capital S)
        success, output = self.run_command("show version | include Serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"Serial line output: {output}", color="yellow")
                
            # Parse output - should contain something like "Serial  #:FNS4303U055"
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from Serial line: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Fallback to lowercase search
        success, output = self.run_command("show version | include serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"serial line output: {output}", color="yellow")
                
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from case-insensitive search: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # As a last resort, try getting full show version output without the pipe
        if not hasattr(self, '_version_output'):
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
                
                # Try to find serial
                serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
                if serial_match:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found serial from full version output: {serial_match.group(1)}", color="green")
                    return serial_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch serial number", color="red")
        return None

    # Add the methods required by ZTP process
    def apply_base_config(self, base_config: str) -> bool:
        """
        Apply base configuration to the switch.
        This should be done first before any port configuration.
        
        Args:
            base_config: Base configuration string to apply.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content preview: {base_config[:200]}...")  # Log first 200 chars
            if self.debug and self.debug_callback:
                self.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.exit_config_mode(save=False)
            return False

    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration after VLANs have been created.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.run_command("exit")  # Exit interface config
                    self.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False
            
    # Import discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.run_command("trace-l2 vlan 1")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.debug and self.debug_callback:
                                    self.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map, output.strip()) is not None
            is_enable_prompt = re.search(r'#\s*
            
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change prompt.
        
        Args:
            initial_output: Initial output from the shell.
            
        Returns:
            True if successfully handled password change, False otherwise.
        """
        try:
            # Print debug message
            if self.debug and self.debug_callback:
                self.debug_callback("First-time login detected, handling password change", color="yellow")
            
            # Check where we are in the password change process
            if "Enter the new password" not in initial_output:
                # Wait for the new password prompt
                self._wait_for_pattern("Enter the new password")
            
            # Send new password (using the preferred password)
            logger.debug(f"Sending new password: {self.preferred_password}")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending new password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for reconfirm prompt and send password again
            self._wait_for_pattern("Enter the reconfirm password")
            logger.debug("Sending reconfirm password")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending reconfirm password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for confirmation
            output = self._wait_for_pattern("Password modified successfully")
            if not output:
                logger.error("Password change failed")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Password change failed", color="red")
                    
                return False
                
            logger.info("Password changed successfully on first login")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Password changed successfully", color="green")
            
            # Wait for command prompt
            output = self._wait_for_pattern(r"[>#]")
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug("Entering enable mode after password change")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Entering enable mode after password change", color="yellow")
                
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    # After password change, we need to use the preferred password
                    if self.debug and self.debug_callback:
                        self.debug_callback("Sending preferred password for enable mode", color="yellow")
                        
                    self.shell.send(f"{self.preferred_password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error("Failed to enter enable mode after password change")
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback("Failed to enter enable mode after password change", color="red")
                        
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Successfully connected to switch {self.ip} after password change")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Successfully connected to switch {self.ip} after password change", color="green")
            
            # Disable pagination to avoid --More-- prompts
            success, output = self.run_command("skip-page-display")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Disabled pagination with skip-page-display", color="green")
            else:
                logger.warning("Failed to disable pagination with skip-page-display")
                
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Switch identified as {self.hostname}", color="yellow")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip} after password change")
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling first-time login: {e}", exc_info=True)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Error handling first-time login: {e}", color="red")
                
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
        
    def _wait_for_pattern(self, pattern: str, timeout: int = 30, send_newline_after: int = 0) -> str:
        """
        Wait for a specific pattern in the output.
        
        Args:
            pattern: Pattern to wait for (string or regex pattern).
            timeout: Timeout in seconds.
            send_newline_after: Send a newline after this many seconds if no output is received
                                (helps with some switches that need an initial prompt).
            
        Returns:
            Output received or empty string if timeout.
        """
        start_time = time.time()
        buffer = ""
        last_output_time = time.time()
        newline_sent = False
        newlines_sent = 0
        max_newlines = 3  # Maximum number of newlines to send
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Waiting for pattern: {pattern}", color="yellow")
        
        while (time.time() - start_time) < timeout:
            # Check if data is available
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='replace')  # Increased buffer size
                buffer += chunk
                last_output_time = time.time()
                
                # Debug output for received chunks
                if self.debug and self.debug_callback and chunk.strip():
                    self.debug_callback(f"RECV: {chunk}", color="yellow")
                
                # Check if pattern is found
                if isinstance(pattern, str) and pattern in buffer:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Pattern found: {pattern}", color="green")
                    return buffer
                elif not isinstance(pattern, str) and re.search(pattern, buffer):
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Regex pattern found: {pattern}", color="green")
                    return buffer
            
            # If send_newline_after is set and we haven't received output for that duration,
            # send newlines periodically to help prompt a response
            if send_newline_after > 0 and (time.time() - last_output_time) > send_newline_after:
                # Only send a limited number of newlines
                if newlines_sent < max_newlines:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"No output received for {send_newline_after}s, sending newline ({newlines_sent+1}/{max_newlines})", color="yellow")
                    self.shell.send("\n")
                    newlines_sent += 1
                    last_output_time = time.time()  # Reset the timer
                    time.sleep(1)  # Wait a bit after sending newline
            
            # If we haven't received any output after half the timeout, try sending a newline once
            if not buffer and not newline_sent and (time.time() - start_time) > (timeout / 2):
                if self.debug and self.debug_callback:
                    self.debug_callback("No output received after half timeout, sending newline", color="yellow")
                self.shell.send("\n")
                newline_sent = True
                time.sleep(1)  # Wait a bit after sending newline
            
            time.sleep(0.1)
        
        # If we've gotten some output but not the exact pattern, try
        # checking for common shell prompts in case we missed the pattern
        if buffer:
            # Check for common command prompts that might indicate success
            if re.search(r'[\w\-\.]+[#>]\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found command prompt instead of exact pattern: {pattern}", color="yellow")
                return buffer
            
            # For enable mode check, consider hash prompt at the end as a success
            if pattern == r'#\s*$' and re.search(r'#\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found enable prompt (#) at the end of buffer", color="green")
                return buffer
        
        logger.error(f"Timeout waiting for pattern: {pattern}. Buffer: {buffer[:100]}...")
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Timeout waiting for pattern: {pattern}. Buffer received: {buffer}", color="red")
            
        return ""
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            timeout: Override the default timeout value.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            
            # Print command in debug mode
            if self.debug and self.debug_callback:
                self.debug_callback(f"SEND: {command}", color="yellow")
            
            # Clear any pending output before sending command
            if self.shell.recv_ready():
                self.shell.recv(4096)
                
            # Send the command
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Wait for command output and command prompt
            start_time = time.time()
            output = ""
            cmd_timeout = timeout or self.timeout
            prompt_found = False
            
            # Wait until we see a command prompt or timeout
            while (time.time() - start_time) < cmd_timeout and not prompt_found:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Debug output
                    if self.debug and self.debug_callback and chunk.strip():
                        self.debug_callback(f"RECV: {chunk}", color="yellow")
                    
                    # Check if we've reached the command prompt
                    if re.search(r'[\w\-\.]+[#>]\s*$', chunk.strip()) or re.search(r'[#>]\s*$', chunk.strip()):
                        prompt_found = True
                        break
                
                time.sleep(0.1)
            
            # If after timeout we haven't found a prompt, send a newline and try to get one
            if not prompt_found:
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected after command, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Try to get the final prompt
                if self.shell.recv_ready():
                    final_chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += final_chunk
            
            # Debug full output
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete command output: {output}", color="yellow")
            
            # Check for common errors in command output
            if 'Invalid input' in output or 'Error:' in output or 'Incomplete command' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            # Filter the command echo from output if present
            # This pattern looks for the command followed by a linebreak
            cmd_echo_pattern = f"^{command}\r\n"
            output = re.sub(cmd_echo_pattern, "", output, flags=re.MULTILINE)
            
            # Remove the prompt at the end
            output = re.sub(r'[\w\-\.]+[#>]\s*$', "", output)
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
            
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First ensure we're in enable mode
            if not self.connected:
                if not self.connect():
                    logger.error(f"Failed to connect to switch {self.ip}")
                    return False
            
            # Send the configure terminal command
            if self.debug and self.debug_callback:
                self.debug_callback("Entering configuration mode", color="yellow")
            
            success, output = self.run_command("configure terminal", wait_time=2.0)
            
            # Check if we're in config mode
            if not success or "Error" in output:
                logger.error(f"Failed to enter configuration mode: {output}")
                return False
            
            # Verify by looking for (config)# prompt in the next command output
            verify_success, verify_output = self.run_command("\n", wait_time=1.0)
            if "(config)" not in verify_output and not re.search(r'\(config\)[#>]', verify_output):
                logger.error(f"Failed to verify configuration mode: {verify_output}")
                return False
                
            logger.debug("Successfully entered configuration mode")
            return True
            
        except Exception as e:
            logger.error(f"Error entering configuration mode: {e}", exc_info=True)
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First send exit to leave config mode
            success, _ = self.run_command("exit", wait_time=1.0)
            
            if self.debug and self.debug_callback:
                self.debug_callback("Exiting configuration mode", color="yellow")
            
            # If requested, save configuration
            if save:
                save_success, save_output = self.run_command("write memory", wait_time=2.0)
                if not save_success:
                    logger.error(f"Failed to save configuration: {save_output}")
                    return False
                logger.info("Configuration saved with write memory")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting configuration mode: {e}", exc_info=True)
            return False
    
    def get_model(self) -> Optional[str]:
        """
        Get the switch model.
        
        Returns:
            Switch model string or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch model...", color="yellow")
            
        # First try with full show version
        success, output = self.run_command("show version")
        
        if success:
            # Look for HW line
            if self.debug and self.debug_callback:
                self.debug_callback(f"Got version output: {output[:200]}...", color="yellow")
                
            hw_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if hw_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {hw_match.group(1)}", color="green")
                return hw_match.group(1)
                
            # Look for ICX model in the output
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from regex: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # If we couldn't get it from show version, try more specific commands
        success, output = self.run_command("show version | include HW:")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"HW line output: {output}", color="yellow")
                
            # Parse output - should contain something like "HW: Stackable ICX8200-C08PF-POE"
            model_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # Try directly searching for ICX
        success, output = self.run_command("show version | include ICX")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"ICX line output: {output}", color="yellow")
                
            # Parse output - should contain something like "ICX6450-24" or "ICX7150-48P"
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from ICX line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch model", color="red")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get the switch serial number.
        
        Returns:
            Switch serial number or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch serial number...", color="yellow")
            
        # First try with full show version to avoid multiple commands
        if hasattr(self, '_version_output') and self._version_output:
            # Use cached output if available
            output = self._version_output
            if self.debug and self.debug_callback:
                self.debug_callback("Using cached version output", color="yellow")
        else:
            # Get full output
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
        
        if hasattr(self, '_version_output') and self._version_output:
            # Look for Serial in the full output
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from full output: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Try with specific grep for Serial (capital S)
        success, output = self.run_command("show version | include Serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"Serial line output: {output}", color="yellow")
                
            # Parse output - should contain something like "Serial  #:FNS4303U055"
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from Serial line: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Fallback to lowercase search
        success, output = self.run_command("show version | include serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"serial line output: {output}", color="yellow")
                
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from case-insensitive search: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # As a last resort, try getting full show version output without the pipe
        if not hasattr(self, '_version_output'):
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
                
                # Try to find serial
                serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
                if serial_match:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found serial from full version output: {serial_match.group(1)}", color="green")
                    return serial_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch serial number", color="red")
        return None

    # Add the methods required by ZTP process
    def apply_base_config(self, base_config: str) -> bool:
        """
        Apply base configuration to the switch.
        This should be done first before any port configuration.
        
        Args:
            base_config: Base configuration string to apply.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content preview: {base_config[:200]}...")  # Log first 200 chars
            if self.debug and self.debug_callback:
                self.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.exit_config_mode(save=False)
            return False

    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration after VLANs have been created.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.run_command("exit")  # Exit interface config
                    self.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False
            
    # Import discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.run_command("trace-l2 vlan 1")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.debug and self.debug_callback:
                                    self.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map, output.strip()) is not None
            
            # If we're in exec mode, enter enable mode
            if is_exec_prompt and not is_enable_prompt:
                logger.debug(f"In exec mode, entering enable mode on switch {self.ip}")
                self._debug_message("Detected exec mode (>), entering enable mode", color="yellow")
                
                # Send enable command
                channel.send("enable\n")
                time.sleep(1)
                
                # Wait for password prompt or enable prompt
                if channel.recv_ready():
                    new_output = channel.recv(4096).decode('utf-8', errors='replace')
                    if self.debug:
                        self._debug_message(f"After enable command: {new_output}", color="yellow")
                    
                    # If password prompt appears
                    if "Password:" in new_output:
                        self._debug_message("Enable password required, sending password", color="yellow")
                        channel.send(f"{self.password}\n")
                        time.sleep(1)
                        
                        if channel.recv_ready():
                            new_output = channel.recv(4096).decode('utf-8', errors='replace')
                            if self.debug:
                                self._debug_message(f"After enable password: {new_output}", color="yellow")
                    
                    # Verify we're in enable mode
                    if not re.search(r'#\s*
            
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change prompt.
        
        Args:
            initial_output: Initial output from the shell.
            
        Returns:
            True if successfully handled password change, False otherwise.
        """
        try:
            # Print debug message
            if self.debug and self.debug_callback:
                self.debug_callback("First-time login detected, handling password change", color="yellow")
            
            # Check where we are in the password change process
            if "Enter the new password" not in initial_output:
                # Wait for the new password prompt
                self._wait_for_pattern("Enter the new password")
            
            # Send new password (using the preferred password)
            logger.debug(f"Sending new password: {self.preferred_password}")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending new password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for reconfirm prompt and send password again
            self._wait_for_pattern("Enter the reconfirm password")
            logger.debug("Sending reconfirm password")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending reconfirm password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for confirmation
            output = self._wait_for_pattern("Password modified successfully")
            if not output:
                logger.error("Password change failed")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Password change failed", color="red")
                    
                return False
                
            logger.info("Password changed successfully on first login")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Password changed successfully", color="green")
            
            # Wait for command prompt
            output = self._wait_for_pattern(r"[>#]")
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug("Entering enable mode after password change")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Entering enable mode after password change", color="yellow")
                
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    # After password change, we need to use the preferred password
                    if self.debug and self.debug_callback:
                        self.debug_callback("Sending preferred password for enable mode", color="yellow")
                        
                    self.shell.send(f"{self.preferred_password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error("Failed to enter enable mode after password change")
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback("Failed to enter enable mode after password change", color="red")
                        
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Successfully connected to switch {self.ip} after password change")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Successfully connected to switch {self.ip} after password change", color="green")
            
            # Disable pagination to avoid --More-- prompts
            success, output = self.run_command("skip-page-display")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Disabled pagination with skip-page-display", color="green")
            else:
                logger.warning("Failed to disable pagination with skip-page-display")
                
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Switch identified as {self.hostname}", color="yellow")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip} after password change")
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling first-time login: {e}", exc_info=True)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Error handling first-time login: {e}", color="red")
                
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
        
    def _wait_for_pattern(self, pattern: str, timeout: int = 30, send_newline_after: int = 0) -> str:
        """
        Wait for a specific pattern in the output.
        
        Args:
            pattern: Pattern to wait for (string or regex pattern).
            timeout: Timeout in seconds.
            send_newline_after: Send a newline after this many seconds if no output is received
                                (helps with some switches that need an initial prompt).
            
        Returns:
            Output received or empty string if timeout.
        """
        start_time = time.time()
        buffer = ""
        last_output_time = time.time()
        newline_sent = False
        newlines_sent = 0
        max_newlines = 3  # Maximum number of newlines to send
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Waiting for pattern: {pattern}", color="yellow")
        
        while (time.time() - start_time) < timeout:
            # Check if data is available
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='replace')  # Increased buffer size
                buffer += chunk
                last_output_time = time.time()
                
                # Debug output for received chunks
                if self.debug and self.debug_callback and chunk.strip():
                    self.debug_callback(f"RECV: {chunk}", color="yellow")
                
                # Check if pattern is found
                if isinstance(pattern, str) and pattern in buffer:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Pattern found: {pattern}", color="green")
                    return buffer
                elif not isinstance(pattern, str) and re.search(pattern, buffer):
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Regex pattern found: {pattern}", color="green")
                    return buffer
            
            # If send_newline_after is set and we haven't received output for that duration,
            # send newlines periodically to help prompt a response
            if send_newline_after > 0 and (time.time() - last_output_time) > send_newline_after:
                # Only send a limited number of newlines
                if newlines_sent < max_newlines:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"No output received for {send_newline_after}s, sending newline ({newlines_sent+1}/{max_newlines})", color="yellow")
                    self.shell.send("\n")
                    newlines_sent += 1
                    last_output_time = time.time()  # Reset the timer
                    time.sleep(1)  # Wait a bit after sending newline
            
            # If we haven't received any output after half the timeout, try sending a newline once
            if not buffer and not newline_sent and (time.time() - start_time) > (timeout / 2):
                if self.debug and self.debug_callback:
                    self.debug_callback("No output received after half timeout, sending newline", color="yellow")
                self.shell.send("\n")
                newline_sent = True
                time.sleep(1)  # Wait a bit after sending newline
            
            time.sleep(0.1)
        
        # If we've gotten some output but not the exact pattern, try
        # checking for common shell prompts in case we missed the pattern
        if buffer:
            # Check for common command prompts that might indicate success
            if re.search(r'[\w\-\.]+[#>]\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found command prompt instead of exact pattern: {pattern}", color="yellow")
                return buffer
            
            # For enable mode check, consider hash prompt at the end as a success
            if pattern == r'#\s*$' and re.search(r'#\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found enable prompt (#) at the end of buffer", color="green")
                return buffer
        
        logger.error(f"Timeout waiting for pattern: {pattern}. Buffer: {buffer[:100]}...")
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Timeout waiting for pattern: {pattern}. Buffer received: {buffer}", color="red")
            
        return ""
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            timeout: Override the default timeout value.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            
            # Print command in debug mode
            if self.debug and self.debug_callback:
                self.debug_callback(f"SEND: {command}", color="yellow")
            
            # Clear any pending output before sending command
            if self.shell.recv_ready():
                self.shell.recv(4096)
                
            # Send the command
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Wait for command output and command prompt
            start_time = time.time()
            output = ""
            cmd_timeout = timeout or self.timeout
            prompt_found = False
            
            # Wait until we see a command prompt or timeout
            while (time.time() - start_time) < cmd_timeout and not prompt_found:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Debug output
                    if self.debug and self.debug_callback and chunk.strip():
                        self.debug_callback(f"RECV: {chunk}", color="yellow")
                    
                    # Check if we've reached the command prompt
                    if re.search(r'[\w\-\.]+[#>]\s*$', chunk.strip()) or re.search(r'[#>]\s*$', chunk.strip()):
                        prompt_found = True
                        break
                
                time.sleep(0.1)
            
            # If after timeout we haven't found a prompt, send a newline and try to get one
            if not prompt_found:
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected after command, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Try to get the final prompt
                if self.shell.recv_ready():
                    final_chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += final_chunk
            
            # Debug full output
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete command output: {output}", color="yellow")
            
            # Check for common errors in command output
            if 'Invalid input' in output or 'Error:' in output or 'Incomplete command' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            # Filter the command echo from output if present
            # This pattern looks for the command followed by a linebreak
            cmd_echo_pattern = f"^{command}\r\n"
            output = re.sub(cmd_echo_pattern, "", output, flags=re.MULTILINE)
            
            # Remove the prompt at the end
            output = re.sub(r'[\w\-\.]+[#>]\s*$', "", output)
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
            
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First ensure we're in enable mode
            if not self.connected:
                if not self.connect():
                    logger.error(f"Failed to connect to switch {self.ip}")
                    return False
            
            # Send the configure terminal command
            if self.debug and self.debug_callback:
                self.debug_callback("Entering configuration mode", color="yellow")
            
            success, output = self.run_command("configure terminal", wait_time=2.0)
            
            # Check if we're in config mode
            if not success or "Error" in output:
                logger.error(f"Failed to enter configuration mode: {output}")
                return False
            
            # Verify by looking for (config)# prompt in the next command output
            verify_success, verify_output = self.run_command("\n", wait_time=1.0)
            if "(config)" not in verify_output and not re.search(r'\(config\)[#>]', verify_output):
                logger.error(f"Failed to verify configuration mode: {verify_output}")
                return False
                
            logger.debug("Successfully entered configuration mode")
            return True
            
        except Exception as e:
            logger.error(f"Error entering configuration mode: {e}", exc_info=True)
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First send exit to leave config mode
            success, _ = self.run_command("exit", wait_time=1.0)
            
            if self.debug and self.debug_callback:
                self.debug_callback("Exiting configuration mode", color="yellow")
            
            # If requested, save configuration
            if save:
                save_success, save_output = self.run_command("write memory", wait_time=2.0)
                if not save_success:
                    logger.error(f"Failed to save configuration: {save_output}")
                    return False
                logger.info("Configuration saved with write memory")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting configuration mode: {e}", exc_info=True)
            return False
    
    def get_model(self) -> Optional[str]:
        """
        Get the switch model.
        
        Returns:
            Switch model string or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch model...", color="yellow")
            
        # First try with full show version
        success, output = self.run_command("show version")
        
        if success:
            # Look for HW line
            if self.debug and self.debug_callback:
                self.debug_callback(f"Got version output: {output[:200]}...", color="yellow")
                
            hw_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if hw_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {hw_match.group(1)}", color="green")
                return hw_match.group(1)
                
            # Look for ICX model in the output
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from regex: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # If we couldn't get it from show version, try more specific commands
        success, output = self.run_command("show version | include HW:")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"HW line output: {output}", color="yellow")
                
            # Parse output - should contain something like "HW: Stackable ICX8200-C08PF-POE"
            model_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # Try directly searching for ICX
        success, output = self.run_command("show version | include ICX")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"ICX line output: {output}", color="yellow")
                
            # Parse output - should contain something like "ICX6450-24" or "ICX7150-48P"
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from ICX line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch model", color="red")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get the switch serial number.
        
        Returns:
            Switch serial number or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch serial number...", color="yellow")
            
        # First try with full show version to avoid multiple commands
        if hasattr(self, '_version_output') and self._version_output:
            # Use cached output if available
            output = self._version_output
            if self.debug and self.debug_callback:
                self.debug_callback("Using cached version output", color="yellow")
        else:
            # Get full output
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
        
        if hasattr(self, '_version_output') and self._version_output:
            # Look for Serial in the full output
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from full output: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Try with specific grep for Serial (capital S)
        success, output = self.run_command("show version | include Serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"Serial line output: {output}", color="yellow")
                
            # Parse output - should contain something like "Serial  #:FNS4303U055"
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from Serial line: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Fallback to lowercase search
        success, output = self.run_command("show version | include serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"serial line output: {output}", color="yellow")
                
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from case-insensitive search: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # As a last resort, try getting full show version output without the pipe
        if not hasattr(self, '_version_output'):
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
                
                # Try to find serial
                serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
                if serial_match:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found serial from full version output: {serial_match.group(1)}", color="green")
                    return serial_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch serial number", color="red")
        return None

    # Add the methods required by ZTP process
    def apply_base_config(self, base_config: str) -> bool:
        """
        Apply base configuration to the switch.
        This should be done first before any port configuration.
        
        Args:
            base_config: Base configuration string to apply.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content preview: {base_config[:200]}...")  # Log first 200 chars
            if self.debug and self.debug_callback:
                self.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.exit_config_mode(save=False)
            return False

    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration after VLANs have been created.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.run_command("exit")  # Exit interface config
                    self.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False
            
    # Import discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.run_command("trace-l2 vlan 1")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.debug and self.debug_callback:
                                    self.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map, new_output.strip()):
                        channel.send("\n")
                        time.sleep(1)
                        
                        if channel.recv_ready():
                            verify_output = channel.recv(4096).decode('utf-8', errors='replace')
                            if not re.search(r'#\s*
            
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change prompt.
        
        Args:
            initial_output: Initial output from the shell.
            
        Returns:
            True if successfully handled password change, False otherwise.
        """
        try:
            # Print debug message
            if self.debug and self.debug_callback:
                self.debug_callback("First-time login detected, handling password change", color="yellow")
            
            # Check where we are in the password change process
            if "Enter the new password" not in initial_output:
                # Wait for the new password prompt
                self._wait_for_pattern("Enter the new password")
            
            # Send new password (using the preferred password)
            logger.debug(f"Sending new password: {self.preferred_password}")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending new password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for reconfirm prompt and send password again
            self._wait_for_pattern("Enter the reconfirm password")
            logger.debug("Sending reconfirm password")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending reconfirm password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for confirmation
            output = self._wait_for_pattern("Password modified successfully")
            if not output:
                logger.error("Password change failed")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Password change failed", color="red")
                    
                return False
                
            logger.info("Password changed successfully on first login")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Password changed successfully", color="green")
            
            # Wait for command prompt
            output = self._wait_for_pattern(r"[>#]")
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug("Entering enable mode after password change")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Entering enable mode after password change", color="yellow")
                
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    # After password change, we need to use the preferred password
                    if self.debug and self.debug_callback:
                        self.debug_callback("Sending preferred password for enable mode", color="yellow")
                        
                    self.shell.send(f"{self.preferred_password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error("Failed to enter enable mode after password change")
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback("Failed to enter enable mode after password change", color="red")
                        
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Successfully connected to switch {self.ip} after password change")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Successfully connected to switch {self.ip} after password change", color="green")
            
            # Disable pagination to avoid --More-- prompts
            success, output = self.run_command("skip-page-display")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Disabled pagination with skip-page-display", color="green")
            else:
                logger.warning("Failed to disable pagination with skip-page-display")
                
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Switch identified as {self.hostname}", color="yellow")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip} after password change")
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling first-time login: {e}", exc_info=True)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Error handling first-time login: {e}", color="red")
                
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
        
    def _wait_for_pattern(self, pattern: str, timeout: int = 30, send_newline_after: int = 0) -> str:
        """
        Wait for a specific pattern in the output.
        
        Args:
            pattern: Pattern to wait for (string or regex pattern).
            timeout: Timeout in seconds.
            send_newline_after: Send a newline after this many seconds if no output is received
                                (helps with some switches that need an initial prompt).
            
        Returns:
            Output received or empty string if timeout.
        """
        start_time = time.time()
        buffer = ""
        last_output_time = time.time()
        newline_sent = False
        newlines_sent = 0
        max_newlines = 3  # Maximum number of newlines to send
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Waiting for pattern: {pattern}", color="yellow")
        
        while (time.time() - start_time) < timeout:
            # Check if data is available
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='replace')  # Increased buffer size
                buffer += chunk
                last_output_time = time.time()
                
                # Debug output for received chunks
                if self.debug and self.debug_callback and chunk.strip():
                    self.debug_callback(f"RECV: {chunk}", color="yellow")
                
                # Check if pattern is found
                if isinstance(pattern, str) and pattern in buffer:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Pattern found: {pattern}", color="green")
                    return buffer
                elif not isinstance(pattern, str) and re.search(pattern, buffer):
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Regex pattern found: {pattern}", color="green")
                    return buffer
            
            # If send_newline_after is set and we haven't received output for that duration,
            # send newlines periodically to help prompt a response
            if send_newline_after > 0 and (time.time() - last_output_time) > send_newline_after:
                # Only send a limited number of newlines
                if newlines_sent < max_newlines:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"No output received for {send_newline_after}s, sending newline ({newlines_sent+1}/{max_newlines})", color="yellow")
                    self.shell.send("\n")
                    newlines_sent += 1
                    last_output_time = time.time()  # Reset the timer
                    time.sleep(1)  # Wait a bit after sending newline
            
            # If we haven't received any output after half the timeout, try sending a newline once
            if not buffer and not newline_sent and (time.time() - start_time) > (timeout / 2):
                if self.debug and self.debug_callback:
                    self.debug_callback("No output received after half timeout, sending newline", color="yellow")
                self.shell.send("\n")
                newline_sent = True
                time.sleep(1)  # Wait a bit after sending newline
            
            time.sleep(0.1)
        
        # If we've gotten some output but not the exact pattern, try
        # checking for common shell prompts in case we missed the pattern
        if buffer:
            # Check for common command prompts that might indicate success
            if re.search(r'[\w\-\.]+[#>]\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found command prompt instead of exact pattern: {pattern}", color="yellow")
                return buffer
            
            # For enable mode check, consider hash prompt at the end as a success
            if pattern == r'#\s*$' and re.search(r'#\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found enable prompt (#) at the end of buffer", color="green")
                return buffer
        
        logger.error(f"Timeout waiting for pattern: {pattern}. Buffer: {buffer[:100]}...")
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Timeout waiting for pattern: {pattern}. Buffer received: {buffer}", color="red")
            
        return ""
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            timeout: Override the default timeout value.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            
            # Print command in debug mode
            if self.debug and self.debug_callback:
                self.debug_callback(f"SEND: {command}", color="yellow")
            
            # Clear any pending output before sending command
            if self.shell.recv_ready():
                self.shell.recv(4096)
                
            # Send the command
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Wait for command output and command prompt
            start_time = time.time()
            output = ""
            cmd_timeout = timeout or self.timeout
            prompt_found = False
            
            # Wait until we see a command prompt or timeout
            while (time.time() - start_time) < cmd_timeout and not prompt_found:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Debug output
                    if self.debug and self.debug_callback and chunk.strip():
                        self.debug_callback(f"RECV: {chunk}", color="yellow")
                    
                    # Check if we've reached the command prompt
                    if re.search(r'[\w\-\.]+[#>]\s*$', chunk.strip()) or re.search(r'[#>]\s*$', chunk.strip()):
                        prompt_found = True
                        break
                
                time.sleep(0.1)
            
            # If after timeout we haven't found a prompt, send a newline and try to get one
            if not prompt_found:
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected after command, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Try to get the final prompt
                if self.shell.recv_ready():
                    final_chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += final_chunk
            
            # Debug full output
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete command output: {output}", color="yellow")
            
            # Check for common errors in command output
            if 'Invalid input' in output or 'Error:' in output or 'Incomplete command' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            # Filter the command echo from output if present
            # This pattern looks for the command followed by a linebreak
            cmd_echo_pattern = f"^{command}\r\n"
            output = re.sub(cmd_echo_pattern, "", output, flags=re.MULTILINE)
            
            # Remove the prompt at the end
            output = re.sub(r'[\w\-\.]+[#>]\s*$', "", output)
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
            
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First ensure we're in enable mode
            if not self.connected:
                if not self.connect():
                    logger.error(f"Failed to connect to switch {self.ip}")
                    return False
            
            # Send the configure terminal command
            if self.debug and self.debug_callback:
                self.debug_callback("Entering configuration mode", color="yellow")
            
            success, output = self.run_command("configure terminal", wait_time=2.0)
            
            # Check if we're in config mode
            if not success or "Error" in output:
                logger.error(f"Failed to enter configuration mode: {output}")
                return False
            
            # Verify by looking for (config)# prompt in the next command output
            verify_success, verify_output = self.run_command("\n", wait_time=1.0)
            if "(config)" not in verify_output and not re.search(r'\(config\)[#>]', verify_output):
                logger.error(f"Failed to verify configuration mode: {verify_output}")
                return False
                
            logger.debug("Successfully entered configuration mode")
            return True
            
        except Exception as e:
            logger.error(f"Error entering configuration mode: {e}", exc_info=True)
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First send exit to leave config mode
            success, _ = self.run_command("exit", wait_time=1.0)
            
            if self.debug and self.debug_callback:
                self.debug_callback("Exiting configuration mode", color="yellow")
            
            # If requested, save configuration
            if save:
                save_success, save_output = self.run_command("write memory", wait_time=2.0)
                if not save_success:
                    logger.error(f"Failed to save configuration: {save_output}")
                    return False
                logger.info("Configuration saved with write memory")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting configuration mode: {e}", exc_info=True)
            return False
    
    def get_model(self) -> Optional[str]:
        """
        Get the switch model.
        
        Returns:
            Switch model string or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch model...", color="yellow")
            
        # First try with full show version
        success, output = self.run_command("show version")
        
        if success:
            # Look for HW line
            if self.debug and self.debug_callback:
                self.debug_callback(f"Got version output: {output[:200]}...", color="yellow")
                
            hw_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if hw_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {hw_match.group(1)}", color="green")
                return hw_match.group(1)
                
            # Look for ICX model in the output
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from regex: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # If we couldn't get it from show version, try more specific commands
        success, output = self.run_command("show version | include HW:")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"HW line output: {output}", color="yellow")
                
            # Parse output - should contain something like "HW: Stackable ICX8200-C08PF-POE"
            model_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # Try directly searching for ICX
        success, output = self.run_command("show version | include ICX")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"ICX line output: {output}", color="yellow")
                
            # Parse output - should contain something like "ICX6450-24" or "ICX7150-48P"
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from ICX line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch model", color="red")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get the switch serial number.
        
        Returns:
            Switch serial number or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch serial number...", color="yellow")
            
        # First try with full show version to avoid multiple commands
        if hasattr(self, '_version_output') and self._version_output:
            # Use cached output if available
            output = self._version_output
            if self.debug and self.debug_callback:
                self.debug_callback("Using cached version output", color="yellow")
        else:
            # Get full output
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
        
        if hasattr(self, '_version_output') and self._version_output:
            # Look for Serial in the full output
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from full output: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Try with specific grep for Serial (capital S)
        success, output = self.run_command("show version | include Serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"Serial line output: {output}", color="yellow")
                
            # Parse output - should contain something like "Serial  #:FNS4303U055"
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from Serial line: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Fallback to lowercase search
        success, output = self.run_command("show version | include serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"serial line output: {output}", color="yellow")
                
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from case-insensitive search: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # As a last resort, try getting full show version output without the pipe
        if not hasattr(self, '_version_output'):
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
                
                # Try to find serial
                serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
                if serial_match:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found serial from full version output: {serial_match.group(1)}", color="green")
                    return serial_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch serial number", color="red")
        return None

    # Add the methods required by ZTP process
    def apply_base_config(self, base_config: str) -> bool:
        """
        Apply base configuration to the switch.
        This should be done first before any port configuration.
        
        Args:
            base_config: Base configuration string to apply.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content preview: {base_config[:200]}...")  # Log first 200 chars
            if self.debug and self.debug_callback:
                self.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.exit_config_mode(save=False)
            return False

    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration after VLANs have been created.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.run_command("exit")  # Exit interface config
                    self.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False
            
    # Import discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.run_command("trace-l2 vlan 1")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.debug and self.debug_callback:
                                    self.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map, verify_output.strip()):
                                self._debug_message(f"Failed to enter enable mode: {verify_output}", color="red")
                                self.disconnect()
                                return False
            
            self.connected = True
            logger.info(f"Connected to switch {self.ip}")
            
            # Disable pagination
            channel.send("skip-page-display\n")
            time.sleep(1)
            if channel.recv_ready():
                pagination_output = channel.recv(4096).decode('utf-8', errors='replace')
                if self.debug:
                    self._debug_message(f"After disabling pagination: {pagination_output}", color="yellow")
            
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                self._debug_message(f"Switch identified as {self.hostname}", color="green")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False
            
    def _handle_first_time_login(self, initial_output: str) -> bool:
        """
        Handle first-time login password change prompt.
        
        Args:
            initial_output: Initial output from the shell.
            
        Returns:
            True if successfully handled password change, False otherwise.
        """
        try:
            # Print debug message
            if self.debug and self.debug_callback:
                self.debug_callback("First-time login detected, handling password change", color="yellow")
            
            # Check where we are in the password change process
            if "Enter the new password" not in initial_output:
                # Wait for the new password prompt
                self._wait_for_pattern("Enter the new password")
            
            # Send new password (using the preferred password)
            logger.debug(f"Sending new password: {self.preferred_password}")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending new password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for reconfirm prompt and send password again
            self._wait_for_pattern("Enter the reconfirm password")
            logger.debug("Sending reconfirm password")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Sending reconfirm password", color="yellow")
                
            self.shell.send(f"{self.preferred_password}\n")
            time.sleep(1)
            
            # Wait for confirmation
            output = self._wait_for_pattern("Password modified successfully")
            if not output:
                logger.error("Password change failed")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Password change failed", color="red")
                    
                return False
                
            logger.info("Password changed successfully on first login")
            
            if self.debug and self.debug_callback:
                self.debug_callback("Password changed successfully", color="green")
            
            # Wait for command prompt
            output = self._wait_for_pattern(r"[>#]")
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug("Entering enable mode after password change")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Entering enable mode after password change", color="yellow")
                
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    # After password change, we need to use the preferred password
                    if self.debug and self.debug_callback:
                        self.debug_callback("Sending preferred password for enable mode", color="yellow")
                        
                    self.shell.send(f"{self.preferred_password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error("Failed to enter enable mode after password change")
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback("Failed to enter enable mode after password change", color="red")
                        
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Successfully connected to switch {self.ip} after password change")
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Successfully connected to switch {self.ip} after password change", color="green")
            
            # Disable pagination to avoid --More-- prompts
            success, output = self.run_command("skip-page-display")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Disabled pagination with skip-page-display", color="green")
            else:
                logger.warning("Failed to disable pagination with skip-page-display")
                
            # Get model and serial number
            self.model = self.get_model()
            self.serial = self.get_serial()
            
            if self.model and self.serial:
                # Update hostname property
                self.hostname = f"{self.model}-{self.serial}"
                logger.info(f"Identified switch {self.ip} as {self.hostname}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Switch identified as {self.hostname}", color="yellow")
            else:
                logger.warning(f"Could not get model and serial number for switch {self.ip} after password change")
                
            return True
            
        except Exception as e:
            logger.error(f"Error handling first-time login: {e}", exc_info=True)
            
            if self.debug and self.debug_callback:
                self.debug_callback(f"Error handling first-time login: {e}", color="red")
                
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
        
    def _wait_for_pattern(self, pattern: str, timeout: int = 30, send_newline_after: int = 0) -> str:
        """
        Wait for a specific pattern in the output.
        
        Args:
            pattern: Pattern to wait for (string or regex pattern).
            timeout: Timeout in seconds.
            send_newline_after: Send a newline after this many seconds if no output is received
                                (helps with some switches that need an initial prompt).
            
        Returns:
            Output received or empty string if timeout.
        """
        start_time = time.time()
        buffer = ""
        last_output_time = time.time()
        newline_sent = False
        newlines_sent = 0
        max_newlines = 3  # Maximum number of newlines to send
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Waiting for pattern: {pattern}", color="yellow")
        
        while (time.time() - start_time) < timeout:
            # Check if data is available
            if self.shell.recv_ready():
                chunk = self.shell.recv(4096).decode('utf-8', errors='replace')  # Increased buffer size
                buffer += chunk
                last_output_time = time.time()
                
                # Debug output for received chunks
                if self.debug and self.debug_callback and chunk.strip():
                    self.debug_callback(f"RECV: {chunk}", color="yellow")
                
                # Check if pattern is found
                if isinstance(pattern, str) and pattern in buffer:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Pattern found: {pattern}", color="green")
                    return buffer
                elif not isinstance(pattern, str) and re.search(pattern, buffer):
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Regex pattern found: {pattern}", color="green")
                    return buffer
            
            # If send_newline_after is set and we haven't received output for that duration,
            # send newlines periodically to help prompt a response
            if send_newline_after > 0 and (time.time() - last_output_time) > send_newline_after:
                # Only send a limited number of newlines
                if newlines_sent < max_newlines:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"No output received for {send_newline_after}s, sending newline ({newlines_sent+1}/{max_newlines})", color="yellow")
                    self.shell.send("\n")
                    newlines_sent += 1
                    last_output_time = time.time()  # Reset the timer
                    time.sleep(1)  # Wait a bit after sending newline
            
            # If we haven't received any output after half the timeout, try sending a newline once
            if not buffer and not newline_sent and (time.time() - start_time) > (timeout / 2):
                if self.debug and self.debug_callback:
                    self.debug_callback("No output received after half timeout, sending newline", color="yellow")
                self.shell.send("\n")
                newline_sent = True
                time.sleep(1)  # Wait a bit after sending newline
            
            time.sleep(0.1)
        
        # If we've gotten some output but not the exact pattern, try
        # checking for common shell prompts in case we missed the pattern
        if buffer:
            # Check for common command prompts that might indicate success
            if re.search(r'[\w\-\.]+[#>]\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found command prompt instead of exact pattern: {pattern}", color="yellow")
                return buffer
            
            # For enable mode check, consider hash prompt at the end as a success
            if pattern == r'#\s*$' and re.search(r'#\s*$', buffer.strip()):
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found enable prompt (#) at the end of buffer", color="green")
                return buffer
        
        logger.error(f"Timeout waiting for pattern: {pattern}. Buffer: {buffer[:100]}...")
        
        if self.debug and self.debug_callback:
            self.debug_callback(f"Timeout waiting for pattern: {pattern}. Buffer received: {buffer}", color="red")
            
        return ""
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            timeout: Override the default timeout value.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            
            # Print command in debug mode
            if self.debug and self.debug_callback:
                self.debug_callback(f"SEND: {command}", color="yellow")
            
            # Clear any pending output before sending command
            if self.shell.recv_ready():
                self.shell.recv(4096)
                
            # Send the command
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Wait for command output and command prompt
            start_time = time.time()
            output = ""
            cmd_timeout = timeout or self.timeout
            prompt_found = False
            
            # Wait until we see a command prompt or timeout
            while (time.time() - start_time) < cmd_timeout and not prompt_found:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Debug output
                    if self.debug and self.debug_callback and chunk.strip():
                        self.debug_callback(f"RECV: {chunk}", color="yellow")
                    
                    # Check if we've reached the command prompt
                    if re.search(r'[\w\-\.]+[#>]\s*$', chunk.strip()) or re.search(r'[#>]\s*$', chunk.strip()):
                        prompt_found = True
                        break
                
                time.sleep(0.1)
            
            # If after timeout we haven't found a prompt, send a newline and try to get one
            if not prompt_found:
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected after command, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Try to get the final prompt
                if self.shell.recv_ready():
                    final_chunk = self.shell.recv(4096).decode('utf-8', errors='replace')
                    output += final_chunk
            
            # Debug full output
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete command output: {output}", color="yellow")
            
            # Check for common errors in command output
            if 'Invalid input' in output or 'Error:' in output or 'Incomplete command' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            # Filter the command echo from output if present
            # This pattern looks for the command followed by a linebreak
            cmd_echo_pattern = f"^{command}\r\n"
            output = re.sub(cmd_echo_pattern, "", output, flags=re.MULTILINE)
            
            # Remove the prompt at the end
            output = re.sub(r'[\w\-\.]+[#>]\s*$', "", output)
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
            
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First ensure we're in enable mode
            if not self.connected:
                if not self.connect():
                    logger.error(f"Failed to connect to switch {self.ip}")
                    return False
            
            # Send the configure terminal command
            if self.debug and self.debug_callback:
                self.debug_callback("Entering configuration mode", color="yellow")
            
            success, output = self.run_command("configure terminal", wait_time=2.0)
            
            # Check if we're in config mode
            if not success or "Error" in output:
                logger.error(f"Failed to enter configuration mode: {output}")
                return False
            
            # Verify by looking for (config)# prompt in the next command output
            verify_success, verify_output = self.run_command("\n", wait_time=1.0)
            if "(config)" not in verify_output and not re.search(r'\(config\)[#>]', verify_output):
                logger.error(f"Failed to verify configuration mode: {verify_output}")
                return False
                
            logger.debug("Successfully entered configuration mode")
            return True
            
        except Exception as e:
            logger.error(f"Error entering configuration mode: {e}", exc_info=True)
            return False
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # First send exit to leave config mode
            success, _ = self.run_command("exit", wait_time=1.0)
            
            if self.debug and self.debug_callback:
                self.debug_callback("Exiting configuration mode", color="yellow")
            
            # If requested, save configuration
            if save:
                save_success, save_output = self.run_command("write memory", wait_time=2.0)
                if not save_success:
                    logger.error(f"Failed to save configuration: {save_output}")
                    return False
                logger.info("Configuration saved with write memory")
            
            return True
            
        except Exception as e:
            logger.error(f"Error exiting configuration mode: {e}", exc_info=True)
            return False
    
    def get_model(self) -> Optional[str]:
        """
        Get the switch model.
        
        Returns:
            Switch model string or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch model...", color="yellow")
            
        # First try with full show version
        success, output = self.run_command("show version")
        
        if success:
            # Look for HW line
            if self.debug and self.debug_callback:
                self.debug_callback(f"Got version output: {output[:200]}...", color="yellow")
                
            hw_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if hw_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {hw_match.group(1)}", color="green")
                return hw_match.group(1)
                
            # Look for ICX model in the output
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from regex: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # If we couldn't get it from show version, try more specific commands
        success, output = self.run_command("show version | include HW:")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"HW line output: {output}", color="yellow")
                
            # Parse output - should contain something like "HW: Stackable ICX8200-C08PF-POE"
            model_match = re.search(r'HW:\s+Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from HW line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        # Try directly searching for ICX
        success, output = self.run_command("show version | include ICX")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"ICX line output: {output}", color="yellow")
                
            # Parse output - should contain something like "ICX6450-24" or "ICX7150-48P"
            model_match = re.search(r'(ICX\d+[a-zA-Z0-9\-]+)', output)
            if model_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found model from ICX line: {model_match.group(1)}", color="green")
                return model_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch model", color="red")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get the switch serial number.
        
        Returns:
            Switch serial number or None if error.
        """
        if self.debug and self.debug_callback:
            self.debug_callback("Getting switch serial number...", color="yellow")
            
        # First try with full show version to avoid multiple commands
        if hasattr(self, '_version_output') and self._version_output:
            # Use cached output if available
            output = self._version_output
            if self.debug and self.debug_callback:
                self.debug_callback("Using cached version output", color="yellow")
        else:
            # Get full output
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
        
        if hasattr(self, '_version_output') and self._version_output:
            # Look for Serial in the full output
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from full output: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Try with specific grep for Serial (capital S)
        success, output = self.run_command("show version | include Serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"Serial line output: {output}", color="yellow")
                
            # Parse output - should contain something like "Serial  #:FNS4303U055"
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from Serial line: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # Fallback to lowercase search
        success, output = self.run_command("show version | include serial")
        
        if success and output:
            if self.debug and self.debug_callback:
                self.debug_callback(f"serial line output: {output}", color="yellow")
                
            serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
            if serial_match:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Found serial from case-insensitive search: {serial_match.group(1)}", color="green")
                return serial_match.group(1)
        
        # As a last resort, try getting full show version output without the pipe
        if not hasattr(self, '_version_output'):
            success, output = self.run_command("show version")
            if success:
                # Cache for future use
                self._version_output = output
                
                # Try to find serial
                serial_match = re.search(r'Serial\s*#:\s*([a-zA-Z0-9]+)', output, re.IGNORECASE)
                if serial_match:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found serial from full version output: {serial_match.group(1)}", color="green")
                    return serial_match.group(1)
        
        if self.debug and self.debug_callback:
            self.debug_callback("Could not determine switch serial number", color="red")
        return None

    # Add the methods required by ZTP process
    def apply_base_config(self, base_config: str) -> bool:
        """
        Apply base configuration to the switch.
        This should be done first before any port configuration.
        
        Args:
            base_config: Base configuration string to apply.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content preview: {base_config[:200]}...")  # Log first 200 chars
            if self.debug and self.debug_callback:
                self.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.exit_config_mode(save=False)
            return False

    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration after VLANs have been created.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.run_command("exit")  # Exit interface config
                    self.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.run_command("exit")
            
            # Exit global config and save
            if not self.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.run_command("exit")  # Try to exit interface config
            self.run_command("exit")  # Try to exit global config
            return False
            
    # Import discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.run_command("trace-l2 vlan 1")
            if success:
                if self.debug and self.debug_callback:
                    self.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.debug and self.debug_callback:
                                    self.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map