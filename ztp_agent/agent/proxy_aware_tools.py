"""
Proxy-aware LangChain tools for the ZTP AI agent that can route SSH operations through SSH proxy.
"""
import logging
import asyncio
from typing import Dict, List, Optional, Any, Callable

from langchain.tools import tool
from ztp_agent.network.switch import (
    SwitchOperation,
    PortStatus,
    PoEStatus
)

# Set up logging
logger = logging.getLogger(__name__)

# Global variables to store state (will be set by factory function)
_switches: Dict[str, SwitchOperation] = {}
_ztp_process = None
_ssh_executor: Optional[Callable] = None


def set_network_context(switches: Dict[str, SwitchOperation], ztp_process=None, ssh_executor=None):
    """Set the network context for all tools."""
    global _switches, _ztp_process, _ssh_executor
    _switches = switches
    _ztp_process = ztp_process
    _ssh_executor = ssh_executor


async def _execute_ssh_command(target_ip: str, username: str, password: str, command: str, timeout: int = 30) -> tuple:
    """Execute SSH command using the configured executor (proxy or direct)."""
    if _ssh_executor:
        return await _ssh_executor(target_ip, username, password, command, timeout)
    else:
        # Fallback to direct connection
        switch = SwitchOperation(target_ip, username, password)
        try:
            with switch:
                return switch.run_command(command)
        except Exception as e:
            return False, str(e)


@tool
def get_switches() -> List[Dict[str, Any]]:
    """Get list of all available switches in the network."""
    return [{"ip": ip} for ip in _switches.keys()]


