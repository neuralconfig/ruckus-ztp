"""
Switch operations package for interacting with RUCKUS ICX switches.
"""
from enum import Enum

# Re-export classes and functions from submodules
from ztp_agent.network.switch.connection import SwitchOperation
from ztp_agent.network.switch.enums import PortStatus, PoEStatus

# Import and attach configuration methods
from ztp_agent.network.switch.configuration import (
    apply_base_config,
    configure_vlans,
    configure_switch_basic,
    configure_switch_port,
    configure_trunk_port,
    configure_ap_port,
    set_hostname,
    change_port_vlan,
    set_port_status,
    get_port_status,
    get_port_vlan,
    get_poe_status,
    set_poe_status
)

# Monkey patch configuration methods to SwitchOperation class
SwitchOperation.apply_base_config = apply_base_config
SwitchOperation.configure_vlans = configure_vlans
SwitchOperation.configure_switch_basic = configure_switch_basic
SwitchOperation.configure_switch_port = configure_switch_port
SwitchOperation.configure_trunk_port = configure_trunk_port
SwitchOperation.configure_ap_port = configure_ap_port
SwitchOperation.set_hostname = set_hostname
SwitchOperation.change_port_vlan = change_port_vlan
SwitchOperation.set_port_status = set_port_status
SwitchOperation.get_port_status = get_port_status
SwitchOperation.get_port_vlan = get_port_vlan
SwitchOperation.get_poe_status = get_poe_status
SwitchOperation.set_poe_status = set_poe_status

# Import and attach discovery methods
from ztp_agent.network.switch.discovery import get_lldp_neighbors, get_l2_trace_data
SwitchOperation.get_lldp_neighbors = get_lldp_neighbors
SwitchOperation.get_l2_trace_data = get_l2_trace_data

__all__ = ['SwitchOperation', 'PortStatus', 'PoEStatus']