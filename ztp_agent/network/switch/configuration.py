"""
Switch configuration module for RUCKUS ICX switches.
"""
import logging
import re
from typing import List, Optional

from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

def set_hostname(self) -> bool:
    """
    Set the switch hostname based on model and serial number.
    Format will be <model>-<serial>
    
    Returns:
        True if successful, False otherwise.
    """
    # Get model and serial if not already set
    if self.model is None:
        self.model = self.get_model()
    
    if self.serial is None:
        self.serial = self.get_serial()
    
    # Check if we have both
    if not self.model or not self.serial:
        logger.error(f"Failed to get model or serial number for switch {self.ip}")
        return False
    
    # Format hostname
    hostname = f"{self.model}-{self.serial}"
    self.hostname = hostname
    
    try:
        # Enter configuration mode
        if not self.enter_config_mode():
            return False
        
        # Set hostname
        if self.debug and self.debug_callback:
            self.debug_callback(f"Setting hostname to {hostname}", color="yellow")
            
        success, output = self.run_command(f"hostname {hostname}", wait_time=1.0)
        if not success:
            logger.error(f"Failed to set hostname: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Exit config mode and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Set hostname for switch {self.ip} to {hostname}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting hostname: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit config mode
        return False

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
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Configure port
        success, output = self.run_command(f"interface ethernet {port}")
        if not success:
            logger.error(f"Failed to enter interface config mode for {port}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Set VLAN for access port
        success, output = self.run_command(f"vlan-config add untagged-vlan {vlan_id}")
        if not success:
            logger.error(f"Failed to set untagged VLAN {vlan_id} on port {port}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Changed port {port} VLAN to {vlan_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error changing port VLAN: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False

def set_port_status(self, port: str, status: PortStatus) -> bool:
    """
    Set port status.
    
    Args:
        port: Port name (e.g., '1/1/1').
        status: New status.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Configure port
        success, output = self.run_command(f"interface ethernet {port}")
        if not success:
            logger.error(f"Failed to enter interface config mode for {port}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Set status
        cmd = status.value
        success, output = self.run_command(cmd)
        if not success:
            logger.error(f"Failed to set port {port} status to {status.value}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Set port {port} status to {status.value}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting port status: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False

def set_poe_status(self, port: str, status: PoEStatus) -> bool:
    """
    Set PoE status.
    
    Args:
        port: Port name (e.g., '1/1/1').
        status: New status.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Configure port
        success, output = self.run_command(f"interface ethernet {port}")
        if not success:
            logger.error(f"Failed to enter interface config mode for {port}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Set PoE status
        cmd = f"inline power {status.value}"
        success, output = self.run_command(cmd)
        if not success:
            logger.error(f"Failed to set PoE status to {status.value} on port {port}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Set PoE status to {status.value} on port {port}")
        return True
        
    except Exception as e:
        logger.error(f"Error setting PoE status: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False

def apply_base_config(self, base_config: str) -> bool:
    """
    Apply base configuration to the switch.
    This should be done first before any port configuration.
    
    Args:
        base_config: Base configuration string to apply.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Log that we're applying base configuration
        logger.info("Applying base configuration to switch")
        if self.debug and self.debug_callback:
            self.debug_callback("Applying base configuration", color="yellow")
        
        # Split the configuration into lines and run each command
        for line in base_config.strip().split('\n'):
            # Skip empty lines and comments
            line = line.strip()
            if not line or line.startswith('!'):
                continue
                
            # Run the command
            success, output = self.run_command(line)
            if not success:
                logger.error(f"Failed to execute base config command '{line}': {output}")
                # We'll continue anyway to apply as much of the config as possible
        
        # Save configuration
        if not self.exit_config_mode(save=True):
            return False
            
        logger.info("Successfully applied base configuration")
        return True
        
    except Exception as e:
        logger.error(f"Error applying base configuration: {e}", exc_info=True)
        self.exit_config_mode(save=False)
        return False

# Keep this function for backward compatibility
def configure_vlans(self, mgmt_vlan: int, wireless_vlans: List[int] = None, other_vlans: List[int] = None) -> bool:
    """
    DEPRECATED: Use apply_base_config instead.
    Configure all VLANs with spanning tree.
    
    Args:
        mgmt_vlan: Management VLAN ID.
        wireless_vlans: List of wireless VLAN IDs.
        other_vlans: List of other VLAN IDs.
        
    Returns:
        True if successful, False otherwise.
    """
    logger.warning("configure_vlans is deprecated, use apply_base_config instead")
    
    # Build a basic configuration string
    config_lines = []
    
    # Management VLAN
    if mgmt_vlan:
        config_lines.extend([
            f"! Management VLAN",
            f"vlan {mgmt_vlan} name Management",
            "spanning-tree 802-1w",
            "exit"
        ])
    
    # Wireless VLANs
    if wireless_vlans:
        for vlan_id in wireless_vlans:
            config_lines.extend([
                f"! Wireless VLAN {vlan_id}",
                f"vlan {vlan_id} name Wireless-{vlan_id}",
                "spanning-tree 802-1w",
                "exit"
            ])
    
    # Other VLANs
    if other_vlans:
        for vlan_id in other_vlans:
            config_lines.extend([
                f"! Other VLAN {vlan_id}",
                f"vlan {vlan_id} name VLAN-{vlan_id}",
                "spanning-tree 802-1w",
                "exit"
            ])
    
    # Global spanning tree
    config_lines.extend([
        "! Global spanning tree settings",
        "spanning-tree",
        "spanning-tree 802-1w"
    ])
    
    # Apply the configuration
    return self.apply_base_config("\n".join(config_lines))

def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
    """
    Perform basic switch configuration after VLANs have been created.
    
    Args:
        hostname: Switch hostname.
        mgmt_vlan: Management VLAN ID.
        mgmt_ip: Management IP address.
        mgmt_mask: Management IP mask.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Set hostname
        success, output = self.run_command(f"hostname {hostname}")
        if not success:
            logger.error(f"Failed to set hostname to {hostname}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Configure management interface
        success, output = self.run_command(f"interface ve {mgmt_vlan}")
        if not success:
            logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Set IP address
        success, output = self.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
        if not success:
            logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Enable interface
        success, output = self.run_command("enable")
        if not success:
            logger.error(f"Failed to enable interface: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
        return True
        
    except Exception as e:
        logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False

def configure_switch_port(self, port: str) -> bool:
    """
    Configure a port connected to another switch as a trunk port.
    Uses vlan-config add all-tagged to tag all VLANs.
    Assumes VLANs have already been created with configure_vlans.
    
    Args:
        port: Port name (e.g., '1/1/1').
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Configure port
        success, output = self.run_command(f"interface ethernet {port}")
        if not success:
            logger.error(f"Failed to enter interface config mode for {port}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Configure the port as a trunk with all VLANs
        success, output = self.run_command("vlan-config add all-tagged")
        if not success:
            logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
        return True
        
    except Exception as e:
        logger.error(f"Error configuring switch port: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False
        
# For backward compatibility
def configure_trunk_port(self, port: str, vlans: List[int] = None) -> bool:
    """
    Alias for configure_switch_port for backward compatibility.
    
    Args:
        port: Port name (e.g., '1/1/1').
        vlans: Ignored - all VLANs will be tagged.
        
    Returns:
        True if successful, False otherwise.
    """
    return self.configure_switch_port(port)

def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
    """
    Configure a port connected to an Access Point.
    Tags specific VLANs needed for AP operation.
    Assumes VLANs have already been created with configure_vlans.
    
    Args:
        port: Port name (e.g., '1/1/1').
        wireless_vlans: List of wireless VLAN IDs.
        management_vlan: Management VLAN ID for AP management.
        
    Returns:
        True if successful, False otherwise.
    """
    try:
        # Enter config mode
        if not self.enter_config_mode():
            return False
        
        # Configure port
        success, output = self.run_command(f"interface ethernet {port}")
        if not success:
            logger.error(f"Failed to enter interface config mode for {port}: {output}")
            self.exit_config_mode(save=False)
            return False
        
        # Add management VLAN to trunk
        success, output = self.run_command(f"vlan-config add tagged-vlan {management_vlan}")
        if not success:
            logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
            self.run_command("exit")  # Exit interface config
            self.exit_config_mode(save=False)
            return False
        
        # Add wireless VLANs to trunk
        for vlan in wireless_vlans:
            success, output = self.run_command(f"vlan-config add tagged-vlan {vlan}")
            if not success:
                logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                self.run_command("exit")  # Exit interface config
                self.exit_config_mode(save=False)
                return False
        
        # Note: We don't need to configure PoE as the default state is already on
        
        # Exit interface config
        self.run_command("exit")
        
        # Exit global config and save
        if not self.exit_config_mode(save=True):
            return False
        
        logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
        return True
        
    except Exception as e:
        logger.error(f"Error configuring AP port: {e}", exc_info=True)
        self.run_command("exit")  # Try to exit interface config
        self.run_command("exit")  # Try to exit global config
        return False