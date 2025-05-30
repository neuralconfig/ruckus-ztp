"""
LangChain tools for the ZTP AI agent.
"""
import logging
from typing import Dict, List, Optional, Any, Type

from langchain.tools import BaseTool
from pydantic import BaseModel, Field

from ztp_agent.network.switch import (
    SwitchOperation,
    PortStatus,
    PoEStatus
)

# Set up logging
logger = logging.getLogger(__name__)


# Input schemas for tools with parameters
class PortStatusInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")
    port: str = Field(description="Port name (e.g., '1/1/1')")


class ChangePortVlanInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")
    port: str = Field(description="Port name (e.g., '1/1/1')")
    vlan_id: int = Field(description="New VLAN ID")


class SetPortStatusInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")
    port: str = Field(description="Port name (e.g., '1/1/1')")
    status: str = Field(description="New status ('enable' or 'disable')")


class SetPoEStatusInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")
    port: str = Field(description="Port name (e.g., '1/1/1')")
    status: str = Field(description="New status ('enabled' or 'disabled')")


class GetLLDPNeighborsInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")


class RunShowCommandInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")
    command: str = Field(description="Show command to run (e.g., 'show version', 'show interfaces brief')")


class GetSwitchDetailsInput(BaseModel):
    switch_ip: str = Field(description="IP address of the switch")


# Tools with no parameters (empty input schemas)
class NoInput(BaseModel):
    pass


class GetPortStatusTool(BaseTool):
    """Tool to get status of a port on a RUCKUS ICX switch."""
    name: str = "get_port_status"
    description: str = "Get status of a port on a switch including VLAN and PoE information"
    args_schema: Type[BaseModel] = PortStatusInput
    switches: Dict[str, SwitchOperation] = {}

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__(switches=switches)

    def _run(self, switch_ip: str, port: str) -> Dict[str, Any]:
        """Execute the tool."""
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


class ChangePortVlanTool(BaseTool):
    """Tool to change VLAN assignment of a port on a RUCKUS ICX switch."""
    name: str = "change_port_vlan"
    description: str = "Change VLAN assignment of a port on a switch"
    args_schema: Type[BaseModel] = ChangePortVlanInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str, port: str, vlan_id: int) -> bool:
        """Execute the tool."""
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        switch = self.switches[switch_ip]
        
        with switch:
            success = switch.change_port_vlan(port, vlan_id)
            return success


class SetPortStatusTool(BaseTool):
    """Tool to enable or disable a port on a RUCKUS ICX switch."""
    name: str = "set_port_status"
    description: str = "Enable or disable a port on a switch"
    args_schema: Type[BaseModel] = SetPortStatusInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str, port: str, status: str) -> bool:
        """Execute the tool."""
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


class SetPoEStatusTool(BaseTool):
    """Tool to control PoE (Power over Ethernet) on a port on a RUCKUS ICX switch."""
    name: str = "set_poe_status"
    description: str = "Control PoE power delivery on a port"
    args_schema: Type[BaseModel] = SetPoEStatusInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str, port: str, status: str) -> bool:
        """Execute the tool."""
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


class GetSwitchesTool(BaseTool):
    """Tool to get list of all available switches in the network."""
    name: str = "get_switches"
    description: str = "Get list of all available switches in the network"
    args_schema: Type[BaseModel] = NoInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self) -> List[Dict[str, Any]]:
        """Execute the tool."""
        return [
            {"ip": ip}
            for ip in self.switches.keys()
        ]


class GetLLDPNeighborsTool(BaseTool):
    """Tool to get LLDP neighbors for network topology discovery on a RUCKUS ICX switch."""
    name: str = "get_lldp_neighbors"
    description: str = "Get LLDP neighbors for network topology discovery"
    args_schema: Type[BaseModel] = GetLLDPNeighborsInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str) -> Dict[str, Any]:
        """Execute the tool."""
        if switch_ip not in self.switches:
            raise ValueError(f"Switch '{switch_ip}' not found")
        
        switch = self.switches[switch_ip]
        
        with switch:
            success, neighbors = switch.get_lldp_neighbors()
            
            if not success:
                return {"error": "Failed to get LLDP neighbors"}
            
            return {"neighbors": neighbors}


