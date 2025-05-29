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