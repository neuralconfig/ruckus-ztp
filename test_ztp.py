#!/usr/bin/env python3
"""
Test script for ZTP functionality.
"""
import os
import sys
import logging
import argparse
import time
import socket
import paramiko

# Set up more verbose logging for paramiko
paramiko_logger = logging.getLogger("paramiko")
paramiko_logger.setLevel(logging.DEBUG)
paramiko_handler = logging.StreamHandler()
paramiko_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
paramiko_logger.addHandler(paramiko_handler)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our modules
from ztp_agent.ztp.process import ZTPProcess
from ztp_agent.ztp.config import load_config

# Set up SSH debugging
import logging
import paramiko

# Configure logging for paramiko
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set paramiko to debug level
paramiko_logger = logging.getLogger('paramiko')
paramiko_logger.setLevel(logging.DEBUG)

# Add handler if none exists
if not paramiko_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    paramiko_logger.addHandler(handler)

logger = logging.getLogger('test_ztp')
logger.setLevel(logging.DEBUG)


def debug_callback(message, color="yellow"):
    """Debug callback function for switch commands"""
    color_codes = {'yellow': '33', 'green': '32', 'red': '31'}
    code = color_codes.get(color, '33')
    print(f"\033[{code}m{message}\033[0m")


def test_ssh_connection(ip, default_password="sp-admin", preferred_password=None):
    """Test SSH connection to the switch"""
    logger.info(f"Testing SSH connection to {ip}")
    
    # Try with default password first
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        logger.info(f"Attempting connection with default password...")
        transport = paramiko.Transport((ip, 22))
        transport.set_log_channel("paramiko")
        transport.start_client()
        logger.debug("Transport started")
        
        # Use the standard password authentication method
        transport.auth_password(username="super", password=default_password)
        logger.debug("Authentication successful")
        
        # Start a session
        channel = transport.open_session()
        channel.set_combine_stderr(True)
        channel.get_pty()
        channel.invoke_shell()
        
        # Receive initial output
        time.sleep(2)
        output = ""
        if channel.recv_ready():
            output = channel.recv(4096).decode('utf-8', errors='replace')
            logger.debug(f"Initial output:\n{output}")
        
        # Send a newline to get a prompt
        channel.send("\n")
        time.sleep(1)
        if channel.recv_ready():
            new_output = channel.recv(4096).decode('utf-8', errors='replace')
            output += new_output
            logger.debug(f"After newline:\n{new_output}")
            
        # Check for password change prompt
        if "Please change the password" in output or "Enter the new password" in output:
            logger.info("Password change prompt detected")
            
            if preferred_password:
                logger.debug(f"Sending new password")
                channel.send(f"{preferred_password}\n")
                time.sleep(1)
                if channel.recv_ready():
                    new_output = channel.recv(4096).decode('utf-8', errors='replace')
                    output += new_output
                    logger.debug(f"After sending password:\n{new_output}")
                
                # Handle reconfirm prompt
                if "Enter the reconfirm password" in new_output:
                    logger.debug(f"Sending reconfirm password")
                    channel.send(f"{preferred_password}\n")
                    time.sleep(1)
                    if channel.recv_ready():
                        new_output = channel.recv(4096).decode('utf-8', errors='replace')
                        output += new_output
                        logger.debug(f"After sending reconfirm password:\n{new_output}")
        
        # Close connections
        channel.close()
        transport.close()
        
        logger.info(f"Successfully connected with default password")
        return True, "default"
    except paramiko.ssh_exception.AuthenticationException:
        logger.info(f"Authentication failed with default password")
    except Exception as e:
        logger.error(f"Connection error with default password: {e}")
        return False, str(e)
    
    # Try with preferred password if provided
    if preferred_password:
        try:
            logger.info(f"Attempting connection with preferred password...")
            client.connect(
                hostname=ip,
                username="super",
                password=preferred_password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            logger.info(f"Successfully connected with preferred password")
            client.close()
            return True, "preferred"
        except paramiko.ssh_exception.AuthenticationException:
            logger.info(f"Authentication failed with preferred password")
        except Exception as e:
            logger.error(f"Connection error with preferred password: {e}")
            return False, str(e)
    
    return False, "Authentication failed with all passwords"


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='ZTP Test Script')
    parser.add_argument('--config', default='~/.ztp_agent.cfg',
                      help='Path to configuration file')
    parser.add_argument('--ip', required=True,
                      help='IP address of seed switch')
    parser.add_argument('--password', required=True,
                      help='Preferred password to set')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug mode')
    parser.add_argument('--test-ssh', action='store_true',
                      help='Only test SSH connection')
    
    return parser.parse_args()


def main():
    """Main function"""
    args = parse_args()
    
    # If test-ssh flag is set, just test the SSH connection and exit
    if args.test_ssh:
        logger.info("Running SSH connection test only")
        success, result = test_ssh_connection(args.ip, "sp-admin", args.password)
        if success:
            logger.info(f"SSH connection test succeeded: {result}")
            return 0
        else:
            logger.error(f"SSH connection test failed: {result}")
            return 1
    
    # Load config
    config = load_config(args.config)
    
    # Set debug mode from arguments
    config['debug'] = True  # Always enable debug for troubleshooting
    config['debug_callback'] = debug_callback
    
    # Create ZTP process with enhanced debug
    logger.info("Creating ZTP process with detailed debugging")
    config['verbose_errors'] = True  # Request verbose error messages
    ztp_process = ZTPProcess(config)
    
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


if __name__ == "__main__":
    sys.exit(main())
