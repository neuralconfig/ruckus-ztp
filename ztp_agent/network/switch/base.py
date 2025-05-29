"""
Base module for switch connection management.
"""
import logging
import time
import paramiko
import re
from typing import Dict, List, Optional, Any, Tuple, Callable

# Set up logging
logger = logging.getLogger(__name__)

class SwitchConnection:
    """Base class for switch connections"""
    
    def __init__(self, 
                 ip: str, 
                 username: str, 
                 password: str, 
                 timeout: int = 30, 
                 preferred_password: str = None,
                 debug: bool = False,
                 debug_callback: Callable = None):
        """
        Initialize switch connection.
        
        Args:
            ip: IP address of the switch.
            username: Username for SSH connection.
            password: Password for SSH connection.
            timeout: Command timeout in seconds.
            preferred_password: Password to set during first-time login.
            debug: Whether to enable debug mode.
            debug_callback: Function to call with debug messages.
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.preferred_password = preferred_password or password
        self.timeout = timeout
        self.client = None
        self.shell = None
        self.connected = False
        self.debug = debug
        self.debug_callback = debug_callback
        self.hostname = f"switch-{ip.replace('.', '-')}"  # Default hostname
        self.model = None
        self.serial = None
        self._version_output = None  # Cache for version output
        
    def _debug_message(self, message: str, color: str = "yellow") -> None:
        """Helper method to print debug messages"""
        if self.debug and self.debug_callback:
            self.debug_callback(message, color=color)
    
    def connect(self) -> bool:
        """
        Connect to the switch.
        
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement connect()")
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        raise NotImplementedError("Subclasses must implement disconnect()")
    
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
        raise NotImplementedError("Subclasses must implement run_command()")
    
    def enter_config_mode(self) -> bool:
        """
        Enter configuration terminal mode.
        
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement enter_config_mode()")
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """
        Exit configuration terminal mode and optionally save the configuration.
        
        Args:
            save: Whether to save configuration with write memory command.
            
        Returns:
            True if successful, False otherwise.
        """
        raise NotImplementedError("Subclasses must implement exit_config_mode()")
