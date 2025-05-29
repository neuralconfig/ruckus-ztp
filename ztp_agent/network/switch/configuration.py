"""
Configuration module for RUCKUS ICX switches.
"""
import logging
import re
from typing import List, Optional

from ztp_agent.network.switch.base import SwitchConnection
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Set up logging
logger = logging.getLogger(__name__)

class SwitchConfiguration:
    """Class for switch configuration operations"""
    
    def __init__(self, connection: SwitchConnection):
        """
        Initialize with a switch connection.
        
        Args:
            connection: SwitchConnection object
        """
        self.connection = connection
    
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
            if not self.connection.enter_config_mode():
                return False
            
            # Log that we're applying base configuration
            logger.info(f"Applying base configuration to switch (length: {len(base_config)})")
            logger.info(f"Base config content: {base_config[:500]}...")  # Log first 500 chars
            if self.connection.debug and self.connection.debug_callback:
                self.connection.debug_callback("Applying base configuration", color="yellow")
            
            # Split the configuration into lines and run each command
            for line in base_config.strip().split('\n'):
                # Skip empty lines and comments
                line = line.strip()
                if not line or line.startswith('!'):
                    continue
                    
                # Run the command
                success, output = self.connection.run_command(line)
                if not success:
                    logger.error(f"Failed to execute base config command '{line}': {output}")
                    # We'll continue anyway to apply as much of the config as possible
            
            # Save configuration
            if not self.connection.exit_config_mode(save=True):
                return False
                
            logger.info("Successfully applied base configuration")
            return True
            
        except Exception as e:
            logger.error(f"Error applying base configuration: {e}", exc_info=True)
            self.connection.exit_config_mode(save=False)
            return False

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
            if not self.connection.enter_config_mode():
                return False
            
            # Set hostname
            success, output = self.connection.run_command(f"hostname {hostname}")
            if not success:
                logger.error(f"Failed to set hostname to {hostname}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Configure management interface
            success, output = self.connection.run_command(f"interface ve {mgmt_vlan}")
            if not success:
                logger.error(f"Failed to configure management interface ve {mgmt_vlan}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Set IP address
            success, output = self.connection.run_command(f"ip address {mgmt_ip} {mgmt_mask}")
            if not success:
                logger.error(f"Failed to set IP address {mgmt_ip} {mgmt_mask}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Enable interface
            success, output = self.connection.run_command("enable")
            if not success:
                logger.error(f"Failed to enable interface: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured basic switch settings: hostname={hostname}, mgmt_vlan={mgmt_vlan}, mgmt_ip={mgmt_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring basic switch settings: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
            return False

    def configure_switch_port(self, port: str) -> bool:
        """
        Configure a port connected to another switch as a trunk port.
        Uses vlan-config add all-tagged to tag all VLANs.
        Assumes VLANs have already been created.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.connection.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.connection.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Configure the port as a trunk with all VLANs
            success, output = self.connection.run_command("vlan-config add all-tagged")
            if not success:
                logger.error(f"Failed to add all VLANs as tagged to port {port}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} as switch trunk port with all VLANs tagged")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring switch port: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
            return False

    def configure_ap_port(self, port: str, wireless_vlans: List[int], management_vlan: int = 10) -> bool:
        """
        Configure a port connected to an Access Point.
        Tags specific VLANs needed for AP operation.
        Assumes VLANs have already been created.
        
        Args:
            port: Port name (e.g., '1/1/1').
            wireless_vlans: List of wireless VLAN IDs.
            management_vlan: Management VLAN ID for AP management.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Enter config mode
            if not self.connection.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.connection.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Add management VLAN to trunk
            success, output = self.connection.run_command(f"vlan-config add tagged-vlan {management_vlan}")
            if not success:
                logger.error(f"Failed to add management VLAN {management_vlan} to port {port}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Add wireless VLANs to trunk
            for vlan in wireless_vlans:
                success, output = self.connection.run_command(f"vlan-config add tagged-vlan {vlan}")
                if not success:
                    logger.error(f"Failed to add wireless VLAN {vlan} to port {port}: {output}")
                    self.connection.run_command("exit")  # Exit interface config
                    self.connection.exit_config_mode(save=False)
                    return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Configured port {port} for AP with wireless VLANs {wireless_vlans} and management VLAN {management_vlan}")
            return True
            
        except Exception as e:
            logger.error(f"Error configuring AP port: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
            return False

    def set_hostname(self) -> bool:
        """
        Set the switch hostname based on model and serial number.
        Format will be <model>-<serial>
        
        Returns:
            True if successful, False otherwise.
        """
        # Get model and serial if not already set
        if self.connection.model is None:
            self.connection.model = self.connection.get_model()
        
        if self.connection.serial is None:
            self.connection.serial = self.connection.get_serial()
        
        # Check if we have both
        if not self.connection.model or not self.connection.serial:
            logger.error(f"Failed to get model or serial number for switch {self.connection.ip}")
            return False
        
        # Format hostname
        hostname = f"{self.connection.model}-{self.connection.serial}"
        self.connection.hostname = hostname
        
        try:
            # Enter configuration mode
            if not self.connection.enter_config_mode():
                return False
            
            # Set hostname
            if self.connection.debug and self.connection.debug_callback:
                self.connection.debug_callback(f"Setting hostname to {hostname}", color="yellow")
                
            success, output = self.connection.run_command(f"hostname {hostname}", wait_time=1.0)
            if not success:
                logger.error(f"Failed to set hostname: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit config mode and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Set hostname for switch {self.connection.ip} to {hostname}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting hostname: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit config mode
            return False

    def get_port_status(self, port: str) -> Optional[PortStatus]:
        """
        Get port status.
        
        Args:
            port: Port name (e.g., '1/1/1').
            
        Returns:
            PortStatus or None if error.
        """
        success, output = self.connection.run_command(f"show interfaces {port} | include admin")
        
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
        success, output = self.connection.run_command(f"show interfaces {port} | include VLAN")
        
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
        success, output = self.connection.run_command(f"show inline power {port}")
        
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
            if not self.connection.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.connection.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Set VLAN for access port
            success, output = self.connection.run_command(f"vlan-config add untagged-vlan {vlan_id}")
            if not success:
                logger.error(f"Failed to set untagged VLAN {vlan_id} on port {port}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Changed port {port} VLAN to {vlan_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error changing port VLAN: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
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
            if not self.connection.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.connection.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Set status
            cmd = status.value
            success, output = self.connection.run_command(cmd)
            if not success:
                logger.error(f"Failed to set port {port} status to {status.value}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Set port {port} status to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting port status: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
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
            if not self.connection.enter_config_mode():
                return False
            
            # Configure port
            success, output = self.connection.run_command(f"interface ethernet {port}")
            if not success:
                logger.error(f"Failed to enter interface config mode for {port}: {output}")
                self.connection.exit_config_mode(save=False)
                return False
            
            # Set PoE status
            cmd = f"inline power {status.value}"
            success, output = self.connection.run_command(cmd)
            if not success:
                logger.error(f"Failed to set PoE status to {status.value} on port {port}: {output}")
                self.connection.run_command("exit")  # Exit interface config
                self.connection.exit_config_mode(save=False)
                return False
            
            # Exit interface config
            self.connection.run_command("exit")
            
            # Exit global config and save
            if not self.connection.exit_config_mode(save=True):
                return False
            
            logger.info(f"Set PoE status to {status.value} on port {port}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting PoE status: {e}", exc_info=True)
            self.connection.run_command("exit")  # Try to exit interface config
            self.connection.run_command("exit")  # Try to exit global config
            return False
