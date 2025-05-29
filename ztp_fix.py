"""
Patch module for fixing SSH connection issues in SwitchOperation class.
This applies a monkey patch to the ZTP agent's SwitchOperation class
to improve the SSH connection handling.
"""
import logging
import time
import socket
import paramiko
import re
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

def patch_switch_operation():
    """
    Apply monkey patch to the SwitchOperation class.
    This modifies the add_switch method in ZTPProcess to try both passwords.
    """
    from ztp_agent.ztp.process import ZTPProcess
    
    # Store the original method for backup
    ZTPProcess._original_add_switch = ZTPProcess.add_switch
    
    # Replace the add_switch method with our improved version
    ZTPProcess.add_switch = improved_add_switch
    
    logger.info("Applied patch to ZTPProcess.add_switch method")
    
def improved_add_switch(self, ip: str, username: str, password: str, preferred_password: str = None, 
                       debug: bool = None, debug_callback = None) -> bool:
    """
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
    """
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
