"""
Device information retrieval for RUCKUS ICX switches.
"""
import logging
import re
from typing import Optional

# Set up logging
logger = logging.getLogger(__name__)

class DeviceInfo:
    """Mixin class for retrieving device information."""
    
    def get_model(self) -> Optional[str]:
        """
        Get switch model from show version.
        
        Returns:
            Switch model string or None if not found.
        """
        if hasattr(self, 'model') and self.model:
            return self.model
            
        success, output = self.run_command("show version")
        
        if not success:
            logger.error(f"Failed to get version info from switch {self.ip}")
            return None
        
        # Parse model from output
        # Example: "RUCKUS ICX7250-48P Router"
        model_match = re.search(r'RUCKUS\s+(ICX\S+)', output, re.IGNORECASE)
        if model_match:
            self.model = model_match.group(1)
            logger.debug(f"Detected model {self.model} for switch {self.ip}")
            return self.model
        
        # Pattern for ICX8200 format: "HW: Stackable ICX8200-C08PF-POE"
        model_match = re.search(r'HW:\s+Stackable\s+(ICX\S+)', output, re.IGNORECASE)
        if model_match:
            self.model = model_match.group(1)
            logger.debug(f"Detected model {self.model} for switch {self.ip}")
            return self.model
        
        # Alternative pattern
        model_match = re.search(r'System\s+Type:\s*(\S+)', output, re.IGNORECASE)
        if model_match:
            self.model = model_match.group(1)
            logger.debug(f"Detected model {self.model} for switch {self.ip}")
            return self.model
        
        logger.warning(f"Could not detect model for switch {self.ip}")
        return None
    
    def get_serial(self) -> Optional[str]:
        """
        Get switch serial number from show version.
        
        Returns:
            Serial number string or None if not found.
        """
        if hasattr(self, 'serial') and self.serial:
            return self.serial
            
        success, output = self.run_command("show version")
        
        if not success:
            logger.error(f"Failed to get version info from switch {self.ip}")
            return None
        
        # Parse serial from output
        # Example: "Serial Number: ABC123456789"
        serial_match = re.search(r'Serial\s+Number:\s*(\S+)', output, re.IGNORECASE)
        if serial_match:
            self.serial = serial_match.group(1)
            logger.debug(f"Detected serial {self.serial} for switch {self.ip}")
            return self.serial
        
        # Alternative pattern
        serial_match = re.search(r'Serial\s*#?\s*:\s*(\S+)', output, re.IGNORECASE)
        if serial_match:
            self.serial = serial_match.group(1)
            logger.debug(f"Detected serial {self.serial} for switch {self.ip}")
            return self.serial
        
        logger.warning(f"Could not detect serial number for switch {self.ip}")
        return None
    
    def get_chassis_mac(self) -> Optional[str]:
        """
        Get switch MAC address from show chassis.
        
        Returns:
            Chassis MAC address or None if not found.
        """
        if hasattr(self, 'chassis_mac') and self.chassis_mac:
            return self.chassis_mac
            
        success, output = self.run_command("show chassis | include Management")
        
        if not success:
            logger.error(f"Failed to get chassis info from switch {self.ip}")
            return None
            
        # Parse for management MAC
        # Example: Management MAC: 94b3.4f30.4788
        mac_match = re.search(r'Management MAC:\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})', output)
        
        if mac_match:
            self.chassis_mac = mac_match.group(1).lower()  # Normalize to lowercase
            logger.debug(f"Detected chassis MAC {self.chassis_mac} for switch {self.ip}")
            return self.chassis_mac
            
        logger.warning(f"Could not detect chassis MAC for switch {self.ip}")
        return None
    
    def get_firmware_version(self) -> Optional[str]:
        """
        Get firmware version from show version.
        
        Returns:
            Firmware version string or None if not found.
        """
        success, output = self.run_command("show version")
        
        if not success:
            logger.error(f"Failed to get version info from switch {self.ip}")
            return None
        
        # Parse firmware version
        # Example: "SW: Version 08.0.95hT213"
        version_match = re.search(r'SW:\s*Version\s+(\S+)', output, re.IGNORECASE)
        if version_match:
            version = version_match.group(1)
            logger.debug(f"Detected firmware version {version} for switch {self.ip}")
            return version
        
        # Alternative pattern
        version_match = re.search(r'Software\s+Version:\s*(\S+)', output, re.IGNORECASE)
        if version_match:
            version = version_match.group(1)
            logger.debug(f"Detected firmware version {version} for switch {self.ip}")
            return version
        
        logger.warning(f"Could not detect firmware version for switch {self.ip}")
        return None
    
    def get_uptime(self) -> Optional[str]:
        """
        Get system uptime.
        
        Returns:
            Uptime string or None if not found.
        """
        success, output = self.run_command("show version")
        
        if not success:
            logger.error(f"Failed to get version info from switch {self.ip}")
            return None
        
        # Parse uptime
        # Example: "System uptime is 2 days 3 hours 45 minutes"
        uptime_match = re.search(r'uptime\s+is\s+(.+?)(?:\n|$)', output, re.IGNORECASE)
        if uptime_match:
            uptime = uptime_match.group(1).strip()
            logger.debug(f"Detected uptime {uptime} for switch {self.ip}")
            return uptime
        
        logger.warning(f"Could not detect uptime for switch {self.ip}")
        return None
    
    def get_hostname(self) -> Optional[str]:
        """
        Get switch hostname from running configuration or prompt.
        
        Returns:
            Hostname string or None if not found.
        """
        if hasattr(self, 'hostname') and self.hostname:
            return self.hostname
            
        # First try to get hostname from running config
        success, output = self.run_command("show running-config | include hostname")
        
        if success and output.strip():
            # Parse hostname from output
            # Example: "hostname ICX8200-C08PF-POE-FNS4352T0D4"
            hostname_match = re.search(r'hostname\s+(\S+)', output, re.IGNORECASE)
            if hostname_match:
                hostname = hostname_match.group(1)
                # Clean up any SSH@ prefix that might be in the configured hostname
                if hostname.startswith('SSH@'):
                    hostname = hostname[4:]  # Remove 'SSH@' prefix
                self.hostname = hostname
                logger.debug(f"Detected hostname {self.hostname} from config for switch {self.ip}")
                return self.hostname
        
        # If no hostname in config, try to extract from prompt
        # The prompt format is typically: SSH@HOSTNAME# or similar
        # First, try to get the prompt directly from the connection
        if hasattr(self, 'connection') and hasattr(self.connection, 'prompt'):
            prompt = self.connection.prompt
            if prompt:
                # Extract hostname from prompt like "SSH@ICX8200-C08PF-POE-FNS4352T0D4#"
                # Handle both SSH@hostname and avoid capturing SSH@ in the hostname
                prompt_match = re.search(r'SSH@([^#\$>\s]+)[#\$>]', prompt)
                if not prompt_match:
                    # Fallback for other prompt formats
                    prompt_match = re.search(r'[@]([^@#\$>\s]+)[#\$>]', prompt)
                if prompt_match:
                    hostname = prompt_match.group(1)
                    # Clean up any remaining SSH@ prefixes that might have been captured
                    if hostname.startswith('SSH@'):
                        hostname = hostname[4:]  # Remove 'SSH@' prefix
                    self.hostname = hostname
                    logger.debug(f"Detected hostname {self.hostname} from current prompt for switch {self.ip}")
                    return self.hostname
        
        # Fallback: run a simple command to see the prompt
        success, output = self.run_command("")  # Empty command just to see prompt
        if success:
            logger.debug(f"Prompt detection output for {self.ip}: {repr(output)}")
            # The output might contain the prompt
            lines = output.strip().split('\n')
            if lines:
                last_line = lines[-1]
                logger.debug(f"Last line for prompt detection {self.ip}: {repr(last_line)}")
                # Look for hostname pattern in the last line
                # Handle both SSH@hostname and avoid capturing SSH@ in the hostname
                prompt_match = re.search(r'SSH@([^#\$>\s]+)[#\$>]', last_line)
                if not prompt_match:
                    # Fallback for other prompt formats
                    prompt_match = re.search(r'[@]([^@#\$>\s]+)[#\$>]', last_line)
                if prompt_match:
                    hostname = prompt_match.group(1)
                    logger.debug(f"Raw hostname from prompt for {self.ip}: {repr(hostname)}")
                    # Clean up any remaining SSH@ prefixes that might have been captured
                    if hostname.startswith('SSH@'):
                        logger.warning(f"Found SSH@ prefix in prompt hostname for {self.ip}: {hostname}")
                        hostname = hostname[4:]  # Remove 'SSH@' prefix
                    self.hostname = hostname
                    logger.debug(f"Detected hostname {self.hostname} from command output for switch {self.ip}")
                    return self.hostname
        
        logger.debug(f"No hostname found for switch {self.ip}")
        return None