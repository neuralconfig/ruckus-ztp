"""
Facade class to maintain backward compatibility with existing code.
"""
import logging
from typing import Dict, List, Optional, Any, Tuple

from ztp_agent.network.switch.base import SwitchConnection
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

class SwitchOperation:
    """
    Facade class that provides the original SwitchOperation interface
    but delegates to the new modular implementation.
    """
    
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
        # Create the base connection
        self.connection = SwitchConnection(
            ip=ip,
            username=username,
            password=password,
            timeout=timeout,
            preferred_password=preferred_password,
            debug=debug,
            debug_callback=debug_callback
        )
        
        # Add property forwarding
        self.ip = self.connection.ip
        self.username = self.connection.username
        self.password = self.connection.password
        self.preferred_password = self.connection.preferred_password
        self.timeout = self.connection.timeout
        self.debug = self.connection.debug
        self.debug_callback = self.connection.debug_callback
        self.hostname = self.connection.hostname
        self.model = self.connection.model
        self.serial = self.connection.serial
    
    # Forward basic connection methods
    def connect(self) -> bool:
        """Forward to connection.connect()"""
        return self.connection.connect()
    
    def disconnect(self) -> None:
        """Forward to connection.disconnect()"""
        self.connection.disconnect()
    
    def run_command(self, command: str, wait_time: float = 1.0, timeout: int = None) -> Tuple[bool, str]:
        """Forward to connection.run_command()"""
        return self.connection.run_command(command, wait_time, timeout)
    
    def enter_config_mode(self) -> bool:
        """Forward to connection.enter_config_mode()"""
        return self.connection.enter_config_mode()
    
    def exit_config_mode(self, save: bool = True) -> bool:
        """Forward to connection.exit_config_mode()"""
        return self.connection.exit_config_mode(save)
    
    # The following methods will be added through monkey patching in __init__.py
    # They are defined explicitly here for code completion and documentation purposes
    
    # Configuration methods
    def apply_base_config(self, base_config: str) -> bool:
        """Apply base configuration to the switch"""
        pass
    
    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """Configure basic switch settings"""
        pass
    
    def configure_switch_port(self, port: str) -> bool:
        """Configure a port connected to another switch as a trunk port"""
        pass
    
    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """Configure a port connected to an Access Point"""
        pass
    
    def set_hostname(self) -> bool:
        """Set the switch hostname based on model and serial number"""
        pass
    
    def change_port_vlan(self, port: str, vlan_id: int) -> bool:
        """Change port VLAN"""
        pass
    
    def set_port_status(self, port: str, status: PortStatus) -> bool:
        """Set port status"""
        pass
    
    def get_port_status(self, port: str) -> Optional[PortStatus]:
        """Get port status"""
        pass
    
    def get_port_vlan(self, port: str) -> Optional[int]:
        """Get port VLAN"""
        pass
    
    def get_poe_status(self, port: str) -> Optional[PoEStatus]:
        """Get PoE status"""
        pass
    
    def set_poe_status(self, port: str, status: PoEStatus) -> bool:
        """Set PoE status"""
        pass
    
    # Discovery methods
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """Get LLDP neighbors"""
        pass
    
    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """Get L2 trace data using trace-l2 show command"""
        pass
    
    # Context manager methods
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
