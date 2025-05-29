"""
Switch operations package for interacting with RUCKUS ICX switches.
"""
# Import the base classes
from ztp_agent.network.switch.base import SwitchConnection
from ztp_agent.network.switch.enums import PortStatus, PoEStatus
from ztp_agent.network.switch.configuration import SwitchConfiguration
from ztp_agent.network.switch.discovery import SwitchDiscovery

# Import the facade for backward compatibility
from ztp_agent.network.switch.facade import SwitchOperation

# Create function wrappers for use in facade class
def apply_base_config(self, base_config: str) -> bool:
    """Wrapper for SwitchConfiguration.apply_base_config"""
    config = SwitchConfiguration(self.connection)
    return config.apply_base_config(base_config)

def configure_switch_basic(self, hostname: str, mgmt_vlan: int, mgmt_ip: str, mgmt_mask: str) -> bool:
    """Wrapper for SwitchConfiguration.configure_switch_basic"""
    config = SwitchConfiguration(self.connection)
    return config.configure_switch_basic(hostname, mgmt_vlan, mgmt_ip, mgmt_mask)

def configure_switch_port(self, port: str) -> bool:
    """Wrapper for SwitchConfiguration.configure_switch_port"""
    config = SwitchConfiguration(self.connection)
    return config.configure_switch_port(port)

def configure_ap_port(self, port: str, wireless_vlans: list, management_vlan: int = 10) -> bool:
    """Wrapper for SwitchConfiguration.configure_ap_port"""
    config = SwitchConfiguration(self.connection)
    return config.configure_ap_port(port, wireless_vlans, management_vlan)

def set_hostname(self) -> bool:
    """Wrapper for SwitchConfiguration.set_hostname"""
    config = SwitchConfiguration(self.connection)
    return config.set_hostname()

def change_port_vlan(self, port: str, vlan_id: int) -> bool:
    """Wrapper for SwitchConfiguration.change_port_vlan"""
    config = SwitchConfiguration(self.connection)
    return config.change_port_vlan(port, vlan_id)

def set_port_status(self, port: str, status: PortStatus) -> bool:
    """Wrapper for SwitchConfiguration.set_port_status"""
    config = SwitchConfiguration(self.connection)
    return config.set_port_status(port, status)

def get_port_status(self, port: str) -> PortStatus:
    """Wrapper for SwitchConfiguration.get_port_status"""
    config = SwitchConfiguration(self.connection)
    return config.get_port_status(port)

def get_port_vlan(self, port: str) -> int:
    """Wrapper for SwitchConfiguration.get_port_vlan"""
    config = SwitchConfiguration(self.connection)
    return config.get_port_vlan(port)

def get_poe_status(self, port: str) -> PoEStatus:
    """Wrapper for SwitchConfiguration.get_poe_status"""
    config = SwitchConfiguration(self.connection)
    return config.get_poe_status(port)

def set_poe_status(self, port: str, status: PoEStatus) -> bool:
    """Wrapper for SwitchConfiguration.set_poe_status"""
    config = SwitchConfiguration(self.connection)
    return config.set_poe_status(port, status)

def get_lldp_neighbors(self) -> tuple:
    """Wrapper for SwitchDiscovery.get_lldp_neighbors"""
    discovery = SwitchDiscovery(self.connection)
    return discovery.get_lldp_neighbors()

def get_l2_trace_data(self) -> tuple:
    """Wrapper for SwitchDiscovery.get_l2_trace_data"""
    discovery = SwitchDiscovery(self.connection)
    return discovery.get_l2_trace_data()

# Monkey patch methods to SwitchOperation class
SwitchOperation.apply_base_config = apply_base_config
SwitchOperation.configure_switch_basic = configure_switch_basic
SwitchOperation.configure_switch_port = configure_switch_port
SwitchOperation.configure_ap_port = configure_ap_port
SwitchOperation.set_hostname = set_hostname
SwitchOperation.change_port_vlan = change_port_vlan
SwitchOperation.set_port_status = set_port_status
SwitchOperation.get_port_status = get_port_status
SwitchOperation.get_port_vlan = get_port_vlan
SwitchOperation.get_poe_status = get_poe_status
SwitchOperation.set_poe_status = set_poe_status
SwitchOperation.get_lldp_neighbors = get_lldp_neighbors
SwitchOperation.get_l2_trace_data = get_l2_trace_data

# For backward compatibility with original imports
__all__ = ['SwitchOperation', 'SwitchConnection', 'SwitchConfiguration', 'SwitchDiscovery', 'PortStatus', 'PoEStatus']
