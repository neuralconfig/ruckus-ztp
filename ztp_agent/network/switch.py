"""
Switch operations module for interacting with RUCKUS ICX switches.
"""
import logging
import time
import paramiko
import re
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

# Set up logging
logger = logging.getLogger(__name__)

class PortStatus(str, Enum):
    """Port administrative status"""
    ENABLE = "enable"
    DISABLE = "disable"

class PoEStatus(str, Enum):
    """PoE status"""
    ENABLED = "enabled"
    DISABLED = "disabled"

class SwitchOperation:
    """Class for interacting with RUCKUS ICX switches via SSH"""
    
    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: int = 30
    ):
        """
        Initialize switch operation.
        
        Args:
            ip: IP address of the switch.
            username: Username for SSH connection.
            password: Password for SSH connection.
            timeout: Command timeout in seconds.
        """
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.client = None
        self.connected = False
    
    def __enter__(self):
        """Enter context manager"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager"""
        self.disconnect()
    
    def connect(self) -> bool:
        """
        Connect to the switch via SSH.
        
        Returns:
            True if successful, False otherwise.
        """
        if self.connected:
            return True
        
        try:
            # Create SSH client
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to switch
            logger.debug(f"Connecting to switch {self.ip}")
            self.client.connect(
                hostname=self.ip,
                username=self.username,
                password=self.password,
                timeout=self.timeout
            )
            
            # Get shell
            self.shell = self.client.invoke_shell()
            self.shell.settimeout(self.timeout)
            
            # Wait for prompt
            time.sleep(1)
            output = self.shell.recv(1000).decode('utf-8')
            
            # Check if we're at the command prompt
            if not re.search(r'[>#]', output.strip()):
                logger.error(f"Did not receive prompt from switch {self.ip}")
                self.disconnect()
                return False
            
            # Enter enable mode if needed
            if '#' not in output:
                logger.debug(f"Entering enable mode on switch {self.ip}")
                self.shell.send("enable\n")
                time.sleep(0.5)
                
                # Check if password is required
                output = self.shell.recv(1000).decode('utf-8')
                if 'Password:' in output:
                    self.shell.send(f"{self.password}\n")
                    time.sleep(0.5)
                    output = self.shell.recv(1000).decode('utf-8')
                
                # Verify we're in enable mode
                if '#' not in output:
                    logger.error(f"Failed to enter enable mode on switch {self.ip}")
                    self.disconnect()
                    return False
            
            self.connected = True
            logger.info(f"Connected to switch {self.ip}")
            return True
        
        except Exception as e:
            logger.error(f"Error connecting to switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False
    
    def disconnect(self) -> None:
        """Disconnect from the switch"""
        if self.client:
            self.client.close()
            self.client = None
        
        self.connected = False
        logger.debug(f"Disconnected from switch {self.ip}")
    
    def run_command(self, command: str, wait_time: float = 1.0) -> Tuple[bool, str]:
        """
        Run a command on the switch.
        
        Args:
            command: Command to run.
            wait_time: Time to wait for response in seconds.
            
        Returns:
            Tuple of (success, output).
        """
        if not self.connected:
            if not self.connect():
                return False, "Not connected to switch"
        
        try:
            # Send command
            logger.debug(f"Running command on switch {self.ip}: {command}")
            self.shell.send(f"{command}\n")
            time.sleep(wait_time)
            
            # Get output
            output = self.shell.recv(10000).decode('utf-8')
            
            # Check for errors
            if 'Invalid input' in output or 'Error' in output:
                logger.error(f"Command error on switch {self.ip}: {output}")
                return False, output
            
            return True, output
        
        except Exception as e:
            logger.error(f"Error running command on switch {self.ip}: {e}", exc_info=True)
            self.disconnect()
            return False, str(e)
    
    def get_lldp_neighbors(self) -> Tuple[bool, Dict[str, Dict[str, str]]]:
        """
        Get LLDP neighbors.
        
        Returns:
            Tuple of (success, neighbors dictionary).
            neighbors dictionary format: {port: {field: value}}
        """
        success, output = self.run_command("show lldp neighbors detail")
        
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
            chassis_match = re.match(r'Chassis ID: (.+)', line)
            if chassis_match and current_port:
                neighbors[current_port]['chassis_id'] = chassis_match.group(1).strip()
                continue
            
            # Check for port ID
            port_id_match = re.match(r'Port ID: (.+)', line)
            if port_id_match and current_port:
                neighbors[current_port]['port_id'] = port_id_match.group(1).strip()
                continue
            
            # Check for system name
            system_name_match = re.match(r'System name: "(.+)"', line)
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
        
        return True, neighbors
    
    def get_port_status(self, port: str) -> Optional[PortStatus]:
        """
        Get port status.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            PortStatus or None if error.
        """
        success, output = self.run_command(f"show interfaces {port} | include admin")
        
        if not success:
            return None
        
        # Parse output
        status_match = re.search(r'admin (up|down)', output, re.IGNORECASE)
        if status_match:
            status = status_match.group(1).lower()
            if status == 'up':
                return PortStatus.ENABLE
            else:
                return PortStatus.DISABLE
        
        return None
    
    def get_port_vlan(self, port: str) -> Optional[int]:
        """
        Get port VLAN.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            VLAN ID or None if error.
        """
        success, output = self.run_command(f"show interfaces {port} | include VLAN")
        
        if not success:
            return None
        
        # Parse output
        vlan_match = re.search(r'VLAN: (\d+)', output)
        if vlan_match:
            return int(vlan_match.group(1))
        
        return None
    
    def get_poe_status(self, port: str) -> Optional[PoEStatus]:
        """
        Get PoE status.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            PoEStatus or None if error.
        """
        success, output = self.run_command(f"show inline power {port}")
        
        if not success or "Not PoE capable" in output:
            return None
        
        # Parse output
        if "Admin Status: Enabled" in output:
            return PoEStatus.ENABLED
        elif "Admin Status: Disabled" in output:
            return PoEStatus.DISABLED
        
        return None
    
    def change_port_vlan(self, port: str, vlan_id: int) -> bool:
        """
        Change port VLAN.
        
        Args:
            port: Port name (e.g., '1/1/1').
            vlan_id: VLAN ID.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Configure port
        success, _ = self.run_command(f"interface {port}")
        if not success:
            self.run_command("exit")
            return False
        
        # Set VLAN
        success, _ = self.run_command(f"switchport access vlan {vlan_id}")
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Exit config mode
        self.run_command("exit")
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
    
    def set_port_status(self, port: str, status: PortStatus) -> bool:
        """
        Set port status.
        
        Args:
            port: Port name (e.g., '1/1/1').
            status: New status.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Configure port
        success, _ = self.run_command(f"interface {port}")
        if not success:
            self.run_command("exit")
            return False
        
        # Set status
        cmd = status.value
        success, _ = self.run_command(cmd)
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Exit config mode
        self.run_command("exit")
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
    
    def set_poe_status(self, port: str, status: PoEStatus) -> bool:
        """
        Set PoE status.
        
        Args:
            port: Port name (e.g., '1/1/1').
            status: New status.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Configure port
        success, _ = self.run_command(f"interface {port}")
        if not success:
            self.run_command("exit")
            return False
        
        # Set PoE status
        cmd = f"inline power {status.value}"
        success, _ = self.run_command(cmd)
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Exit config mode
        self.run_command("exit")
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
    
    def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
        """
        Perform basic switch configuration.
        
        Args:
            hostname: Switch hostname.
            mgmt_vlan: Management VLAN ID.
            mgmt_ip: Management IP address.
            mgmt_mask: Management IP mask.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Set hostname
        success, _ = self.run_command(f"hostname {hostname}")
        if not success:
            self.run_command("exit")
            return False
        
        # Configure management VLAN
        success, _ = self.run_command(f"vlan {mgmt_vlan} name Management")
        if not success:
            self.run_command("exit")
            return False
        
        # Exit VLAN config
        self.run_command("exit")
        
        # Configure management interface
        success, _ = self.run_command(f"interface ve {mgmt_vlan}")
        if not success:
            self.run_command("exit")
            return False
        
        # Set IP address
        success, _ = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Enable interface
        success, _ = self.run_command("enable")
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Exit interfaces
        self.run_command("exit")
        
        # Save configuration
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
    
    def configure_trunk_port(self, port: str, vlans: List[int]) -> bool:
        """
        Configure a trunk port.
        
        Args:
            port: Port name (e.g., '1/1/1').
            vlans: List of VLAN IDs to trunk.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Configure port
        success, _ = self.run_command(f"interface {port}")
        if not success:
            self.run_command("exit")
            return False
        
        # Configure as trunk
        success, _ = self.run_command("switchport mode trunk")
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Add VLANs to trunk
        for vlan in vlans:
            success, _ = self.run_command(f"switchport trunk allowed vlan add {vlan}")
            if not success:
                self.run_command("exit")
                self.run_command("exit")
                return False
        
        # Exit config mode
        self.run_command("exit")
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
    
    def configure_ap_port(self, port: str, wireless_vlans: List[int]) -> bool:
        """
        Configure a port for an AP.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            
        Returns:
            True if successful, False otherwise.
        """
        # Enter config mode
        success, _ = self.run_command("configure terminal")
        if not success:
            return False
        
        # Configure port
        success, _ = self.run_command(f"interface {port}")
        if not success:
            self.run_command("exit")
            return False
        
        # Configure as trunk
        success, _ = self.run_command("switchport mode trunk")
        if not success:
            self.run_command("exit")
            self.run_command("exit")
            return False
        
        # Add wireless VLANs to trunk
        for vlan in wireless_vlans:
            success, _ = self.run_command(f"switchport trunk allowed vlan add {vlan}")
            if not success:
                self.run_command("exit")
                self.run_command("exit")
                return False
        
        # Enable PoE
        success, _ = self.run_command("inline power enabled")
        if not success:
            # Not all ports support PoE, so this is not a fatal error
            logger.warning(f"Port {port} does not support PoE or inline power command failed")
        
        # Exit config mode
        self.run_command("exit")
        self.run_command("exit")
        self.run_command("write memory")
        
        return True
