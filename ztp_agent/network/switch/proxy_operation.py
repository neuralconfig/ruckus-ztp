"""
Proxy-aware switch operation class that can route SSH commands through SSH proxy.
"""
import logging
from typing import Optional, List, Tuple, Callable, Any

from ztp_agent.network.switch.base.proxy_connection import ProxyAwareConnection
from ztp_agent.network.switch.base.device_info import DeviceInfo
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)


class ProxyAwareSwitchOperation(ProxyAwareConnection, DeviceInfo):
    """
    Proxy-aware switch operation class that combines connection, device info,
    configuration, and discovery capabilities with SSH proxy support.
    """
    
    def __init__(self, ip: str, username: str, password: str, 
                 preferred_password: Optional[str] = None,
                 timeout: int = 30, debug: bool = False,
                 debug_callback: Optional[Callable[[str, str], None]] = None,
                 inventory_update_callback: Optional[Callable[[str, dict], None]] = None,
                 ssh_executor: Optional[Callable] = None):
        """
        Initialize proxy-aware switch operation.
        
        Args:
            ip: Switch IP address.
            username: SSH username.
            password: SSH password.
            preferred_password: Password to set on first login.
            timeout: Connection timeout in seconds.
            debug: Enable debug mode.
            debug_callback: Callback for debug messages.
            inventory_update_callback: Callback to update inventory state.
            ssh_executor: Optional SSH executor function for proxy support.
        """
        super().__init__(ip, username, password, preferred_password, timeout, debug, debug_callback, ssh_executor)
        self.inventory_update_callback = inventory_update_callback
        
        logger.debug(f"Created ProxyAwareSwitchOperation for {ip}, SSH executor: {ssh_executor is not None}")
    
    def __repr__(self) -> str:
        """String representation of the proxy-aware switch operation."""
        proxy_mode = "proxy" if self.ssh_executor else "direct"
        return f"ProxyAwareSwitchOperation(ip='{self.ip}', mode={proxy_mode}, connected={self.connected})"


# Import and attach configuration and discovery methods
# This preserves the existing pattern while adding proxy support
def _attach_methods():
    """Attach configuration and discovery methods to ProxyAwareSwitchOperation."""
    try:
        # Import configuration methods
        from ztp_agent.network.switch.configuration import (
            get_port_status, change_port_vlan, set_port_status, 
            get_port_vlan, get_poe_status, set_poe_status
        )
        
        # Attach configuration methods
        ProxyAwareSwitchOperation.get_port_status = get_port_status
        ProxyAwareSwitchOperation.change_port_vlan = change_port_vlan
        ProxyAwareSwitchOperation.set_port_status = set_port_status
        ProxyAwareSwitchOperation.get_port_vlan = get_port_vlan
        ProxyAwareSwitchOperation.get_poe_status = get_poe_status
        ProxyAwareSwitchOperation.set_poe_status = set_poe_status
        
    except ImportError as e:
        logger.warning(f"Could not import configuration methods: {e}")
    
    try:
        # Import discovery methods
        from ztp_agent.network.switch.discovery import get_lldp_neighbors
        
        # Attach discovery methods
        ProxyAwareSwitchOperation.get_lldp_neighbors = get_lldp_neighbors
        
    except ImportError as e:
        logger.warning(f"Could not import discovery methods: {e}")


# Attach methods when module is imported
_attach_methods()