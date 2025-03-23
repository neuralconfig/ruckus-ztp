#!/usr/bin/env python3
"""
Simplified ZTP script that uses direct connection method known to work.
"""
import os
import sys
import logging
import argparse
import time
import socket
import paramiko
import re

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ztp_direct')

# Set up paramiko logging if needed
paramiko_logger = logging.getLogger('paramiko')
paramiko_logger.setLevel(logging.INFO)  # Set to DEBUG for more verbose SSH logging

# Print banner
print("=" * 80)
print("ZTP DIRECT CONFIGURATION SCRIPT")
print("=" * 80)
print("This script performs Zero Touch Provisioning (ZTP) for Ruckus ICX switches")
print("It will apply a base configuration and configure ports based on LLDP discovery")
print("=" * 80)

def debug_callback(message, color="yellow"):
    """Debug callback function for switch commands"""
    color_codes = {'yellow': '33', 'green': '32', 'red': '31', 'blue': '34'}
    code = color_codes.get(color, '33')
    print(f"\033[{code}m{message}\033[0m")
    # Also log the message
    logger.debug(message)

class DirectSwitchOperation:
    """Direct switch operation using low-level Paramiko Transport API"""
    
    def __init__(self, ip, username, password, preferred_password=None, timeout=30, debug=False, debug_callback=None):
        """Initialize the direct switch operation"""
        self.ip = ip
        self.username = username
        self.password = password
        self.preferred_password = preferred_password
        self.timeout = timeout
        self.debug = debug
        self.debug_callback = debug_callback
        self.transport = None
        self.channel = None
        self.connected = False
        self.model = None
        self.serial = None
        self.hostname = None
    
    def _debug_message(self, message, color="yellow"):
        """Print debug message"""
        if self.debug and self.debug_callback:
            self.debug_callback(message, color=color)
    
    def connect(self):
        """Connect to the switch"""
        if self.connected:
            self._debug_message(f"Already connected to switch {self.ip}", color="green")
            return True
        
        try:
            self._debug_message(f"====== CONNECTING TO SWITCH {self.ip} ======", color="blue")
            self._debug_message(f"Connection parameters:", color="blue")
            self._debug_message(f"   IP: {self.ip}", color="blue")
            self._debug_message(f"   Username: {self.username}", color="blue")
            self._debug_message(f"   Default Password: {'*' * len(self.password)}", color="blue")
            if self.preferred_password:
                self._debug_message(f"   Preferred Password: {'*' * len(self.preferred_password)}", color="blue")
            self._debug_message(f"   Timeout: {self.timeout} seconds", color="blue")
            
            # Open socket first to test connectivity
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            self._debug_message(f"Opening socket connection to {self.ip}:22", color="yellow")
            sock.connect((self.ip, 22))
            self._debug_message(f"Socket connected to {self.ip}:22", color="green")
            
            # Initialize transport
            self._debug_message(f"Initializing SSH transport", color="yellow")
            transport = paramiko.Transport(sock)
            transport.set_log_channel("paramiko")
            
            self._debug_message(f"Starting SSH client", color="yellow")
            transport.start_client()
            self._debug_message(f"Client started, performing authentication", color="yellow")
            
            # First try with default password
            password_used = None
            try:
                self._debug_message(f"Trying authentication with default password '{self.username}'", color="yellow")
                transport.auth_password(username=self.username, password=self.password)
                self._debug_message(f"Authentication successful with default password", color="green")
                password_used = self.password
            except paramiko.ssh_exception.AuthenticationException as e:
                self._debug_message(f"Default password failed: {str(e)}", color="red")
                # If preferred password is available, try it
                if self.preferred_password and self.preferred_password != self.password:
                    try:
                        self._debug_message(f"Trying with preferred password", color="yellow")
                        transport.auth_password(username=self.username, password=self.preferred_password)
                        self._debug_message(f"Authentication successful with preferred password", color="green")
                        password_used = self.preferred_password
                        # Update password to the one that worked
                        self.password = self.preferred_password
                    except paramiko.ssh_exception.AuthenticationException as e:
                        self._debug_message(f"Both passwords failed: {str(e)}", color="red")
                        raise
                else:
                    self._debug_message(f"No alternative password available", color="red")
                    raise
            
            # Open channel and get shell
            self._debug_message(f"Opening SSH channel", color="yellow")
            channel = transport.open_session()
            channel.set_combine_stderr(True)
            channel.get_pty()
            channel.invoke_shell()
            self._debug_message(f"Shell invoked successfully", color="green")
            
            # Save references
            self.transport = transport
            self.channel = channel
            
            # Initial interaction
            self._debug_message(f"Reading initial output from switch", color="yellow")
            time.sleep(2)  # Wait longer for initial output
            output = ""
            
            if channel.recv_ready():
                initial_output = channel.recv(4096).decode('utf-8', errors='replace')
                output += initial_output
                self._debug_message(f"Initial output from switch:\n{initial_output}", color="green")
            else:
                self._debug_message(f"No initial output received from switch", color="red")
            
            # Check for first-time login prompt
            if password_used == self.password and ("Please change the password" in output or "Enter the new password" in output):
                self._debug_message(f"Password change prompt detected - performing first-time login flow", color="yellow")
                return self._handle_first_time_login(output)
            
            # Send a newline to get a prompt
            self._debug_message(f"Sending newline to get prompt", color="yellow")
            channel.send("\n")
            time.sleep(2)  # Wait longer for response
            
            if channel.recv_ready():
                new_output = channel.recv(4096).decode('utf-8', errors='replace')
                output += new_output
                self._debug_message(f"Response after newline:\n{new_output}", color="green")
            else:
                self._debug_message(f"No response after sending newline", color="red")
            
            # Check for prompt
            if not re.search(r'[>#]', output):
                self._debug_message(f"No prompt found in output, sending another newline", color="red")
                channel.send("\n")
                time.sleep(2)
                
                if channel.recv_ready():
                    more_output = channel.recv(4096).decode('utf-8', errors='replace')
                    output += more_output
                    self._debug_message(f"Response after second newline:\n{more_output}", color="green")
                else:
                    self._debug_message(f"No response after second newline", color="red")
                
                if not re.search(r'[>#]', output):
                    self._debug_message(f"Still no prompt found, aborting connection", color="red")
                    return False
            
            # Enable mode if needed
            if '#' not in output:
                self._debug_message(f"Currently in user mode, entering enable mode", color="yellow")
                channel.send("enable\n")
                time.sleep(2)
                
                if channel.recv_ready():
                    enable_output = channel.recv(4096).decode('utf-8', errors='replace')
                    self._debug_message(f"Response after enable command:\n{enable_output}", color="green")
                    
                    if "Password:" in enable_output:
                        self._debug_message(f"Enable password required, sending password", color="yellow")
                        channel.send(f"{self.password}\n")
                        time.sleep(2)
                        
                        if channel.recv_ready():
                            pw_output = channel.recv(4096).decode('utf-8', errors='replace')
                            self._debug_message(f"Response after sending enable password:\n{pw_output}", color="green")
                        else:
                            self._debug_message(f"No response after sending enable password", color="red")
            
            # We're successfully connected
            self._debug_message(f"Successfully connected to switch {self.ip} with user {self.username}", color="green")
            self.connected = True
            
            # Turn off pagination
            self._debug_message(f"Disabling pagination with 'skip-page-display'", color="yellow")
            channel.send("skip-page-display\n")
            time.sleep(2)
            if channel.recv_ready():
                pagination_output = self.channel.recv(4096).decode('utf-8', errors='replace')
                self._debug_message(f"Response after disabling pagination:\n{pagination_output}", color="green")
            else:
                self._debug_message(f"No response after disabling pagination", color="red")
            
            # Get switch info
            self._debug_message(f"Getting switch information", color="yellow")
            self._get_switch_info()
            
            return True
        
        except Exception as e:
            error_msg = f"Error connecting to switch {self.ip}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._debug_message(error_msg, color="red")
            self.disconnect()
            return False
    
    def _handle_first_time_login(self, initial_output):
        """Handle first-time login password change prompt"""
        try:
            channel = self.channel
            
            # Send new password
            self._debug_message(f"Sending new password for first-time login", color="yellow")
            channel.send(f"{self.preferred_password}\n")
            time.sleep(2)
            
            # Check for reconfirm prompt
            confirmation_output = ""
            if channel.recv_ready():
                confirmation_output = channel.recv(4096).decode('utf-8', errors='replace')
                self._debug_message(f"After sending password: {confirmation_output}")
            
            # If we need to reconfirm, send it again
            if "Enter the reconfirm password" in confirmation_output:
                self._debug_message(f"Sending password confirmation", color="yellow")
                channel.send(f"{self.preferred_password}\n")
                time.sleep(2)
                
                if channel.recv_ready():
                    success_output = channel.recv(4096).decode('utf-8', errors='replace')
                    self._debug_message(f"Password change result: {success_output}")
                    
                    if "Password modified successfully" not in success_output:
                        self._debug_message(f"Password change failed", color="red")
                        return False
            
            # Update our stored password to the new one
            self.password = self.preferred_password
            
            # We should be connected now
            self.connected = True
            self._debug_message(f"Successfully changed password and connected", color="green")
            
            # Turn off pagination
            channel.send("skip-page-display\n")
            time.sleep(1)
            if channel.recv_ready():
                self.channel.recv(4096)
            
            # Get switch info
            self._get_switch_info()
            
            return True
            
        except Exception as e:
            logger.error(f"Error in first-time login: {e}", exc_info=True)
            self._debug_message(f"First-time login error: {e}", color="red")
            return False
    
    def _get_switch_info(self):
        """Get switch model, serial, and hostname"""
        try:
            if not self.connected:
                return False
            
            # Get version info
            self._debug_message(f"Getting switch information", color="yellow")
            self.channel.send("show version\n")
            time.sleep(2)
            
            version_output = ""
            if self.channel.recv_ready():
                version_output = self.channel.recv(4096).decode('utf-8', errors='replace')
            
            # Extract model
            model_match = re.search(r'HW: Stackable\s+(ICX\d+[a-zA-Z0-9\-]+(?:-POE)?)', version_output)
            if model_match:
                self.model = model_match.group(1)
                self._debug_message(f"Found model: {self.model}", color="green")
            
            # Extract serial
            serial_match = re.search(r'Serial\s+#:([a-zA-Z0-9]+)', version_output)
            if serial_match:
                self.serial = serial_match.group(1)
                self._debug_message(f"Found serial: {self.serial}", color="green")
            
            # Set hostname based on model and serial
            if self.model and self.serial:
                self.hostname = f"{self.model}-{self.serial}"
                self._debug_message(f"Set hostname: {self.hostname}", color="green")
            
            return True
        
        except Exception as e:
            logger.error(f"Error getting switch info: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the switch"""
        if self.channel:
            self.channel.close()
        
        if self.transport:
            self.transport.close()
        
        self.connected = False
        self._debug_message(f"Disconnected from switch {self.ip}", color="yellow")

class DirectZTPProcess:
    """Simplified ZTP process using direct connection"""
    
    def __init__(self, config):
        """Initialize the ZTP process"""
        self.config = config
        self.running = False
        self.thread = None
        self.inventory = {
            'switches': {},
            'aps': {}
        }
        
        # Get network configuration
        network_config = config.get('network', {})
        
        # Get base configuration
        self.base_config = network_config.get('base_config', '')
        
        # Get VLAN configurations
        self.mgmt_vlan = network_config.get('management_vlan', 10)
        self.wireless_vlans = network_config.get('wireless_vlans', [20, 30, 40])
        
        # Set up IP address management
        self.ip_pool = network_config.get('ip_pool', '192.168.10.0/24')
        self.gateway = network_config.get('gateway', '192.168.10.1')
        self.next_ip_index = 10  # Start assigning from .10
        
        # Debug settings
        self.debug = config.get('debug', False)
        self.debug_callback = config.get('debug_callback', None)
        
        logger.info("Initialized Direct ZTP process")
    
    def add_switch(self, ip, username, password, preferred_password=None, debug=None, debug_callback=None):
        """Add a switch to the inventory"""
        try:
            # Use module-level debug settings if not provided
            if debug is None:
                debug = self.debug
            if debug_callback is None and self.debug_callback:
                debug_callback = self.debug_callback
            
            # Create direct switch operation
            switch_op = DirectSwitchOperation(
                ip=ip,
                username=username,
                password=password,
                preferred_password=preferred_password,
                timeout=30,
                debug=debug,
                debug_callback=debug_callback
            )
            
            # Test connection
            if not switch_op.connect():
                logger.error(f"Failed to connect to switch {ip}")
                return False
            
            # Add to inventory
            self.inventory['switches'][ip] = {
                'ip': ip,
                'username': username,
                'password': switch_op.password,  # This will be updated if preferred password was used
                'model': switch_op.model,
                'serial': switch_op.serial,
                'hostname': switch_op.hostname,
                'status': 'Connected',
                'configured': False,
                'base_config_applied': False,
                'neighbors': {},
                'ports': {}
            }
            
            # Disconnect
            switch_op.disconnect()
            
            logger.info(f"Added switch {ip} to inventory")
            return True
            
        except Exception as e:
            logger.error(f"Error adding switch {ip}: {e}", exc_info=True)
            return False
    
    def start(self):
        """Start ZTP process"""
        if self.running:
            logger.warning("ZTP process already running")
            return False
        
        # Check if we have any switches
        if not self.inventory['switches']:
            logger.error("No switches configured, cannot start ZTP process")
            return False
        
        try:
            # Set running flag
            self.running = True
            
            # Start in a separate thread
            self.thread = threading.Thread(target=self._run_process)
            self.thread.daemon = True
            self.thread.start()
            
            logger.info("Started ZTP process")
            return True
            
        except Exception as e:
            logger.error(f"Error starting ZTP process: {e}", exc_info=True)
            self.running = False
            return False
    
    def stop(self):
        """Stop ZTP process"""
        if not self.running:
            logger.warning("ZTP process not running")
            return False
        
        try:
            # Set running flag to false
            self.running = False
            
            # Wait for thread to exit (with timeout)
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5.0)
            
            logger.info("Stopped ZTP process")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping ZTP process: {e}", exc_info=True)
            return False
    
    def get_status(self):
        """Get ZTP process status"""
        return {
            'running': self.running,
            'switches': len(self.inventory['switches']),
            'aps': len(self.inventory['aps']),
            'configured_switches': sum(1 for s in self.inventory['switches'].values() if s.get('configured', False)),
            'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _run_process(self):
        """Main ZTP process loop"""
        logger.info("ZTP process thread started")
        
        poll_interval = self.config.get('poll_interval', 60)  # seconds
        
        try:
            while self.running:
                try:
                    # Log that we're running
                    logger.info("ZTP process running...")
                    
                    # Process each unconfigured switch
                    for ip, switch in list(self.inventory['switches'].items()):
                        if not switch.get('configured', False):
                            self._configure_switch(ip, switch)
                    
                    # Check if all switches are configured
                    all_configured = all(s.get('configured', False) for s in self.inventory['switches'].values())
                    if all_configured and self.inventory['switches']:
                        logger.info("All switches have been configured. ZTP process complete.")
                        self.running = False
                        break
                    
                except Exception as e:
                    logger.error(f"Error in ZTP process loop: {e}", exc_info=True)
                
                # Sleep for the poll interval
                for _ in range(poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            
            logger.info("ZTP process thread exiting")
            
        except Exception as e:
            logger.error(f"Unhandled error in ZTP process thread: {e}", exc_info=True)
            self.running = False
    
    def _configure_switch(self, ip, switch_data):
        """Configure a single switch"""
        logger.info(f"Configuring switch {ip}...")
        
        try:
            # Connect to the switch
            switch_op = DirectSwitchOperation(
                ip=ip,
                username=switch_data['username'],
                password=switch_data['password'],
                timeout=30,
                debug=self.debug,
                debug_callback=self.debug_callback
            )
            
            if not switch_op.connect():
                logger.error(f"Failed to connect to switch {ip} for configuration")
                return False
            
            # Apply base configuration first if not already applied
            if not switch_data.get('base_config_applied', False):
                self._apply_base_configuration(switch_op)
                switch_data['base_config_applied'] = True
                
                # Save the configuration after applying base config
                self._save_configuration(switch_op)
            
            # Configure switch hostname and management
            self._configure_hostname_and_management(switch_op, switch_data)
            
            # Get and configure neighbors
            self._discover_and_configure_neighbors(switch_op, switch_data)
            
            # Save the final configuration
            self._save_configuration(switch_op)
            
            # Mark as configured
            switch_data['configured'] = True
            switch_data['status'] = 'Configured'
            logger.info(f"Switch {ip} configured successfully")
            
            # Disconnect
            switch_op.disconnect()
            
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch {ip}: {e}", exc_info=True)
            switch_data['status'] = f"Error: {str(e)}"
            return False
    
    def _apply_base_configuration(self, switch_op):
        """Apply base configuration to the switch"""
        logger.info(f"Applying base configuration to switch {switch_op.ip}...")
        
        try:
            # Get base configuration
            base_config = self.config.get('network', {}).get('base_config', '')
            if not base_config:
                logger.warning("Base configuration is empty")
                switch_op._debug_message("ERROR: Base configuration is empty!", color="red")
                return False
            
            # Log the full configuration we're about to apply
            if self.debug:
                switch_op._debug_message(f"Full base configuration to apply ({len(base_config)} bytes):", color="blue")
                for line in base_config.split("\n"):
                    if line.strip():
                        switch_op._debug_message(f"CONFIG: {line}", color="blue")
            
            # Split into lines and send each command
            commands = [line.strip() for line in base_config.split('\n') 
                      if line.strip() and not line.strip().startswith('!')]
            
            # Log count of commands
            logger.info(f"Applying {len(commands)} commands from base configuration")
            switch_op._debug_message(f"Applying {len(commands)} commands from base configuration", color="green")
            
            # Enter configuration mode first
            switch_op._debug_message("Entering configuration mode with 'configure terminal'", color="blue")
            switch_op.channel.send("configure terminal\n")
            time.sleep(2)  # Give it time to enter config mode
            
            if switch_op.channel.recv_ready():
                config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Response after entering config mode: {config_response}", color="green")
                
                if "error" in config_response.lower() or "invalid" in config_response.lower():
                    switch_op._debug_message(f"ERROR: Failed to enter configuration mode: {config_response}", color="red")
                    logger.error(f"Failed to enter configuration mode: {config_response}")
                    return False
            else:
                switch_op._debug_message("No response after entering configuration mode", color="red")
                logger.warning("No response after entering configuration mode")
            
            # Now apply each configuration command
            for i, cmd in enumerate(commands):
                logger.info(f"Sending command {i+1}/{len(commands)}: {cmd}")
                switch_op._debug_message(f"Sending command [{i+1}/{len(commands)}]: {cmd}", color="yellow")
                
                # Send the command
                switch_op.channel.send(f"{cmd}\n")
                time.sleep(1)  # Increased delay to ensure command is processed
                
                # Read response
                response = ""
                if switch_op.channel.recv_ready():
                    response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                    switch_op._debug_message(f"Response: {response}", color="green")
                    logger.debug(f"Response: {response}")
                else:
                    switch_op._debug_message("No response received", color="red")
                    logger.warning(f"No response received for command: {cmd}")
                
                # Check for error messages
                if "error" in response.lower() or "invalid" in response.lower():
                    switch_op._debug_message(f"WARNING: Possible error in response: {response}", color="red")
                    logger.warning(f"Possible error in response to command '{cmd}': {response}")
            
            # Exit configuration mode
            switch_op._debug_message("Exiting configuration mode", color="blue")
            switch_op.channel.send("end\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Response after exiting config mode: {exit_response}", color="green")
            
            logger.info(f"Base configuration applied to switch {switch_op.ip}")
            switch_op._debug_message(f"Base configuration applied to switch {switch_op.ip}", color="green")
            return True
            
        except Exception as e:
            error_msg = f"Error applying base configuration: {e}"
            logger.error(error_msg, exc_info=True)
            switch_op._debug_message(error_msg, color="red")
            return False
    
    def _configure_hostname_and_management(self, switch_op, switch_data):
        """Configure hostname and management IP"""
        logger.info(f"Configuring hostname and management for switch {switch_op.ip}...")
        
        try:
            # Enter configuration mode first
            switch_op._debug_message("Entering configuration mode for hostname and management setup", color="blue")
            switch_op.channel.send("configure terminal\n")
            time.sleep(2)
            
            if switch_op.channel.recv_ready():
                config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Response after entering config mode: {config_response}", color="green")
                
                if "error" in config_response.lower() or "invalid" in config_response.lower():
                    switch_op._debug_message(f"ERROR: Failed to enter configuration mode: {config_response}", color="red")
                    logger.error(f"Failed to enter configuration mode: {config_response}")
                    return False
            
            # Configure hostname if available
            if switch_data.get('hostname'):
                hostname = switch_data['hostname']
                logger.info(f"Setting hostname to {hostname}")
                switch_op._debug_message(f"Setting hostname to: {hostname}", color="yellow")
                
                # Send hostname command
                switch_op.channel.send(f"hostname {hostname}\n")
                time.sleep(1)
                if switch_op.channel.recv_ready():
                    hostname_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                    switch_op._debug_message(f"Hostname response: {hostname_response}", color="green")
            
            # Configure management IP in the management VLAN
            mgmt_vlan = self.config.get('network', {}).get('management_vlan', 10)
            
            # Assign an IP from the pool
            ip_pool = self.config.get('network', {}).get('ip_pool', '192.168.10.0/24')
            
            # For simplicity, we'll just use the existing IP address
            mgmt_ip = switch_op.ip
            gateway = self.config.get('network', {}).get('gateway', '192.168.10.1')
            
            # Configure the management interface
            logger.info(f"Configuring management interface with VLAN {mgmt_vlan}, IP {mgmt_ip}")
            switch_op._debug_message(f"Configuring management interface with VLAN {mgmt_vlan}, IP {mgmt_ip}", color="yellow")
            
            # Enter interface config for virtual interface
            switch_op.channel.send(f"interface ve {mgmt_vlan}\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Interface mode response: {interface_response}", color="green")
            
            # Configure IP address
            switch_op.channel.send(f"ip address {mgmt_ip} 255.255.255.0\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                ip_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"IP address response: {ip_response}", color="green")
            
            # Exit interface config
            switch_op.channel.send("exit\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit interface response: {exit_interface_response}", color="green")
            
            # Configure default gateway
            switch_op.channel.send(f"ip route 0.0.0.0 0.0.0.0 {gateway}\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                gateway_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Gateway config response: {gateway_response}", color="green")
            
            # Exit configuration mode
            switch_op._debug_message("Exiting configuration mode", color="blue")
            switch_op.channel.send("end\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit config mode response: {exit_response}", color="green")
            
            logger.info(f"Hostname and management configured for switch {switch_op.ip}")
            switch_op._debug_message(f"Hostname and management configured for switch {switch_op.ip}", color="green")
            return True
            
        except Exception as e:
            error_msg = f"Error configuring hostname and management: {e}"
            logger.error(error_msg, exc_info=True)
            switch_op._debug_message(error_msg, color="red")
            return False
    
    def _discover_and_configure_neighbors(self, switch_op, switch_data):
        """Discover and configure neighbor ports"""
        logger.info(f"Discovering neighbors for switch {switch_op.ip}...")
        switch_op._debug_message(f"Discovering neighbors for switch {switch_op.ip}...", color="blue")
        
        try:
            # Get LLDP neighbors
            switch_op._debug_message("Sending 'show lldp neighbors detail' command", color="yellow")
            switch_op.channel.send("show lldp neighbors detail\n")
            time.sleep(2)
            
            lldp_output = ""
            if switch_op.channel.recv_ready():
                lldp_output = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"LLDP neighbors output received ({len(lldp_output)} bytes)", color="green")
            else:
                switch_op._debug_message("No LLDP neighbors data received", color="red")
            
            # Log the LLDP output for debugging
            logger.debug(f"LLDP output: {lldp_output}")
            
            # Parse neighbors - very simplified for this script
            port_pattern = r'Local port: (\d+/\d+/\d+)'
            system_name_pattern = r'System name\s+: "([^"]+)"'
            port_desc_pattern = r'Port description\s+: "([^"]+)"'
            
            # Find all port entries
            port_matches = list(re.finditer(port_pattern, lldp_output))
            switch_op._debug_message(f"Found {len(port_matches)} neighbor ports in LLDP data", color="blue")
            
            wireless_vlans = self.config.get('network', {}).get('wireless_vlans', [20, 30, 40])
            wireless_vlans_str = ', '.join(str(v) for v in wireless_vlans)
            switch_op._debug_message(f"Wireless VLANs that will be configured: {wireless_vlans_str}", color="blue")
            
            # If no ports found, let the user know
            if not port_matches:
                switch_op._debug_message("No neighbor ports found in LLDP data. Nothing to configure.", color="yellow")
                logger.info("No neighbor ports found in LLDP data. Nothing to configure.")
            
            # Process each port
            for port_match in port_matches:
                port = port_match.group(1)
                
                # Try to find system name for this port section
                start_pos = port_match.start()
                end_pos = lldp_output.find("Local port:", start_pos + 1)
                if end_pos == -1:
                    end_pos = len(lldp_output)
                
                port_section = lldp_output[start_pos:end_pos]
                switch_op._debug_message(f"Parsing LLDP data for port {port}", color="yellow")
                
                # Try to find system name
                system_name_match = re.search(system_name_pattern, port_section)
                system_name = system_name_match.group(1) if system_name_match else "unknown"
                
                # Try to find port description
                port_desc_match = re.search(port_desc_pattern, port_section)
                port_desc = port_desc_match.group(1) if port_desc_match else ""
                
                switch_op._debug_message(f"Port {port} neighbor details:", color="yellow")
                switch_op._debug_message(f"  - System name: {system_name}", color="yellow")
                switch_op._debug_message(f"  - Port description: {port_desc}", color="yellow")
                
                # Determine device type based on name or description
                is_switch = "ICX" in system_name
                is_ap = "AP" in system_name or "ap" in port_desc.lower()
                
                # Configure the port based on device type
                if is_switch:
                    logger.info(f"Configuring switch-to-switch trunk port {port} for neighbor {system_name}")
                    switch_op._debug_message(f"Device is a switch - configuring port {port} as trunk", color="blue")
                    self._configure_switch_port(switch_op, port)
                elif is_ap:
                    logger.info(f"Configuring AP port {port} for neighbor {system_name}")
                    switch_op._debug_message(f"Device is an AP - configuring port {port} with wireless VLANs", color="blue")
                    self._configure_ap_port(switch_op, port, wireless_vlans)
                else:
                    logger.info(f"Unknown device type on port {port}: {system_name}, {port_desc}")
                    switch_op._debug_message(f"Unknown device type - skipping port {port}", color="red")
            
            logger.info(f"Neighbors discovered and configured for switch {switch_op.ip}")
            switch_op._debug_message(f"All neighbors discovered and configured for switch {switch_op.ip}", color="green")
            return True
            
        except Exception as e:
            error_msg = f"Error discovering and configuring neighbors: {e}"
            logger.error(error_msg, exc_info=True)
            switch_op._debug_message(error_msg, color="red")
            return False
    
    def _configure_switch_port(self, switch_op, port):
        """Configure a switch-to-switch trunk port"""
        try:
            # Enter configuration mode first
            switch_op._debug_message(f"Entering configuration mode to configure switch port {port}", color="blue")
            switch_op.channel.send("configure terminal\n")
            time.sleep(1)
            
            if switch_op.channel.recv_ready():
                config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Config mode response: {config_response}", color="green")
            
            # Enter interface config
            switch_op._debug_message(f"Configuring switch-to-switch trunk port {port}", color="yellow")
            switch_op.channel.send(f"interface ethernet {port}\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Interface mode response: {interface_response}", color="green")
            
            # Configure as trunk port with all VLANs
            switch_op._debug_message(f"Setting port {port} as trunk with all tagged VLANs", color="yellow")
            switch_op.channel.send("vlan-config add all-tagged\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                trunk_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Trunk config response: {trunk_response}", color="green")
            
            # Set spanning tree port fast
            switch_op._debug_message(f"Enabling spanning-tree edge port", color="yellow")
            switch_op.channel.send("spanning-tree 802-1w admin-edge-port\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                stp_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Spanning tree response: {stp_response}", color="green")
            
            # Exit interface config
            switch_op._debug_message(f"Exiting interface configuration", color="yellow")
            switch_op.channel.send("exit\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit interface response: {exit_interface_response}", color="green")
            
            # Exit configuration mode
            switch_op._debug_message(f"Exiting configuration mode", color="blue")
            switch_op.channel.send("end\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit config mode response: {exit_config_response}", color="green")
            
            logger.info(f"Switch port {port} configured as trunk")
            switch_op._debug_message(f"Switch port {port} successfully configured as trunk", color="green")
            return True
            
        except Exception as e:
            error_msg = f"Error configuring switch port {port}: {e}"
            logger.error(error_msg)
            switch_op._debug_message(error_msg, color="red")
            return False
    
    def _configure_ap_port(self, switch_op, port, wireless_vlans):
        """Configure a switch-to-AP port"""
        try:
            # Enter configuration mode first
            switch_op._debug_message(f"Entering configuration mode to configure AP port {port}", color="blue")
            switch_op.channel.send("configure terminal\n")
            time.sleep(1)
            
            if switch_op.channel.recv_ready():
                config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Config mode response: {config_response}", color="green")
            
            # Enter interface config
            switch_op._debug_message(f"Configuring switch-to-AP port {port}", color="yellow")
            switch_op.channel.send(f"interface ethernet {port}\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Interface mode response: {interface_response}", color="green")
            
            # Configure management VLAN as untagged
            mgmt_vlan = self.config.get('network', {}).get('management_vlan', 10)
            switch_op._debug_message(f"Setting VLAN {mgmt_vlan} as untagged (native) VLAN", color="yellow")
            switch_op.channel.send(f"vlan-config add untagged-vlan {mgmt_vlan}\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                mgmt_vlan_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Management VLAN response: {mgmt_vlan_response}", color="green")
            
            # Configure wireless VLANs as tagged
            switch_op._debug_message(f"Adding wireless VLANs {wireless_vlans} as tagged", color="yellow")
            for vlan in wireless_vlans:
                switch_op.channel.send(f"vlan-config add tagged-vlan {vlan}\n")
                time.sleep(1)
                if switch_op.channel.recv_ready():
                    vlan_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                    switch_op._debug_message(f"VLAN {vlan} response: {vlan_response}", color="green")
            
            # Set spanning tree port fast
            switch_op._debug_message(f"Enabling spanning-tree edge port", color="yellow")
            switch_op.channel.send("spanning-tree 802-1w admin-edge-port\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                stp_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Spanning tree response: {stp_response}", color="green")
            
            # Exit interface config
            switch_op._debug_message(f"Exiting interface configuration", color="yellow")
            switch_op.channel.send("exit\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_interface_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit interface response: {exit_interface_response}", color="green")
            
            # Exit configuration mode
            switch_op._debug_message(f"Exiting configuration mode", color="blue")
            switch_op.channel.send("end\n")
            time.sleep(1)
            if switch_op.channel.recv_ready():
                exit_config_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Exit config mode response: {exit_config_response}", color="green")
            
            logger.info(f"AP port {port} configured with management VLAN {mgmt_vlan} and wireless VLANs {wireless_vlans}")
            switch_op._debug_message(f"AP port {port} successfully configured with VLANs", color="green")
            return True
            
        except Exception as e:
            error_msg = f"Error configuring AP port {port}: {e}"
            logger.error(error_msg)
            switch_op._debug_message(error_msg, color="red")
            return False
    
    def _save_configuration(self, switch_op):
        """Save the switch configuration"""
        try:
            # Send write memory command
            switch_op._debug_message("Saving configuration with 'write memory' command", color="blue")
            switch_op.channel.send("write memory\n")
            time.sleep(3)  # Wait longer for write memory to complete
            
            if switch_op.channel.recv_ready():
                response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                switch_op._debug_message(f"Write memory response: {response}", color="green")
                
                if "done" in response.lower() or "written to flash" in response.lower():
                    logger.info(f"Configuration saved for switch {switch_op.ip}")
                    switch_op._debug_message("Configuration successfully saved to flash", color="green")
                    return True
                else:
                    warning_msg = f"Unexpected response when saving configuration: {response}"
                    logger.warning(warning_msg)
                    switch_op._debug_message(warning_msg, color="red")
                    
                    # Try again with 'wr mem' (shorter form)
                    switch_op._debug_message("Trying again with 'wr mem' command", color="yellow")
                    switch_op.channel.send("wr mem\n")
                    time.sleep(3)
                    
                    if switch_op.channel.recv_ready():
                        retry_response = switch_op.channel.recv(4096).decode('utf-8', errors='replace')
                        switch_op._debug_message(f"Second write memory response: {retry_response}", color="green")
                        
                        if "done" in retry_response.lower() or "written to flash" in retry_response.lower():
                            logger.info(f"Configuration saved for switch {switch_op.ip} on second attempt")
                            switch_op._debug_message("Configuration successfully saved to flash on second attempt", color="green")
                            return True
                    
                    # If still not successful, just report it but continue
                    switch_op._debug_message("Warning: Could not confirm configuration was saved", color="red")
                    return False
            else:
                switch_op._debug_message("No response received after write memory command", color="red")
            
            # Assume it worked even if we didn't get a confirmation
            logger.info(f"Configuration assumed saved for switch {switch_op.ip} (no response)")
            return True
            
        except Exception as e:
            error_msg = f"Error saving configuration: {e}"
            logger.error(error_msg)
            switch_op._debug_message(error_msg, color="red")
            return False

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Direct ZTP Script')
    parser.add_argument('--config', default='test_config.ini',
                      help='Path to configuration file')
    parser.add_argument('--ip', required=True,
                      help='IP address of seed switch')
    parser.add_argument('--password', required=True,
                      help='Preferred password to set')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug mode')
    
    return parser.parse_args()

def load_config(config_path):
    """Load configuration from file"""
    import configparser
    import os
    
    # Default configuration
    config = {
        'ztp': {
            'poll_interval': 60,
        },
        'network': {
            'base_config_file': 'config/base_configuration.txt',
            'base_config': '',  # Will be populated from the file
            'management_vlan': 10,
            'wireless_vlans': [20, 30, 40],
            'ip_pool': '192.168.10.0/24',
            'gateway': '192.168.10.1',
        },
        'debug': False
    }
    
    # Expand path
    config_path = os.path.expanduser(config_path)
    
    # If config file exists, load it
    if os.path.exists(config_path):
        try:
            parser = configparser.ConfigParser()
            parser.read(config_path)
            
            # Parse each section
            for section in parser.sections():
                if section not in config:
                    config[section] = {}
                
                for key, value in parser[section].items():
                    # Handle special cases
                    if section == 'network' and key == 'wireless_vlans':
                        config[section]['wireless_vlans'] = [int(v.strip()) for v in value.split(',')]
                    elif section == 'network' and key == 'management_vlan':
                        config[section]['management_vlan'] = int(value)
                    else:
                        # Try to convert to int if possible
                        try:
                            config[section][key] = int(value)
                        except ValueError:
                            config[section][key] = value
            
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default configuration")
    else:
        logger.warning(f"Configuration file {config_path} not found, using default configuration")
    
    # Regardless of whether the config file loaded successfully, try to load the base configuration
    # This is separate to ensure we always try to load the base config
    try:
        # Get base configuration file path from config
        base_config_file = config['network'].get('base_config_file', 'config/base_configuration.txt')
        
        # Try several paths to find the base configuration file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.dirname(os.path.abspath(config_path)) if os.path.exists(config_path) else script_dir
        
        possible_paths = [
            os.path.join(os.getcwd(), base_config_file),  # Current working directory
            os.path.join(os.getcwd(), "config", "base_configuration.txt"),  # Explicit path from CWD
            os.path.join(script_dir, base_config_file),  # Relative to script
            os.path.join(config_dir, base_config_file),  # Relative to config file
            os.path.join(script_dir, "config", "base_configuration.txt"),  # Explicit from script dir
            os.path.abspath(base_config_file),  # Absolute path
            os.path.expanduser(base_config_file),  # Expanded user path
            base_config_file,  # As provided
        ]
        
        # Debug: print out the current working directory and script directory
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Script directory: {script_dir}")
        logger.info(f"Config directory: {config_dir}")
        
        # Try each path until we find the file
        base_config_found = False
        for path in possible_paths:
            logger.info(f"Trying to load base configuration from: {path}")
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        base_config_content = f.read()
                    
                    # Verify the content is not empty
                    if base_config_content.strip():
                        config['network']['base_config'] = base_config_content
                        logger.info(f"Successfully loaded base configuration from {path} ({len(base_config_content)} bytes)")
                        
                        # Print the first few lines of the config for debugging
                        lines = base_config_content.split('\n')
                        preview = '\n'.join(lines[:min(5, len(lines))])
                        logger.info(f"Base config preview:\n{preview}")
                        
                        base_config_found = True
                        break
                    else:
                        logger.warning(f"Base configuration file at {path} is empty")
                except Exception as e:
                    logger.warning(f"Failed to read base configuration from {path}: {e}")
        
        if not base_config_found:
            # Emergency fallback: hardcode a minimal base configuration
            logger.warning("Could not find base configuration file. Using hardcoded minimal configuration.")
            minimal_config = """! Hardcoded minimal configuration
vlan 10 name Management
spanning-tree 802-1w
exit

vlan 20 name Wireless-20
spanning-tree 802-1w
exit

vlan 30 name Wireless-30
spanning-tree 802-1w
exit

vlan 40 name Wireless-40
spanning-tree 802-1w
exit"""
            config['network']['base_config'] = minimal_config
            logger.info("Using hardcoded minimal base configuration as fallback")
    
    except Exception as e:
        logger.error(f"Error loading base configuration: {e}", exc_info=True)
        # Emergency fallback if everything fails
        config['network']['base_config'] = "! Minimal fallback config\nvlan 10 name Management\nspanning-tree 802-1w\nexit"
        logger.warning("Using emergency minimal fallback configuration")
    
    return config

def main():
    """Main function"""
    # Parse command line arguments
    args = parse_args()
    
    # Print debug banner if debug mode is enabled
    if args.debug:
        print("\n" + "=" * 80)
        print("RUNNING IN DEBUG MODE")
        print("All SSH traffic and configuration details will be displayed")
        print("=" * 80 + "\n")
    
    # Load configuration
    config = load_config(args.config)
    
    # Set debug mode
    config['debug'] = args.debug or True  # Always enable debug for testing
    config['debug_callback'] = debug_callback
    
    # Print configuration details
    print("\n" + "=" * 60)
    print(f"CONFIGURATION DETAILS")
    print("=" * 60)
    print(f"Config file: {args.config}")
    print(f"Switch IP: {args.ip}")
    print(f"Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    print(f"Base config file: {config['network'].get('base_config_file')}")
    print(f"Management VLAN: {config['network'].get('management_vlan')}")
    print(f"Wireless VLANs: {config['network'].get('wireless_vlans')}")
    print(f"IP Pool: {config['network'].get('ip_pool')}")
    print(f"Gateway: {config['network'].get('gateway')}")
    print("=" * 60 + "\n")
    
    # Log the same information
    logger.info(f"Config file: {args.config}")
    logger.info(f"Switch IP: {args.ip}")
    logger.info(f"Debug mode: {'Enabled' if args.debug else 'Disabled'}")
    logger.info(f"Base config file: {config['network'].get('base_config_file')}")
    logger.info(f"Management VLAN: {config['network'].get('management_vlan')}")
    logger.info(f"Wireless VLANs: {config['network'].get('wireless_vlans')}")
    logger.info(f"IP Pool: {config['network'].get('ip_pool')}")
    logger.info(f"Gateway: {config['network'].get('gateway')}")
    
    # Print the base config that was loaded
    base_config = config['network'].get('base_config', '')
    if base_config:
        print("\n" + "=" * 60)
        print(f"BASE CONFIGURATION LOADED SUCCESSFULLY ({len(base_config.strip())} bytes)")
        print("=" * 60)
        print("Preview of first 5 lines:")
        lines = [line for line in base_config.split("\n") if line.strip()][:5]
        for line in lines:
            print(f"  {line}")
        print("=" * 60 + "\n")
        
        logger.info(f"Base configuration loaded successfully ({len(base_config.strip())} bytes)")
    else:
        print("\n" + "=" * 60)
        print("ERROR: NO BASE CONFIGURATION WAS LOADED!")
        print("This will cause the ZTP process to fail.")
        print("=" * 60 + "\n")
        
        logger.error("No base configuration was loaded - this will cause the ZTP process to fail!")
    
    # Create ZTP process
    ztp_process = DirectZTPProcess(config)
    
    # Add seed switch
    logger.info(f"Adding seed switch {args.ip}")
    success = ztp_process.add_switch(
        ip=args.ip,
        username="super",  # Always use 'super' for RUCKUS ICX switches
        password="sp-admin",  # Use the default password for first login
        preferred_password=args.password,  # Password to change to
        debug=True,
        debug_callback=debug_callback
    )
    
    if not success:
        logger.error(f"Failed to add switch {args.ip}")
        return 1
    
    # Start ZTP process
    logger.info("Starting ZTP process")
    success = ztp_process.start()
    
    if not success:
        logger.error("Failed to start ZTP process")
        return 1
    
    # Run for a while
    try:
        logger.info("ZTP process running... Press Ctrl+C to stop")
        run_count = 0
        max_run_time = 600  # 10 minutes max
        
        while run_count < max_run_time:
            time.sleep(10)  # Status update every 10 seconds
            run_count += 10
            
            # Print status
            status = ztp_process.get_status()
            logger.info(f"Status: {status}")
            
            # Print current inventory
            switches_count = len(ztp_process.inventory['switches'])
            aps_count = len(ztp_process.inventory['aps'])
            configured_switches = sum(1 for s in ztp_process.inventory['switches'].values() 
                                    if s.get('configured', False))
            
            logger.info(f"Inventory: {switches_count} switches ({configured_switches} configured), {aps_count} APs")
            
            # Show details of each switch in inventory
            logger.info("Switch inventory details:")
            for ip, switch in ztp_process.inventory['switches'].items():
                logger.info(f"  - {ip}: {switch.get('hostname', 'unknown')}, "
                           f"Model: {switch.get('model', 'unknown')}, "
                           f"Status: {switch.get('status', 'unknown')}")
            
    except KeyboardInterrupt:
        logger.info("Stopping ZTP process...")
    finally:
        # Stop ZTP process
        ztp_process.stop()
        logger.info("ZTP process stopped")
    
    return 0

# Import threading at module level
import threading

if __name__ == "__main__":
    sys.exit(main())
