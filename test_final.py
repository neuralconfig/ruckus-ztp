#!/usr/bin/env python3
"""
Final test script for ZTP functionality.
"""
import os
import sys
import logging
import argparse
import time
import socket
import paramiko

# Set up more verbose logging for paramiko
logging.basicConfig(
    level=logging.DEBUG,  # Set root logger to DEBUG level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Configure paramiko to show full debug output
paramiko_logger = logging.getLogger('paramiko')
paramiko_logger.setLevel(logging.DEBUG)
if not paramiko_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    paramiko_logger.addHandler(handler)

# Create our own logger
logger = logging.getLogger('test_ztp')
logger.setLevel(logging.DEBUG)

def debug_callback(message, color="yellow"):
    """Debug callback function for switch commands"""
    color_codes = {'yellow': '33', 'green': '32', 'red': '31'}
    code = color_codes.get(color, '33')
    print(f"\033[{code}m{message}\033[0m")


def test_direct_connection(ip, username="super", default_password="sp-admin", preferred_password=None):
    """
    Test direct connection to switch using low-level Paramiko Transport API.
    First tries the default password, and if that fails, tries the preferred password.
    This handles cases where the password was already changed from default.
    """
    try:
        logger.info(f"Testing direct connection to {ip}")
        
        # Open socket first to test connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        logger.info(f"Connecting to {ip}:22...")
        sock.connect((ip, 22))
        logger.info(f"Socket connected to {ip}:22")
        
        # Initialize transport
        transport = paramiko.Transport(sock)
        transport.set_log_channel("paramiko")
        transport.window_size = 2097152  # 2MB window size
        
        logger.info(f"Starting client...")
        transport.start_client()
        logger.info(f"Client started, doing authentication...")
        
        # First try with default password
        password_used = None
        try:
            logger.info(f"Trying authentication with default password: {default_password}")
            transport.auth_password(username=username, password=default_password)
            logger.info(f"Authentication successful with default password")
            password_used = default_password
        except paramiko.ssh_exception.AuthenticationException as e:
            logger.info(f"Default password failed, trying preferred password: {preferred_password}")
            # If preferred password is available, try it
            if preferred_password and preferred_password != default_password:
                try:
                    transport.auth_password(username=username, password=preferred_password)
                    logger.info(f"Authentication successful with preferred password")
                    password_used = preferred_password
                except paramiko.ssh_exception.AuthenticationException:
                    logger.error("Both default and preferred passwords failed")
                    raise
            else:
                # No preferred password or same as default, just re-raise
                logger.error("Authentication failed and no alternative password available")
                raise
        
        # Open channel and get shell
        logger.info(f"Opening channel...")
        channel = transport.open_session()
        channel.set_combine_stderr(True)
        channel.get_pty()
        channel.invoke_shell()
        logger.info(f"Shell invoked")
        
        # Initial interaction
        logger.info(f"Reading initial output...")
        time.sleep(2)
        output = ""
        
        if channel.recv_ready():
            initial_output = channel.recv(4096).decode('utf-8', errors='replace')
            output += initial_output
            logger.info(f"Initial output: {initial_output}")
        
        # Check for first-time login prompt only if we used the default password
        if password_used == default_password and ("Please change the password" in output or "Enter the new password" in output):
            logger.info(f"Password change prompt detected")
            
            if preferred_password:
                logger.info(f"Sending new password: {preferred_password}")
                channel.send(f"{preferred_password}\n")
                time.sleep(2)
                
                if channel.recv_ready():
                    confirm_output = channel.recv(4096).decode('utf-8', errors='replace')
                    logger.info(f"After sending password: {confirm_output}")
                    
                    if "Enter the reconfirm password" in confirm_output:
                        logger.info(f"Sending reconfirm password")
                        channel.send(f"{preferred_password}\n")
                        time.sleep(2)
                        
                        if channel.recv_ready():
                            success_output = channel.recv(4096).decode('utf-8', errors='replace')
                            logger.info(f"After reconfirm: {success_output}")
        
        # Send a command to test the shell
        logger.info("Sending a test command (show version)...")
        channel.send("show version\n")
        time.sleep(2)
        
        if channel.recv_ready():
            cmd_output = channel.recv(4096).decode('utf-8', errors='replace')
            logger.info(f"Command output: {cmd_output}")
        
        # Close everything
        logger.info(f"Closing connection...")
        channel.close()
        transport.close()
        sock.close()
        
        return True, "Success"
    except Exception as e:
        logger.error(f"Error in direct connection test: {e}", exc_info=True)
        return False, str(e)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='ZTP Test Script')
    parser.add_argument('--config', default='test_config.ini',
                      help='Path to configuration file')
    parser.add_argument('--ip', required=True,
                      help='IP address of seed switch')
    parser.add_argument('--password', required=True,
                      help='Preferred password to set')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug mode')
    parser.add_argument('--direct-test', action='store_true',
                      help='Run direct SSH session test')
    
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_args()
    
    # Run the direct connection test if requested
    if args.direct_test:
        logger.info("Running direct connection test")
        success, message = test_direct_connection(args.ip, "super", "sp-admin", args.password)
        if success:
            logger.info("Direct connection test succeeded")
            return 0
        else:
            logger.error(f"Direct connection test failed: {message}")
            return 1
    
    # Otherwise, load ZTP modules and continue
    logger.info("Loading ZTP modules...")
    
    # Now we need to import our modules
    try:
        # Add parent directory to path if needed
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Import ZTP modules
        from ztp_agent.ztp.process import ZTPProcess
        from ztp_agent.ztp.config import load_config
        
        # Create the ztp_fix.py monkey patch module dynamically
        create_monkey_patch()
        
        # Now import our patch module
        from ztp_fix import patch_switch_operation
        
        logger.info("ZTP modules loaded successfully")
    except ImportError as e:
        logger.error(f"Failed to import ZTP modules: {e}")
        return 1
    
    # Apply our patch
    logger.info("Applying patch to SwitchOperation class")
    patch_switch_operation()
    
    # Load config
    config = load_config(args.config)
    
    # Always enable debug for troubleshooting
    config['debug'] = True
    config['debug_callback'] = debug_callback
    
    # Print key configuration
    logger.info(f"Base config file: {config['network'].get('base_config_file')}")
    logger.info(f"Management VLAN: {config['network'].get('management_vlan')}")
    logger.info(f"Wireless VLANs: {config['network'].get('wireless_vlans')}")
    logger.info(f"IP Pool: {config['network'].get('ip_pool')}")
    
    # Create and run ZTP process
    logger.info("Creating ZTP process")
    ztp_process = ZTPProcess(config)
    
    # Add seed switch with first-time login handling
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
        
        # Try with the preferred password directly
        logger.info(f"Trying to add switch with preferred password instead")
        success = ztp_process.add_switch(
            ip=args.ip,
            username="super",
            password=args.password,  # Try with preferred password directly
            debug=True,
            debug_callback=debug_callback
        )
        
        if not success:
            logger.error(f"Failed to add switch with both default and preferred passwords")
            return 1
        else:
            logger.info(f"Successfully added switch using preferred password")
    
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
                
                # If we have neighbors, show them
                if 'neighbors' in switch and switch['neighbors']:
                    logger.info(f"    Neighbors:")
                    for port, neighbor in switch['neighbors'].items():
                        if neighbor.get('type') == 'switch':
                            logger.info(f"      Port {port}: Switch {neighbor.get('system_name', 'unknown')}, "
                                      f"IP: {neighbor.get('mgmt_address', 'unknown')}")
                        elif neighbor.get('type') == 'ap':
                            logger.info(f"      Port {port}: AP {neighbor.get('system_name', 'unknown')}, "
                                      f"IP: {neighbor.get('mgmt_address', 'unknown')}")
            
            # Show details of each AP in inventory
            if ztp_process.inventory['aps']:
                logger.info("AP inventory details:")
                for ip, ap in ztp_process.inventory['aps'].items():
                    logger.info(f"  - {ip}: {ap.get('hostname', 'unknown')}, "
                               f"Status: {ap.get('status', 'unknown')}")
            
    except KeyboardInterrupt:
        logger.info("Stopping ZTP process...")
    finally:
        # Stop ZTP process
        ztp_process.stop()
        logger.info("ZTP process stopped")
    
    return 0