@tool  
def get_ztp_status() -> Dict[str, Any]:
    """Get ZTP (Zero Touch Provisioning) process status and statistics."""
    logger.info("Getting ZTP status")
    logger.debug(f"ZTP process object: {_ztp_process is not None}")
    
    if not _ztp_process:
        return {
            "running": False,
            "error": "ZTP process not initialized"
        }
    
    # Count devices
    switches = _ztp_process.inventory.get('switches', {})
    aps = _ztp_process.inventory.get('aps', {})
    
    switches_discovered = len(switches)
    aps_discovered = len(aps)
    
    switches_configured = sum(1 for s in switches.values() if s.get('configured', False))
    switches_configuring = sum(1 for s in switches.values() if s.get('configuring', False))
    
    # Get seed switches
    seed_switches = [s.get('ip', 'Unknown') for s in switches.values() if s.get('is_seed', False)]
    
    # Get configuration details
    mgmt_vlan = getattr(_ztp_process, 'mgmt_vlan', 'Not configured')
    wireless_vlans = getattr(_ztp_process, 'wireless_vlans', [])
    ip_pool = getattr(_ztp_process, 'ip_pool', 'Not configured')
    poll_interval = _ztp_process.config.get('ztp', {}).get('poll_interval', 60)
    
    return {
        "running": _ztp_process.running,
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


@tool
def get_ap_inventory() -> List[Dict[str, Any]]:
    """Get inventory of discovered access points (APs)."""
    logger.info("Getting AP inventory")
    
    if not _ztp_process:
        return []
    
    ap_inventory = []
    aps = _ztp_process.inventory.get('aps', {})
    
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


@tool
def get_port_status(switch_ip: str, port: str) -> Dict[str, Any]:
    """Get status of a port on a switch including VLAN and PoE information.
    
    Args:
        switch_ip: IP address of the switch
        port: Port name (e.g., '1/1/1')
    """
    if switch_ip not in _switches:
        raise ValueError(f"Switch '{switch_ip}' not found")
    
    switch = _switches[switch_ip]
    
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


@tool
def change_port_vlan(switch_ip: str, port: str, vlan_id: int) -> bool:
    """Change VLAN assignment of a port on a switch.
    
    Args:
        switch_ip: IP address of the switch
        port: Port name (e.g., '1/1/1')
        vlan_id: New VLAN ID
    """
    if switch_ip not in _switches:
        raise ValueError(f"Switch '{switch_ip}' not found")
    
    switch = _switches[switch_ip]
    
    with switch:
        success = switch.change_port_vlan(port, vlan_id)
        return success


@tool
def set_port_status(switch_ip: str, port: str, status: str) -> bool:
    """Enable or disable a port on a switch.
    
    Args:
        switch_ip: IP address of the switch
        port: Port name (e.g., '1/1/1')
        status: New status ('enable' or 'disable')
    """
    if switch_ip not in _switches:
        raise ValueError(f"Switch '{switch_ip}' not found")
    
    try:
        port_status = PortStatus(status.lower())
    except ValueError:
        raise ValueError(f"Invalid port status '{status}'. Use 'enable' or 'disable'.")
    
    switch = _switches[switch_ip]
    
    with switch:
        success = switch.set_port_status(port, port_status)
        return success


@tool
def set_poe_status(switch_ip: str, port: str, status: str) -> bool:
    """Control PoE power delivery on a port.
    
    Args:
        switch_ip: IP address of the switch
        port: Port name (e.g., '1/1/1')
        status: New status ('enabled' or 'disabled')
    """
    if switch_ip not in _switches:
        raise ValueError(f"Switch '{switch_ip}' not found")
    
    try:
        poe_status = PoEStatus(status.lower())
    except ValueError:
        raise ValueError(
            f"Invalid PoE status '{status}'. Use 'enabled' or 'disabled'."
        )
    
    switch = _switches[switch_ip]
    
    with switch:
        success = switch.set_poe_status(port, poe_status)
        return success


@tool
def get_lldp_neighbors(switch_ip: str) -> Dict[str, Any]:
    """Get LLDP neighbors for network topology discovery.
    
    Args:
        switch_ip: IP address of the switch
    """
    if switch_ip not in _switches:
        raise ValueError(f"Switch '{switch_ip}' not found")
    
    switch = _switches[switch_ip]
    
    with switch:
        success, neighbors = switch.get_lldp_neighbors()
        
        if not success:
            return {"error": "Failed to get LLDP neighbors"}
        
        return {"neighbors": neighbors}


@tool
def run_show_command(switch_ip: str, command: str) -> Dict[str, Any]:
    """Execute diagnostic 'show' commands on a RUCKUS ICX switch through proxy if configured.
    
    Args:
        switch_ip: IP address of the switch
        command: Show command to run (e.g., 'show version', 'show interfaces brief')
    """
    logger.info(f"Running show command '{command}' on switch {switch_ip}")
    
    if switch_ip not in _switches:
        raise ValueError(f"Switch {switch_ip} not found")
    
    # Ensure command starts with "show"
    if not command.strip().lower().startswith('show'):
        command = f"show {command}"
    
    try:
        # Get credentials from switch object
        switch = _switches[switch_ip]
        username = switch.username
        password = switch.password
        
        # Use proxy-aware SSH execution if available
        if _ssh_executor:
            # Run in event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, _execute_ssh_command(switch_ip, username, password, command))
                    success, output = future.result()
            else:
                success, output = asyncio.run(_execute_ssh_command(switch_ip, username, password, command))
        else:
            # Fallback to direct connection
            with switch:
                success, output = switch.run_command(command)
        
        if not success:
            return {
                "success": False,
                "error": f"Command '{command}' failed on switch {switch_ip}. Output: {output[:200]}{'...' if len(output) > 200 else ''}",
                "output": output if output else ""
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


@tool
def get_network_summary() -> Dict[str, Any]:
    """Get comprehensive network summary including switches, APs, ZTP status, and topology overview."""
    logger.info("Getting comprehensive network summary")
    
    summary = {
        "switches": [],
        "access_points": [],
        "ztp_status": {},
        "summary_stats": {}
    }
    
    # Get switch information
    switch_count = len(_switches)
    switch_list = []
    for ip in _switches.keys():
        switch_info = {"ip": ip, "status": "available"}
        try:
            # Get credentials from switch object
            switch = _switches[ip]
            username = switch.username
            password = switch.password
            
            # Use proxy-aware SSH execution if available
            if _ssh_executor:
                # Run in event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, _execute_ssh_command(ip, username, password, "show version"))
                        success, output = future.result()
                else:
                    success, output = asyncio.run(_execute_ssh_command(ip, username, password, "show version"))
            else:
                with switch:
                    success, output = switch.run_command("show version")
            
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
    if _ztp_process:
        try:
            ztp_switches = _ztp_process.inventory.get('switches', {})
            ztp_aps = _ztp_process.inventory.get('aps', {})
            
            summary["ztp_status"] = {
                "running": _ztp_process.running,
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


@tool
def get_switch_details(switch_ip: str) -> Dict[str, Any]:
    """Get detailed information about a specific switch including hostname, model, version, and port count.
    
    Args:
        switch_ip: IP address of the switch
    """
    logger.info(f"Getting detailed information for switch {switch_ip}")
    
    if switch_ip not in _switches:
        raise ValueError(f"Switch {switch_ip} not found")
    
    switch = _switches[switch_ip]
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
        # Get credentials from switch object
        username = switch.username
        password = switch.password
        
        # Use proxy-aware SSH execution if available
        if _ssh_executor:
            # Run commands through proxy
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    # Get version information
                    future = executor.submit(asyncio.run, _execute_ssh_command(switch_ip, username, password, "show version"))
                    success, version_output = future.result()
                    
                    if success:
                        details["reachable"] = True
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
                    future = executor.submit(asyncio.run, _execute_ssh_command(switch_ip, username, password, "show running-config | include hostname"))
                    success, hostname_output = future.result()
                    
                    if success:
                        for line in hostname_output.split('\n'):
                            if 'hostname' in line:
                                parts = line.strip().split()
                                if len(parts) >= 2:
                                    details["hostname"] = parts[1]
                                    break
                    
                    # Get interface summary
                    future = executor.submit(asyncio.run, _execute_ssh_command(switch_ip, username, password, "show interfaces brief"))
                    success, int_output = future.result()
                    
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
            else:
                # Direct async execution
                success, version_output = await _execute_ssh_command(switch_ip, username, password, "show version")
                if success:
                    details["reachable"] = True
                    # Process version output...
        else:
            # Fallback to direct connection
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


def get_proxy_aware_network_tools(switches: Dict[str, SwitchOperation], ztp_process=None, ssh_executor=None) -> List:
    """Get all network tools with proxy awareness after setting the context."""
    # Set the global context including SSH executor
    set_network_context(switches, ztp_process, ssh_executor)
    
    # Return the list of tools
    tools = [
        get_switches,
        get_switch_details,
        get_network_summary,
        get_port_status,
        change_port_vlan,
        set_port_status,
        set_poe_status,
        get_lldp_neighbors,
        run_show_command
    ]
    
    if ztp_process:
        tools.extend([get_ap_inventory, get_ztp_status])
    
    return tools