class RunShowCommandTool(BaseTool):
    """Tool to execute diagnostic 'show' commands on a RUCKUS ICX switch."""
    name: str = "run_show_command"
    description: str = "Execute diagnostic 'show' commands on a RUCKUS ICX switch"
    args_schema: Type[BaseModel] = RunShowCommandInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str, command: str) -> Dict[str, Any]:
        """Execute the tool."""
        logger.info(f"Running show command '{command}' on switch {switch_ip}")
        
        if switch_ip not in self.switches:
            raise ValueError(f"Switch {switch_ip} not found")
        
        switch = self.switches[switch_ip]
        
        # Ensure command starts with "show"
        if not command.strip().lower().startswith('show'):
            command = f"show {command}"
        
        try:
            success, output = switch.run_command(command)
            
            if not success:
                return {
                    "success": False,
                    "error": f"Command '{command}' failed on switch {switch_ip}",
                    "output": ""
                }
            
            return {
                "success": True,
                "command": command,
                "switch_ip": switch_ip,
                "output": output
            }
            
        except Exception as e:
            logger.error(f"Error running command '{command}' on switch {switch_ip}: {e}")
            return {
                "success": False,
                "error": str(e),
                "output": ""
            }


class GetZTPStatusTool(BaseTool):
    """Tool to get ZTP (Zero Touch Provisioning) process status and statistics."""
    name: str = "get_ztp_status"
    description: str = "Get ZTP (Zero Touch Provisioning) process status and statistics"
    args_schema: Type[BaseModel] = NoInput
    ztp_process: Any = None

    def __init__(self, ztp_process):
        super().__init__(ztp_process=ztp_process)

    def _run(self) -> Dict[str, Any]:
        """Execute the tool."""
        logger.info("Getting ZTP status")
        
        if not self.ztp_process:
            return {
                "running": False,
                "error": "ZTP process not initialized"
            }
        
        # Count devices
        switches = self.ztp_process.inventory.get('switches', {})
        aps = self.ztp_process.inventory.get('aps', {})
        
        switches_discovered = len(switches)
        aps_discovered = len(aps)
        
        switches_configured = sum(1 for s in switches.values() if s.get('configured', False))
        switches_configuring = sum(1 for s in switches.values() if s.get('configuring', False))
        
        # Get seed switches
        seed_switches = [s.get('ip', 'Unknown') for s in switches.values() if s.get('is_seed', False)]
        
        # Get configuration details
        mgmt_vlan = getattr(self.ztp_process, 'mgmt_vlan', 'Not configured')
        wireless_vlans = getattr(self.ztp_process, 'wireless_vlans', [])
        ip_pool = getattr(self.ztp_process, 'ip_pool', 'Not configured')
        poll_interval = self.ztp_process.config.get('ztp', {}).get('poll_interval', 60)
        
        return {
            "running": self.ztp_process.running,
            "switches_discovered": switches_discovered,
            "switches_configured": switches_configured,
            "switches_configuring": switches_configuring,
            "aps_discovered": aps_discovered,
            "seed_switches": seed_switches,
            "management_vlan": mgmt_vlan,
            "wireless_vlans": wireless_vlans,
            "ip_pool": ip_pool,
            "poll_interval": poll_interval,
            "base_config_applied": sum(1 for s in switches.values() if s.get('base_config_applied', False))
        }


