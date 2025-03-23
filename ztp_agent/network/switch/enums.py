"""
Enumeration classes for switch operations.
"""
from enum import Enum

class PortStatus(str, Enum):
    """Port administrative status"""
    ENABLE = "enable"
    DISABLE = "disable"

class PoEStatus(str, Enum):
    """PoE status"""
    ENABLED = "enabled"
    DISABLED = "disabled"