def create_monkey_patch():
    """Create the ztp_fix.py monkey patch module"""
    patch_code = """\"\"\"
Patch module for fixing SSH connection issues in SwitchOperation class.
This applies a monkey patch to the ZTP agent's SwitchOperation class
to improve the SSH connection handling.
\"\"\"
import logging
import time
import socket
import paramiko
import re
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

def patch_switch_operation():
    \"\"\"
    Apply monkey patch to the SwitchOperation class.
    This modifies the add_switch method in ZTPProcess to try both passwords.
    \"\"\"
    from ztp_agent.ztp.process import ZTPProcess
    
    # Store the original method for backup
    ZTPProcess._original_add_switch = ZTPProcess.add_switch
    
    # Replace the add_switch method with our improved version
    ZTPProcess.add_switch = improved_add_switch
    
    logger.info("Applied patch to ZTPProcess.add_switch method")
    
def improved_add_switch(self, ip: str, username: str, password: str, preferred_password: str = None, 
                       debug: bool = None, debug_callback = None) -> bool:
    \"\"\"
    Add a switch to the inventory with improved password handling.
    First tries with default password, if that fails, tries with preferred password.
    
    Args:
        ip: IP address of the switch.
        username: Username for switch access.
        password: Default password for switch access.
        preferred_password: Preferred password to try if default fails.
        debug: Whether to enable debug mode for this switch.
        debug_callback: Function to call with debug messages.
        
    Returns:
        True if successful, False otherwise.
    \"\"\"
    try:
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        # Validate IP
        import ipaddress
        ipaddress.IPv4Address(ip)
        
        # Use module-level debug settings if not provided
        if debug is None:
            debug = self.debug
        if debug_callback is None and self.debug_callback:
            debug_callback = self.debug_callback
        
        # First try with default password
        try:
            logger.info(f"Attempting to connect to {ip} with default password")
            
            # Create switch operation instance to test connection
            switch_op = SwitchOperation(
                ip=ip,
                username=username,
                password=password,
                timeout=30,
                preferred_password=preferred_password,
                debug=debug,
                debug_callback=debug_callback
            )
            
            # Test connection
            if not switch_op.connect():
                logger.error(f"Failed to connect to switch {ip} with default password")
                raise Exception("Connection failed with default password")
                
            # Connection succeeded with default password
            password_used = password
            logger.info(f"Successfully connected to {ip} with default password")
            
        except Exception as default_error:
            # If preferred password is available and different, try it
            if preferred_password and preferred_password != password:
                logger.info(f"Attempting to connect to {ip} with preferred password")
                try:
                    # Create new switch operation instance with preferred password
                    switch_op = SwitchOperation(
                        ip=ip,
                        username=username,
                        password=preferred_password,  # Use preferred as primary
                        timeout=30,
                        debug=debug,
                        debug_callback=debug_callback
                    )
                    
                    # Test connection
                    if not switch_op.connect():
                        logger.error(f"Failed to connect to switch {ip} with preferred password")
                        # Both passwords failed, re-raise original error
                        raise default_error
                        
                    # Connection succeeded with preferred password
                    password_used = preferred_password
                    logger.info(f"Successfully connected to {ip} with preferred password")
                    
                except Exception as preferred_error:
                    # Both passwords failed
                    logger.error(f"Failed to connect with both passwords: {preferred_error}")
                    return False
            else:
                # No alternative password available, just fail
                return False
        
        # Get model and serial number
        model = switch_op.model
        serial = switch_op.serial
        hostname = switch_op.hostname
        
        # Add to inventory
        self.inventory['switches'][ip] = {
            'ip': ip,
            'username': username,
            'password': password_used,  # Store whichever password worked
            'preferred_password': preferred_password,
            'model': model,
            'serial': serial,
            'hostname': hostname,
            'status': 'Connected',
            'configured': False,
            'base_config_applied': False,  # Track if base config has been applied
            'neighbors': {},
            'ports': {}
        }
        
        # Disconnect
        switch_op.disconnect()
        
        logger.info(f"Added switch {ip} to inventory (Model: {model}, Serial: {serial})")
        return True
    
    except ValueError:
        logger.error(f"Invalid IP address: {ip}")
        return False
    except paramiko.ssh_exception.AuthenticationException as e:
        logger.error(f"Authentication failed for switch {ip}: {e}")
        logger.error(f"Verify that the username '{username}' and password are correct.")
        return False
    except paramiko.ssh_exception.NoValidConnectionsError as e:
        logger.error(f"Connection error to switch {ip}: {e}")
        logger.error(f"Make sure SSH (port 22) is enabled and accessible on the switch.")
        return False
    except Exception as e:
        logger.error(f"Error adding switch {ip}: {e}", exc_info=True)
        return False
"""
    
    # Write the patch code to a file
    with open('ztp_fix.py', 'w') as f:
        f.write(patch_code)


if __name__ == "__main__":
    sys.exit(main())
