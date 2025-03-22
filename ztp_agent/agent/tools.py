"""
Tools for the ZTP AI agent.
"""
import logging
from typing import Dict, List, Optional, Any

from smolagents import tool, Tool

from ztp_agent.network.switch import (
    SwitchOperation,
    PortStatus,
    PoEStatus
)

# Set up logging
logger = logging.getLogger(__name__)


class GetPortStatusTool(Tool):
    name = "get_port_status"
    description = "Get status of a port on a switch"
    inputs = {
        "switch_ip": {
            "type": "string",
            "description": "IP address of the switch"
        },
        "port": {
            "type": "string",
            "description": "Port name (e.g., '1/1/1')"
        }
    }
    output_type = "object"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self, switch_ip: str, port: str) -> Dict[str, Any]:
        """
        Get status of a port.
        
        Args:
            switch_ip: IP address of the switch.
            port: Port name.
            
        Returns:
            Dictionary of port status information.
            
        Raises:
            ValueError: If switch not found.
        """
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        switch = self.switches[switch_ip]
        
        with switch:
            port_status = switch.get_port_status(port)
            vlan = switch.get_port_vlan(port)
            poe_status = switch.get_poe_status(port)
            
            return {
                "port": port,
                "status": port_status.value if port_status else "unknown",
                "vlan": vlan,
                "poe_status": poe_status.value if poe_status else "not supported",
            }


class ChangePortVlanTool(Tool):
    name = "change_port_vlan"
    description = "Change VLAN of a port on a switch"
    inputs = {
        "switch_ip": {
            "type": "string",
            "description": "IP address of the switch"
        },
        "port": {
            "type": "string",
            "description": "Port name (e.g., '1/1/1')"
        },
        "vlan_id": {
            "type": "integer",
            "description": "New VLAN ID"
        }
    }
    output_type = "boolean"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self, switch_ip: str, port: str, vlan_id: int) -> bool:
        """
        Change VLAN of a port.
        
        Args:
            switch_ip: IP address of the switch.
            port: Port name.
            vlan_id: New VLAN ID.
            
        Returns:
            True if successful, False otherwise.
            
        Raises:
            ValueError: If switch not found.
        """
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        switch = self.switches[switch_ip]
        
        with switch:
            success = switch.change_port_vlan(port, vlan_id)
            return success


class SetPortStatusTool(Tool):
    name = "set_port_status"
    description = "Set status of a port on a switch"
    inputs = {
        "switch_ip": {
            "type": "string",
            "description": "IP address of the switch"
        },
        "port": {
            "type": "string",
            "description": "Port name (e.g., '1/1/1')"
        },
        "status": {
            "type": "string",
            "description": "New status ('enable' or 'disable')"
        }
    }
    output_type = "boolean"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self, switch_ip: str, port: str, status: str) -> bool:
        """
        Set status of a port.
        
        Args:
            switch_ip: IP address of the switch.
            port: Port name.
            status: New status ("enable" or "disable").
            
        Returns:
            True if successful, False otherwise.
            
        Raises:
            ValueError: If switch not found or status invalid.
        """
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        try:
            port_status = PortStatus(status.lower())
        except ValueError:
            raise ValueError(f"Invalid port status '{status}'. Use 'enable' or 'disable'.")
        
        switch = self.switches[switch_ip]
        
        with switch:
            success = switch.set_port_status(port, port_status)
            return success


class SetPoEStatusTool(Tool):
    name = "set_poe_status"
    description = "Set PoE status of a port on a switch"
    inputs = {
        "switch_ip": {
            "type": "string",
            "description": "IP address of the switch"
        },
        "port": {
            "type": "string",
            "description": "Port name (e.g., '1/1/1')"
        },
        "status": {
            "type": "string",
            "description": "New status ('enabled' or 'disabled')"
        }
    }
    output_type = "boolean"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self, switch_ip: str, port: str, status: str) -> bool:
        """
        Set PoE status of a port.
        
        Args:
            switch_ip: IP address of the switch.
            port: Port name.
            status: New status ("enabled" or "disabled").
            
        Returns:
            True if successful, False otherwise.
            
        Raises:
            ValueError: If switch not found or status invalid.
        """
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        try:
            poe_status = PoEStatus(status.lower())
        except ValueError:
            raise ValueError(
                f"Invalid PoE status '{status}'. Use 'enabled' or 'disabled'."
            )
        
        switch = self.switches[switch_ip]
        
        with switch:
            success = switch.set_poe_status(port, poe_status)
            return success


class GetSwitchesTool(Tool):
    name = "get_switches"
    description = "Get list of available switches"
    inputs = {}
    output_type = "array"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self) -> List[Dict[str, Any]]:
        """
        Get list of available switches.
        
        Returns:
            List of switch information dictionaries.
        """
        return [
            {"ip": ip}
            for ip in self.switches.keys()
        ]


class GetLLDPNeighborsTool(Tool):
    name = "get_lldp_neighbors"
    description = "Get LLDP neighbors for a switch"
    inputs = {
        "switch_ip": {
            "type": "string",
            "description": "IP address of the switch"
        }
    }
    output_type = "object"

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def forward(self, switch_ip: str) -> Dict[str, Any]:
        """
        Get LLDP neighbors for a switch.
        
        Args:
            switch_ip: IP address of the switch.
            
        Returns:
            Dictionary of port to neighbor information.
            
        Raises:
            ValueError: If switch not found.
        """
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        switch = self.switches[switch_ip]
        
        with switch:
            success, neighbors = switch.get_lldp_neighbors()
            
            if not success:
                return {"error": "Failed to get LLDP neighbors"}
            
            return {"neighbors": neighbors}


def get_network_tools(
    switches: Dict[str, SwitchOperation]
) -> List[Tool]:
    """
    Get tools for network operations.
    
    Args:
        switches: Dictionary of switch IP to SwitchOperation instance.
        
    Returns:
        List of network tools.
    """
    tools = [
        GetSwitchesTool(switches),
        GetPortStatusTool(switches),
        ChangePortVlanTool(switches),
        SetPortStatusTool(switches),
        SetPoEStatusTool(switches),
        GetLLDPNeighborsTool(switches)
    ]
    
    return tools
