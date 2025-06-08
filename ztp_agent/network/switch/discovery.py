"""
Network discovery module for switch operations.
"""
import logging
import re
import time
from typing import Dict, Tuple

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ztp_agent.network.switch.base.connection import BaseConnection as SwitchConnection
else:
    # At runtime, this will be the actual connection object passed in
    SwitchConnection = object

# Set up logging
logger = logging.getLogger(__name__)

class SwitchDiscovery:
    """Class for switch discovery operations"""
    
    def __init__(self, connection: SwitchConnection):
        """
        Initialize with a switch connection.
        
        Args:
            connection: SwitchConnection object
        """
        self.connection = connection

    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.connection.run_command("show lldp neighbors detail")
        
        if not success:
            return False, {}
        
        neighbors = {}
        current_port = None
        
        # Parse output
        for line in output.splitlines():
            # Check for port name
            port_match = re.match(r'Local port: (.+)', line)
            if port_match:
                current_port = port_match.group(1).strip()
                neighbors[current_port] = {}
                continue
            
            # Check for chassis ID
            chassis_match = re.match(r'  \+ Chassis ID \([^)]+\): (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'  \+ Port ID \([^)]+\): (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'  \+ System name\s+: "(.+)"', line)
            if system_name_match and current_port:
                system_name = system_name_match.group(1).strip()
                neighbors[current_port]['system_name'] = system_name
                
                # Determine device type
                if 'ICX' in system_name:
                    neighbors[current_port]['type'] = 'switch'
                elif 'AP' in system_name or 'R' in system_name:
                    neighbors[current_port]['type'] = 'ap'
                else:
                    neighbors[current_port]['type'] = 'unknown'
                continue
                
            # Check for system description
            system_desc_match = re.match(r'  \+ System description\s+: "(.+)"', line)
            if system_desc_match and current_port:
                system_desc = system_desc_match.group(1).strip()
                neighbors[current_port]['system_description'] = system_desc
                
                # If we couldn't determine type from system name, try from description
                if 'type' not in neighbors[current_port]:
                    if 'ICX' in system_desc:
                        neighbors[current_port]['type'] = 'switch'
                    elif 'AP' in system_desc or 'R' in system_desc:
                        neighbors[current_port]['type'] = 'ap'
                    else:
                        neighbors[current_port]['type'] = 'unknown'
                
                # Extract model for APs from system description
                # Format: "Ruckus R350 Multimedia Hotzone Wireless AP/SW Version: 7.1.0.510.1041"
                # We want to extract "R350" (2nd word)
                if (neighbors[current_port].get('type') == 'ap' or 
                    neighbors[current_port].get('type') == 'unknown' and 'AP' in system_desc):
                    
                    # Split system description and try to extract model (2nd word)
                    desc_parts = system_desc.split()
                    if len(desc_parts) >= 2 and desc_parts[0].lower() == 'ruckus':
                        # Extract model from 2nd position (e.g., "R350", "R750", etc.)
                        model = desc_parts[1]
                        neighbors[current_port]['model'] = model
                        logger.debug(f"Extracted AP model '{model}' from system description: {system_desc}")
                        # Update type to ap if it wasn't set
                        if neighbors[current_port].get('type') == 'unknown':
                            neighbors[current_port]['type'] = 'ap'
                    else:
                        logger.warning(f"Could not extract AP model from system description: {system_desc}")
                
                continue
                
            # Check for port description
            port_desc_match = re.match(r'  \+ Port description\s+: "(.+)"', line)
            if port_desc_match and current_port:
                neighbors[current_port]['port_description'] = port_desc_match.group(1).strip()
                continue
                
            # Check for management address
            mgmt_addr_match = re.match(r'  \+ Management address \(IPv4\): (.+)', line)
            if mgmt_addr_match and current_port:
                mgmt_addr = mgmt_addr_match.group(1).strip()
                neighbors[current_port]['mgmt_address'] = mgmt_addr
                continue
        
        # For switches, use trace-l2 to get IP addresses
        if any(n.get('type') == 'switch' for n in neighbors.values()):
            # Run trace-l2 on VLAN 1 (default untagged VLAN on unconfigured switches)
            success, _ = self.connection.run_command("trace-l2 vlan 1")
            if success:
                if self.connection.debug and self.connection.debug_callback:
                    self.connection.debug_callback("Initiated trace-l2 on VLAN 1, waiting for completion...", color="yellow")
                    
                # Wait for the command to complete (trace probes take a few seconds)
                time.sleep(5)
                
                # Get trace-l2 results
                trace_attempts = 0
                max_attempts = 3
                ip_data = {}
                trace_success = False
                
                while trace_attempts < max_attempts:
                    trace_attempts += 1
                    
                    if self.connection.debug and self.connection.debug_callback:
                        self.connection.debug_callback(f"Getting trace-l2 results (attempt {trace_attempts}/{max_attempts})...", color="yellow")
                    
                    trace_success, ip_data = self.get_l2_trace_data()
                    
                    # If we got data or reached max attempts, break
                    if trace_success and ip_data:
                        if self.connection.debug and self.connection.debug_callback:
                            self.connection.debug_callback(f"Successfully retrieved trace-l2 data with {len(ip_data)} entries", color="green")
                        break
                    elif trace_attempts < max_attempts:
                        # Wait a bit more before retrying
                        time.sleep(3)
                
                if trace_success and ip_data:
                    # Update neighbor information with IP addresses
                    for port, info in neighbors.items():
                        # If it's a switch and has no valid IP address from LLDP
                        if info.get('type') == 'switch' and (
                            'mgmt_address' not in info or 
                            info.get('mgmt_address') == '0.0.0.0'
                        ):
                            # Try to find IP in trace-l2 data
                            mac_addr = info.get('chassis_id')
                            if mac_addr and mac_addr in ip_data:
                                info['mgmt_address'] = ip_data[mac_addr]
                                logger.info(f"Updated IP for switch at port {port} using trace-l2: {ip_data[mac_addr]}")
                                
                                if self.connection.debug and self.connection.debug_callback:
                                    self.connection.debug_callback(f"Updated IP for switch at port {port}: {ip_data[mac_addr]}", color="green")
        
        return True, neighbors

    def get_l2_trace_data(self) -> Tuple[bool, Dict[str, str]]:
        """
        Get L2 trace data using trace-l2 show command.
        
        Returns:
            Tuple of (success, {mac_address: ip_address}).
        """
        success, output = self.connection.run_command("trace-l2 show")
        
        if not success:
            return False, {}
        
        # Parse the trace-l2 output
        ip_mac_map = {}
        path_pattern = re.compile(r'path \d+ from (.+),')
        hop_pattern = re.compile(r'  \d+\s+(\S+)\s+(?:\S+)?\s+(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f\.]+)')
        
        current_path = None
        
        for line in output.splitlines():
            # Check for new path
            path_match = path_pattern.match(line)
            if path_match:
                current_path = path_match.group(1).strip()
                continue
                
            # Check for hop information
            hop_match = hop_pattern.match(line)
            if hop_match:
                port, ip, mac = hop_match.groups()
                mac = mac.lower()  # Normalize MAC address
                
                # Store IP and MAC mapping
                if ip != '0.0.0.0' and mac != '0000.0000.0000':
                    ip_mac_map[mac] = ip
                    
                    # Debug output
                    if self.connection.debug and self.connection.debug_callback:
                        self.connection.debug_callback(f"Found switch in trace-l2: MAC={mac}, IP={ip}", color="green")
                        
        return True, ip_mac_map


# Module-level functions for monkey patching to SwitchOperation class

def get_lldp_neighbors(connection):
    """Get LLDP neighbor information."""
    discovery_obj = SwitchDiscovery(connection)
    return discovery_obj.get_lldp_neighbors()

def get_l2_trace_data(connection):
    """Get L2 trace data for switch discovery."""
    discovery_obj = SwitchDiscovery(connection)
    return discovery_obj.get_l2_trace_data()
