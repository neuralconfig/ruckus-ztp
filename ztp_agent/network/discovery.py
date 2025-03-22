"""
Discovery module for finding devices in the network.
"""
import logging
from typing import Dict, List, Any, Optional

from ztp_agent.network.switch import SwitchOperation

# Set up logging
logger = logging.getLogger(__name__)

class DeviceDiscovery:
    """Class for discovering devices in the network via LLDP"""
    
    def __init__(self, switches: Dict[str, SwitchOperation]):
        """
        Initialize device discovery.
        
        Args:
            switches: Dictionary of switch IP to SwitchOperation instance.
        """
        self.switches = switches
    
    def discover_neighbors(self, switch_ip: str) -> Dict[str, Dict[str, Any]]:
        """
        Discover neighbors for a switch.
        
        Args:
            switch_ip: IP address of the switch.
            
        Returns:
            Dictionary of port to neighbor information.
        """
        if switch_ip not in self.switches:
            logger.error(f"Switch '{switch_ip}' not found")
            return {}
        
        switch = self.switches[switch_ip]
        
        try:
            with switch:
                success, neighbors = switch.get_lldp_neighbors()
                
                if not success:
                    logger.error(f"Failed to get LLDP neighbors for switch {switch_ip}")
                    return {}
                
                return neighbors
        
        except Exception as e:
            logger.error(f"Error discovering neighbors for switch {switch_ip}: {e}", exc_info=True)
            return {}
    
    def classify_device(self, system_name: str) -> str:
        """
        Classify device type based on system name.
        
        Args:
            system_name: Device system name.
            
        Returns:
            Device type: 'switch', 'ap', or 'unknown'.
        """
        if 'ICX' in system_name:
            return 'switch'
        elif 'AP' in system_name or 'R' in system_name:
            return 'ap'
        else:
            return 'unknown'
