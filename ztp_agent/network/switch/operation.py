"""
Main switch operation class that combines all switch functionality.
"""
import logging
from typing import Optional, List, Tuple, Callable, Any

from ztp_agent.network.switch.base.connection import BaseConnection
from ztp_agent.network.switch.base.device_info import DeviceInfo
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

class SwitchOperation(BaseConnection, DeviceInfo):
    """
    Main class for all switch operations, combining connection, device info,
    configuration, and discovery capabilities.
    """
    
    def __init__(self, ip: str, username: str, password: str, 
                 preferred_password: Optional[str] = None,
                 timeout: int = 30, debug: bool = False,
                 debug_callback: Optional[Callable[[str, str], None]] = None):
        """
        Initialize switch operation.
        
        Args:
            ip: Switch IP address.
            username: SSH username.
            password: SSH password.
            preferred_password: Password to set on first login.
            timeout: Connection timeout in seconds.
            debug: Enable debug mode.
            debug_callback: Callback for debug messages.
        """
        super().__init__(ip, username, password, preferred_password, timeout, debug, debug_callback)
    
    # Configuration methods will be attached via monkey patching in __init__.py
    # This preserves the existing pattern while using clean inheritance
    
    # Discovery methods will be attached via monkey patching in __init__.py
    # This preserves the existing pattern while using clean inheritance
    
    def __repr__(self) -> str:
        """String representation of the switch operation."""
        return f"SwitchOperation(ip='{self.ip}', connected={self.connected})"