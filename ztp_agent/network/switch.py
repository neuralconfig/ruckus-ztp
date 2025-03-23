"""
Switch operations module for interacting with RUCKUS ICX switches.
This module is now a facade that imports from the modular subpackage.
"""
from ztp_agent.network.switch.connection import SwitchOperation
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

__all__ = ['SwitchOperation', 'PortStatus', 'PoEStatus']