class GetAPInventoryTool(BaseTool):
    """Tool to get inventory of discovered access points (APs)."""
    name: str = "get_ap_inventory"
    description: str = "Get inventory of discovered access points (APs)"
    args_schema: Type[BaseModel] = NoInput

    def __init__(self, ztp_process):
        super().__init__()
        self.ztp_process = ztp_process

    def _run(self) -> List[Dict[str, Any]]:
        """Execute the tool."""
        logger.info("Getting AP inventory")
        
        if not self.ztp_process:
            return []
        
        ap_inventory = []
        aps = self.ztp_process.inventory.get('aps', {})
        
        for mac, ap_data in aps.items():
            ap_info = {
                "mac": mac,
                "ip": ap_data.get('ip', 'Unknown'),
                "hostname": ap_data.get('hostname') or ap_data.get('system_name', 'Unknown'),
                "model": ap_data.get('model') or ap_data.get('system_name', 'Unknown'),
                "status": ap_data.get('status', 'Unknown'),
                "connected_switch": ap_data.get('switch_ip', 'Unknown'),
                "connected_port": ap_data.get('switch_port', 'Unknown'),
                "configured": ap_data.get('status') == 'Configured'
            }
            ap_inventory.append(ap_info)
        
        return ap_inventory


class GetNetworkSummaryTool(BaseTool):
    """Tool to get comprehensive network summary including switches, APs, ZTP status, and topology overview."""
    name: str = "get_network_summary"
    description: str = "Get comprehensive network summary including switches, APs, ZTP status, and topology overview"
    args_schema: Type[BaseModel] = NoInput

    def __init__(self, switches: Dict[str, SwitchOperation], ztp_process=None):
        super().__init__()
        self.switches = switches
        self.ztp_process = ztp_process

    def _run(self) -> Dict[str, Any]:
        """Execute the tool."""
        logger.info("Getting comprehensive network summary")
        
        summary = {
            "switches": [],
            "access_points": [],
            "ztp_status": {},
            "summary_stats": {}
        }
        
        # Get switch information
        switch_count = len(self.switches)
        switch_list = []
        for ip in self.switches.keys():
            switch_info = {"ip": ip, "status": "available"}
            try:
                with self.switches[ip]:
                    # Try to get basic info
                    success, output = self.switches[ip].run_command("show version")
                    if success:
                        # Extract model from show version
                        for line in output.split('\n'):
                            if 'ICX' in line and ('Switch' in line or 'Router' in line):
                                switch_info["model"] = line.strip()
                                break
                    switch_info["status"] = "reachable"
            except Exception:
                switch_info["status"] = "unreachable"
            switch_list.append(switch_info)
        
        summary["switches"] = switch_list
        
        # Get ZTP process info if available
        if self.ztp_process:
            try:
                ztp_switches = self.ztp_process.inventory.get('switches', {})
                ztp_aps = self.ztp_process.inventory.get('aps', {})
                
                summary["ztp_status"] = {
                    "running": self.ztp_process.running,
                    "switches_discovered": len(ztp_switches),
                    "switches_configured": sum(1 for s in ztp_switches.values() if s.get('configured', False)),
                    "aps_discovered": len(ztp_aps),
                    "aps_configured": sum(1 for ap in ztp_aps.values() if ap.get('status') == 'Configured')
                }
                
                # Add AP information
                ap_list = []
                for mac, ap_data in ztp_aps.items():
                    ap_info = {
                        "mac": mac,
                        "ip": ap_data.get('ip', 'Unknown'),
                        "hostname": ap_data.get('hostname') or ap_data.get('system_name', 'Unknown'),
                        "connected_switch": ap_data.get('switch_ip', 'Unknown'),
                        "connected_port": ap_data.get('switch_port', 'Unknown'),
                        "status": ap_data.get('status', 'Unknown')
                    }
                    ap_list.append(ap_info)
                summary["access_points"] = ap_list
                
            except Exception as e:
                logger.error(f"Error getting ZTP information: {e}")
                summary["ztp_status"] = {"error": str(e)}
        
        # Generate summary statistics
        summary["summary_stats"] = {
            "total_switches": switch_count,
            "reachable_switches": len([s for s in switch_list if s["status"] == "reachable"]),
            "total_aps": len(summary.get("access_points", [])),
            "configured_aps": len([ap for ap in summary.get("access_points", []) if ap["status"] == "Configured"])
        }
        
        return summary


