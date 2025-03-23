"""
Connection management module for interacting with RUCKUS ICX switches.
"""
import logging
import time
import paramiko
import re
from typing import Dict, List, Optional, Any, Tuple

from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

class SwitchOperation:
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
            # Create SSH client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Print debug message if debug mode is enabled
            if self.debug and self.debug_callback:
                self.debug_callback(f"Connecting to switch {self.ip} with username {self.username}", color="yellow")
            
            # Connect to switch
            logger.debug(f"Connecting to switch {self.ip}")
            
            # Try to connect with a retry for common connection issues
            connection_attempts = 0
            max_connection_attempts = 3  # Increased from 2 to 3
            connection_error = None
            
            # First try with default password, then with preferred if different
            passwords_to_try = [self.password]
            if self.preferred_password != self.password:
                passwords_to_try.append(self.preferred_password)
            
            # Authentication loop
            while connection_attempts < max_connection_attempts:
                # For each attempt, try all available passwords before moving to the next attempt
                for password_index, current_password in enumerate(passwords_to_try):
                    try:
                        connection_attempts += 1
                        password_desc = "default" if password_index == 0 else "preferred"
                        
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Trying {password_desc} password for {self.ip} (attempt {connection_attempts}/{max_connection_attempts})", 
                                              color="yellow")
                        
                        self.client.connect(
                            hostname=self.ip,
                            username=self.username,
                            password=current_password,
                            timeout=self.timeout,
                            allow_agent=False,  # Don't use SSH agent
                            look_for_keys=False  # Don't look for SSH keys
                        )
                        
                        # Remember which password worked
                        self.password = current_password
                        connection_error = None
                        
                        if password_index > 0:  # If using the preferred password
                            logger.info(f"Connected to {self.ip} using preferred password")
                            if self.debug and self.debug_callback:
                                self.debug_callback(f"Connected using preferred password", color="green")
                        
                        # Break out of the password loop on success
                        break
                        
                    except paramiko.ssh_exception.AuthenticationException as e:
                        connection_error = e
                        logger.warning(f"Authentication failed with {password_desc} password for {self.ip}: {e}")
                        
                        # If this is not the last password, continue to the next one
                        if password_index < len(passwords_to_try) - 1:
                            continue
                        
                        # If we've tried all passwords, log the failure
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Authentication failed with all passwords", color="red")
                        
                        # Close and recreate the client for next attempt
                        if self.client:
                            self.client.close()
                        self.client = paramiko.SSHClient()
                        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        time.sleep(1)
                        
                    except paramiko.ssh_exception.SSHException as e:
                        # Handle SSH-specific exceptions
                        connection_error = e
                        logger.warning(f"SSH connection issue to {self.ip}, attempt {connection_attempts}: {e}")
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"SSH connection issue: {e}, retrying...", color="yellow")
                        
                        # Close and recreate the client
                        if self.client:
                            self.client.close()
                        self.client = paramiko.SSHClient()
                        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        time.sleep(2)  # Wait before retry
                        break  # Break out of password loop, move to next attempt
                        
                    except TimeoutError as e:
                        # Handle timeout errors specifically
                        connection_error = e
                        logger.warning(f"Connection timeout to {self.ip}, attempt {connection_attempts}: {e}")
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Connection timeout: {e}, retrying...", color="yellow")
                        
                        # Close and recreate the client
                        if self.client:
                            self.client.close()
                        self.client = paramiko.SSHClient()
                        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                        time.sleep(3)  # Longer wait for timeouts
                        break  # Break out of password loop, move to next attempt
                        
                    except Exception as e:
                        # For other exceptions, don't retry
                        connection_error = e
                        logger.error(f"Connection error to {self.ip}: {e}")
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Connection error: {e}", color="red")
                        break  # Break out of password loop
                
                # If we successfully connected, break out of the attempt loop
                if connection_error is None:
                    break
                
                # If this is a non-authentication error, don't retry with different passwords
                if not isinstance(connection_error, paramiko.ssh_exception.AuthenticationException):
                    break
            
            # If we still have an error after retries, raise it
            if connection_error:
                raise connection_error
            
            # Get shell
            self.shell = self.client.invoke_shell()
            self.shell.settimeout(self.timeout)
            
            # Wait for prompt - use a longer initial wait time
            time.sleep(3)  # Increased from 2 to 3 seconds
            
            # Actively wait for output with timeout
            start_time = time.time()
            output = ""
            max_wait_time = 15  # Increased from 10 to 15 seconds
            
            while time.time() - start_time < max_wait_time:
                if self.shell.recv_ready():
                    chunk = self.shell.recv(10000).decode('utf-8', errors='replace')
                    output += chunk
                    
                    # Print debug output if debug mode is enabled
                    if chunk and self.debug and self.debug_callback:
                        self.debug_callback(f"Initial connection chunk: {chunk}", color="yellow")
                    
                    # If we see a prompt or login prompt, we can proceed
                    if re.search(r'[>#]', output) or "login:" in output or "Password:" in output:
                        break
                
                time.sleep(0.5)
            
            # If no output is received, try sending a newline
            if not output:
                if self.debug and self.debug_callback:
                    self.debug_callback("No initial output received, sending newline", color="yellow")
                self.shell.send("\n")
                time.sleep(2)
                
                # Try to get output again
                if self.shell.recv_ready():
                    chunk = self.shell.recv(10000).decode('utf-8', errors='replace')
                    output += chunk
            
            logger.debug(f"Initial output: {output}")
            
            # Print debug output if debug mode is enabled
            if self.debug and self.debug_callback:
                self.debug_callback(f"Complete initial connection output: {output}", color="yellow")
            
            # Check for first-time login password change prompt
            if "Please change the password" in output or "Enter the new password" in output:
                logger.info(f"First-time login detected for {self.ip}, handling password change")
                return self._handle_first_time_login(output)
                
            # Check if this is a login prompt
            if "login:" in output:
                if self.debug and self.debug_callback:
                    self.debug_callback(f"Detected login prompt, sending username: {self.username}", color="yellow")
                self.shell.send(f"{self.username}\n")
                time.sleep(1)
                
                # Wait for password prompt
                output = self._wait_for_pattern("Password:", timeout=8)  # Increased timeout
                if output:
                    if self.debug and self.debug_callback:
                        self.debug_callback(f"Detected password prompt, sending password", color="yellow")
                    self.shell.send(f"{self.password}\n")
                    time.sleep(1)
                    
                    # Wait for command prompt
                    output = self._wait_for_pattern(r'[>#]', timeout=8)  # Increased timeout
                    if not output:
                        logger.error(f"Did not receive prompt after sending password for switch {self.ip}")
                        self.disconnect()
                        return False
                else:
                    logger.error(f"Did not receive password prompt for switch {self.ip}")
                    self.disconnect()
                    return False
            
            # Check if we're at any command prompt (either exec '>' or enable '#')
            if not (re.search(r'[>#]', output) or re.search(r'\w+\s*[>#]', output)):
                # Try sending a newline in case we're at a prompt but didn't get it in the output
                if self.debug and self.debug_callback:
                    self.debug_callback("No prompt detected, sending newline to check", color="yellow")
                self.shell.send("\n")
                time.sleep(1)
                
                # Check if we got a prompt
                newline_output = ""
                if self.shell.recv_ready():
                    newline_output = self.shell.recv(1000).decode('utf-8', errors='replace')
                    output += newline_output
                
                if not (re.search(r'[>#]', output) or re.search(r'\w+\s*[>#]', output)):
                    logger.error(f"Did not receive prompt from switch {self.ip}. Output: {output}")
                    self.disconnect()
                    return False
            
            # Check if we're in exec mode (prompt ends with '>')
            is_exec_prompt = re.search(r'>\s*$', output.strip()) is not None
            is_enable_prompt = re.search(r'#\s*$', output.strip()) is not None
            
            # If we're in exec mode, enter enable mode
            if is_exec_prompt and not is_enable_prompt:
                logger.debug(f"In exec mode, entering enable mode on switch {self.ip}")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Detected exec mode (>), entering enable mode", color="yellow")
                
                # Send enable command
                self.shell.send("enable\n")
                time.sleep(1)
                
                # Wait for either password prompt or the enable mode prompt
                output = self._wait_for_pattern(r'(Password:|#\s*$)', timeout=8, send_newline_after=3)
                
                # If password is required
                if 'Password:' in output:
                    # Send password for enable
                    if self.debug and self.debug_callback:
                        self.debug_callback("Enable password required, sending password", color="yellow")
                    
                    self.shell.send(f"{self.password}\n")
                    time.sleep(1)
                    
                    # Wait for the enable mode prompt
                    output = self._wait_for_pattern(r'#\s*$', timeout=8)
                
                # Verify we're in enable mode
                if not re.search(r'#\s*$', output.strip()):
                    logger.error(f"Failed to enter enable mode on switch {self.ip}, output: {output}")
                    
                    # Try one more time with a simple verification
                    self.shell.send("\n")
                    time.sleep(1)
                    
                    # Check if just pressing Enter gives us a prompt
                    verify_output = ""
                    if self.shell.recv_ready():
                        verify_output = self.shell.recv(1000).decode('utf-8', errors='replace')
                    
                    # If still no enable prompt, disconnect
                    if not re.search(r'#\s*$', verify_output.strip()):
                        if self.debug and self.debug_callback:
                            self.debug_callback(f"Final verification failed, not in enable mode: {verify_output}", color="red")
                        self.disconnect()
                        return False
                    else:
                        logger.info(f"Verified we're in enable mode after retry")
                
                if self.debug and self.debug_callback:
                    self.debug_callback("Successfully entered enable mode", color="green")
            elif is_enable_prompt:
                logger.debug(f"Already in enable mode on switch {self.ip}")
            
            self.connected = True
            logger.info(f"Connected to switch {self.ip}")
            
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

    # Monkey patching other methods from submodules to this class
    from ztp_agent.network.switch.discovery import get_lldp_neighbors, get_l2_trace_data
    from ztp_agent.network.switch.configuration import (
        set_hostname, get_port_status, get_port_vlan, get_poe_status,
        change_port_vlan, set_port_status, set_poe_status,
        configure_switch_basic, configure_trunk_port, configure_ap_port
    )
    
    # Attach imported methods to the class
    get_lldp_neighbors = get_lldp_neighbors
    get_l2_trace_data = get_l2_trace_data
    set_hostname = set_hostname
    get_port_status = get_port_status
    get_port_vlan = get_port_vlan
    get_poe_status = get_poe_status
    change_port_vlan = change_port_vlan
    set_port_status = set_port_status
    set_poe_status = set_poe_status
    configure_switch_basic = configure_switch_basic
    configure_trunk_port = configure_trunk_port
    configure_ap_port = configure_ap_port