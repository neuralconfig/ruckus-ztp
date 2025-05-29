"""
Switch operations package for interacting with RUCKUS ICX switches.

This package provides a clean, modular approach to switch operations using
proper inheritance instead of monkey patching.
"""

# Re-export main classes
from ztp_agent.network.switch.operation import SwitchOperation
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Import configuration functions to attach as methods
from ztp_agent.network.switch.configuration import (
    apply_base_config,
    configure_switch_basic,
    configure_switch_port,
    configure_ap_port,
    set_hostname,
    change_port_vlan,
    set_port_status,
    get_port_status,
    get_port_vlan,
    get_poe_status,
    set_poe_status
)

# Import discovery functions to attach as methods
from ztp_agent.network.switch.discovery import get_lldp_neighbors, get_l2_trace_data

# Attach configuration methods to SwitchOperation class
# Note: These functions expect 'self' as first parameter but are defined as module functions
# that take a connection object. We create wrapper methods that pass 'self' as the connection.

def _create_config_method(func):
    """Create a method that passes self as the connection parameter."""
    def method(self, *args, **kwargs):
        return func(self, *args, **kwargs)
    return method

def _create_discovery_method(func):
    """Create a method that passes self as the connection parameter."""
    def method(self, *args, **kwargs):
        return func(self, *args, **kwargs)
    return method

# Attach configuration methods
SwitchOperation.apply_base_config = _create_config_method(apply_base_config)
SwitchOperation.configure_switch_basic = _create_config_method(configure_switch_basic)
SwitchOperation.configure_switch_port = _create_config_method(configure_switch_port)
SwitchOperation.configure_ap_port = _create_config_method(configure_ap_port)
SwitchOperation.set_hostname = _create_config_method(set_hostname)
SwitchOperation.change_port_vlan = _create_config_method(change_port_vlan)
SwitchOperation.set_port_status = _create_config_method(set_port_status)
SwitchOperation.get_port_status = _create_config_method(get_port_status)
SwitchOperation.get_port_vlan = _create_config_method(get_port_vlan)
SwitchOperation.get_poe_status = _create_config_method(get_poe_status)
SwitchOperation.set_poe_status = _create_config_method(set_poe_status)

# Attach discovery methods
SwitchOperation.get_lldp_neighbors = _create_discovery_method(get_lldp_neighbors)
SwitchOperation.get_l2_trace_data = _create_discovery_method(get_l2_trace_data)

__all__ = ['SwitchOperation', 'PortStatus', 'PoEStatus']