class GetSwitchDetailsTool(BaseTool):
    """Tool to get detailed information about a specific switch including hostname, model, version, and port count."""
    name: str = "get_switch_details"
    description: str = "Get detailed information about a specific switch including hostname, model, version, and port count"
    args_schema: Type[BaseModel] = GetSwitchDetailsInput

    def __init__(self, switches: Dict[str, SwitchOperation]):
        super().__init__()
        self.switches = switches

    def _run(self, switch_ip: str) -> Dict[str, Any]:
        """Execute the tool."""
        logger.info(f"Getting detailed information for switch {switch_ip}")
        
        if switch_ip not in self.switches:
            raise ValueError(f"Switch {switch_ip} not found")
        
        switch = self.switches[switch_ip]
        details = {
            "ip": switch_ip,
            "reachable": False,
            "hostname": None,
            "model": None,
            "version": None,
            "serial": None,
            "uptime": None,
            "port_count": None,
            "interface_summary": {},
            "error": None
        }
        
        try:
            with switch:
                details["reachable"] = True
                
                # Get version information
                success, version_output = switch.run_command("show version")
                if success:
                    for line in version_output.split('\n'):
                        line = line.strip()
                        if 'ICX' in line and ('Switch' in line or 'Router' in line):
                            details["model"] = line
                        elif line.startswith('SW:'):
                            details["version"] = line.replace('SW:', '').strip()
                        elif 'Serial' in line:
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if 'Serial' in part and i + 1 < len(parts):
                                    details["serial"] = parts[i + 1]
                                    break
                        elif 'Up time' in line:
                            details["uptime"] = line.split('Up time')[1].strip()
                
                # Get hostname
                success, hostname_output = switch.run_command("show running-config | include hostname")
                if success:
                    for line in hostname_output.split('\n'):
                        if 'hostname' in line:
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                details["hostname"] = parts[1]
                                break
                
                # Get interface summary
                success, int_output = switch.run_command("show interfaces brief")
                if success:
                    interface_counts = {"up": 0, "down": 0, "disabled": 0}
                    lines = int_output.split('\n')
                    for line in lines:
                        if '/' in line and ('Up' in line or 'Down' in line or 'Disabled' in line):
                            if 'Up' in line:
                                interface_counts["up"] += 1
                            elif 'Disabled' in line:
                                interface_counts["disabled"] += 1
                            else:
                                interface_counts["down"] += 1
                    
                    details["interface_summary"] = interface_counts
                    details["port_count"] = sum(interface_counts.values())
                
        except Exception as e:
            logger.error(f"Error getting switch details for {switch_ip}: {e}")
            details["error"] = str(e)
        
        return details


def get_network_tools(
    switches: Dict[str, SwitchOperation],
    ztp_process = None
) -> List[BaseTool]:
    """
    Get LangChain tools for network operations.
    
    Args:
        switches: Dictionary of switch IP to SwitchOperation instance.
        ztp_process: ZTP process instance for accessing inventory.
        
    Returns:
        List of LangChain network tools.
    """
    tools = [
        GetSwitchesTool(switches),
        GetSwitchDetailsTool(switches),
        GetNetworkSummaryTool(switches, ztp_process),
        GetPortStatusTool(switches),
        ChangePortVlanTool(switches),
        SetPortStatusTool(switches),
        SetPoEStatusTool(switches),
        GetLLDPNeighborsTool(switches),
        RunShowCommandTool(switches)
    ]
    
    if ztp_process:
        tools.append(GetAPInventoryTool(ztp_process))
        tools.append(GetZTPStatusTool(ztp_process))
    
    return tools