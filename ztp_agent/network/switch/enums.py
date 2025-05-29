"""
Enumerations for switch operations.
"""
from enum import Enum

class PortStatus(Enum):
    """Port status enumeration"""
    ENABLE = "enable"
    DISABLE = "disable"

class PoEStatus(Enum):
    """PoE status enumeration"""
    ENABLED = "enable"
    DISABLED = "disable"
