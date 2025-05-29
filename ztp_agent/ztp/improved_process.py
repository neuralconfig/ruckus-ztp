"""
Improved ZTP (Zero Touch Provisioning) process implementation.
This implementation uses proper state management.
"""
import logging
import threading
import time
import re
import ipaddress
from typing import Dict, List, Any, Optional

from ztp_agent.network.switch import SwitchOperation, SwitchConnection, SwitchConfiguration, SwitchDiscovery
from ztp_agent.network.switch.state import SwitchState, StateManager

# Set up logging
logger = logging.getLogger(__name__)

class ImprovedZTPProcess:
    """
    Improved handler for the ZTP process for RUCKUS devices.
    Uses proper state management and clear separation of concerns.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the ZTP process.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        self.running = False
        self.thread = None
        
        # Initialize state manager
        self.state_manager = StateManager()
        
        # Store inventory for backward compatibility
        self.inventory = {
            'switches': {},
            'aps': {}
        }
        
        # Get network configuration
        network_config = config.get('network', {})
        
        # Get base configuration
        self.base_config = network_config.get('base_config', '')
        
        # Get VLAN configurations
        self.mgmt_vlan = network_config.get('management_vlan', 10)
        self.wireless_vlans = network_config.get('wireless_vlans', [20, 30, 40])
        
        # Set up IP address management
        self.ip_pool = network_config.get('ip_pool', '192.168.10.0/24')
        self.gateway = network_config.get('gateway', '192.168.10.1')
        self.next_ip_index = 10  # Start assigning from .10
        
        # Debug settings
        self.debug = config.get('debug', False)
        self.debug_callback = config.get('debug_callback', None)
        
        logger.info("Initialized improved ZTP process")
    
    def add_switch(self, ip: str, username: str, password: str, preferred_password: str = None, 
                  debug: bool = None, debug_callback = None) -> bool:
        """
        Add a switch to the inventory.
        
        Args:
            ip: IP address of the switch.
            username: Username for switch access.
            password: Password for switch access.
            preferred_password: Password to set during first-time login.
            debug: Whether to enable debug mode for this switch.
            debug_callback: Function to call with debug messages.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Validate IP
            ipaddress.IPv4Address(ip)
            
            # Use module-level debug settings if not provided
            if debug is None:
                debug = self.debug
            if debug_callback is None and self.debug_callback:
                debug_callback = self.debug_callback
            
            # Create switch connection to test
            connection = SwitchConnection(
                ip=ip,
                username=username,
                password=password,
                timeout=30,
                preferred_password=preferred_password,
                debug=debug,
                debug_callback=debug_callback
            )
            
            # Test connection
            if not connection.connect():
                logger.error(f"Failed to connect to switch {ip}")
                return False
            
            # Get model and serial number
            model = connection.model
            serial = connection.serial
            hostname = connection.hostname
            
            # Add to inventory (for backward compatibility)
            self.inventory['switches'][ip] = {
                'ip': ip,
                'username': username,
                'password': password,
                'preferred_password': preferred_password,
                'model': model,
                'serial': serial,
                'hostname': hostname,
                'status': 'Connected',
                'configured': False,
                'base_config_applied': False,
                'neighbors': {},
                'ports': {}
            }
            
            # Add to state manager
            self.state_manager.add_switch(
                ip=ip,
                initial_state=SwitchState.DISCOVERED,
                metadata={
                    'username': username,
                    'password': password,
                    'preferred_password': preferred_password,
                    'model': model,
                    'serial': serial,
                    'hostname': hostname,
                    'debug': debug,
                    'debug_callback': debug_callback
                }
            )
            
            # Disconnect
            connection.disconnect()
            
            logger.info(f"Added switch {ip} to inventory (Model: {model}, Serial: {serial})")
            return True
        
        except ValueError:
            logger.error(f"Invalid IP address: {ip}")
            return False
        except Exception as e:
            logger.error(f"Error adding switch {ip}: {e}", exc_info=True)
            return False
    
    def get_switch_info(self, ip: str) -> Dict[str, Any]:
        """
        Get information about a switch.
        
        Args:
            ip: IP address of the switch.
            
        Returns:
            Dictionary with switch information.
        """
        metadata = self.state_manager.get_metadata(ip)
        state = self.state_manager.get_state(ip)
        
        if not metadata or not state:
            return {}
        
        return {
            'ip': ip,
            'model': metadata.get('model'),
            'serial': metadata.get('serial'),
            'hostname': metadata.get('hostname'),
            'status': state.value,
            'configured': state == SwitchState.FULLY_CONFIGURED
        }
    
    def start(self) -> bool:
        """
        Start the ZTP process.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self.running:
            logger.warning("ZTP process already running")
            return False
        
        # Check if we have any switches
        if not self.state_manager.switches:
            logger.error("No switches configured, cannot start ZTP process")
            return False
        
        try:
            # Set running flag
            self.running = True
            
            # Start in a separate thread
            self.thread = threading.Thread(target=self._run_process)
            self.thread.daemon = True
            self.thread.start()
            
            logger.info("Started ZTP process")
            return True
        
        except Exception as e:
            logger.error(f"Error starting ZTP process: {e}", exc_info=True)
            self.running = False
            return False
    
    def stop(self) -> bool:
        """
        Stop the ZTP process.
        
        Returns:
            True if stopped successfully, False otherwise.
        """
        if not self.running:
            logger.warning("ZTP process not running")
            return False
        
        try:
            # Set running flag to false
            self.running = False
            
            # Wait for thread to exit (with timeout)
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5.0)
            
            logger.info("Stopped ZTP process")
            return True
        
        except Exception as e:
            logger.error(f"Error stopping ZTP process: {e}", exc_info=True)
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of the ZTP process.
        
        Returns:
            Dictionary with status information.
        """
        # Count switches in each state
        state_counts = {}
        for state in SwitchState:
            switches = self.state_manager.get_switches_by_state(state)
            state_counts[state.value] = len(switches)
        
        return {
            'running': self.running,
            'switches': len(self.state_manager.switches),
            'aps': len(self.inventory['aps']),  # TODO: Implement AP state management
            'switch_states': state_counts,
            'fully_configured': state_counts.get(SwitchState.FULLY_CONFIGURED.value, 0),
            'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _run_process(self) -> None:
        """
        Main ZTP process loop with clear separation of concerns.
        
        This method runs in a separate thread.
        """
        logger.info("ZTP process thread started")
        
        poll_interval = self.config.get('ztp', {}).get('poll_interval', 60)  # seconds
        
        try:
            while self.running:
                try:
                    # Step 1: Discover new devices
                    self._discover_devices()
                    
                    # Step 2: Apply base configuration to newly discovered switches
                    self._apply_base_configurations()
                    
                    # Step 3: Configure management interfaces
                    self._configure_management_interfaces()
                    
                    # Step 4: Configure ports
                    self._configure_ports()
                    
                    # Step 5: Update inventory for backward compatibility
                    self._update_inventory()
                    
                except Exception as e:
                    logger.error(f"Error in ZTP process loop: {e}", exc_info=True)
                
                # Sleep for the poll interval
                for _ in range(poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            
            logger.info("ZTP process thread exiting")
        
        except Exception as e:
            logger.error(f"Unhandled error in ZTP process thread: {e}", exc_info=True)
            self.running = False
    
    def _discover_devices(self) -> None:
        """
        Discover devices using LLDP neighbors.
        
        This method connects to each configured switch and retrieves
        LLDP neighbors to discover new devices.
        """
        logger.debug("Running device discovery")
        
        # Get all switches that are at least in DISCOVERED state
        for ip, data in self.state_manager.switches.items():
            try:
                metadata = data['metadata']
                
                # Create switch connection
                connection = SwitchConnection(
                    ip=ip,
                    username=metadata['username'],
                    password=metadata['password'],
                    preferred_password=metadata.get('preferred_password'),
                    debug=metadata.get('debug', False),
                    debug_callback=metadata.get('debug_callback')
                )
                
                # Connect to switch
                if not connection.connect():
                    logger.error(f"Failed to connect to switch {ip}")
                    continue
                
                # Create discovery instance
                discovery = SwitchDiscovery(connection)
                
                # Get LLDP neighbors
                success, neighbors = discovery.get_lldp_neighbors()
                
                # Disconnect from switch
                connection.disconnect()
                
                if not success:
                    logger.error(f"Failed to get LLDP neighbors from switch {ip}")
                    continue
                
                # Store neighbors in metadata
                self.state_manager.update_metadata(ip, 'neighbors', neighbors)
                
                # Process neighbors to discover new devices
                for port, neighbor in neighbors.items():
                    # Process switch neighbors
                    if neighbor['type'] == 'switch':
                        neighbor_ip = neighbor.get('mgmt_address')
                        
                        # Skip if we don't have a valid IP address
                        if not neighbor_ip or neighbor_ip == '0.0.0.0':
                            continue
                            
                        # Skip if this switch is already in our inventory
                        if neighbor_ip in self.state_manager.switches:
                            continue
                            
                        # Extract information from neighbor
                        system_name = neighbor.get('system_name', '')
                        system_description = neighbor.get('system_description', '')
                        
                        # Extract model from system description if possible
                        model = None
                        if system_description:
                            model_match = re.search(r'ICX\d+[a-zA-Z0-9\-]+(?:-POE)?', system_description)
                            if model_match:
                                model = model_match.group(0)
                        
                        # Add the switch to our state manager
                        self.state_manager.add_switch(
                            ip=neighbor_ip,
                            initial_state=SwitchState.DISCOVERED,
                            metadata={
                                'username': metadata['username'],
                                'password': metadata['password'],
                                'preferred_password': metadata.get('preferred_password'),
                                'model': model,
                                'hostname': system_name or f"switch-{neighbor_ip.replace('.', '-')}",
                                'debug': metadata.get('debug', False),
                                'debug_callback': metadata.get('debug_callback'),
                                'discovered_from': {
                                    'switch_ip': ip,
                                    'port': port
                                }
                            }
                        )
                        
                        # Update inventory for backward compatibility
                        self.inventory['switches'][neighbor_ip] = {
                            'ip': neighbor_ip,
                            'username': metadata['username'],
                            'password': metadata['password'],
                            'preferred_password': metadata.get('preferred_password'),
                            'model': model,
                            'hostname': system_name or f"switch-{neighbor_ip.replace('.', '-')}",
                            'status': 'Discovered',
                            'configured': False,
                            'base_config_applied': False,
                            'neighbors': {},
                            'ports': {},
                            'discovered_from': {
                                'switch_ip': ip,
                                'port': port
                            }
                        }
                        
                        logger.info(f"Discovered new switch {neighbor_ip} via {ip}:{port}")
                    
                    # Process AP neighbors
                    elif neighbor['type'] == 'ap':
                        ap_ip = neighbor.get('mgmt_address')
                        
                        # Skip if we don't have a valid IP address
                        if not ap_ip or ap_ip == '0.0.0.0':
                            continue
                            
                        # Skip if this AP is already in our inventory
                        if ap_ip in self.inventory['aps']:
                            continue
                            
                        # Extract information from neighbor
                        system_name = neighbor.get('system_name', '')
                        chassis_id = neighbor.get('chassis_id', 'unknown')
                        
                        # Add the AP to our inventory
                        self.inventory['aps'][ap_ip] = {
                            'ip': ap_ip,
                            'mac': chassis_id,
                            'system_name': system_name,
                            'hostname': system_name or f"ap-{ap_ip.replace('.', '-')}",
                            'status': 'Discovered',
                            'connected_to': {
                                'switch_ip': ip,
                                'port': port
                            }
                        }
                        
                        # Store port connection info in switch metadata
                        ports = metadata.get('ports', {})
                        ports[port] = {
                            'type': 'ap',
                            'device_ip': ap_ip,
                            'configured': False
                        }
                        self.state_manager.update_metadata(ip, 'ports', ports)
                        
                        logger.info(f"Discovered new AP {ap_ip} via {ip}:{port}")
                
                # Log total discoveries
                switch_count = sum(1 for n in neighbors.values() if n.get('type') == 'switch')
                ap_count = sum(1 for n in neighbors.values() if n.get('type') == 'ap')
                logger.info(f"Discovered {switch_count} switches and {ap_count} APs on switch {ip}")
                
            except Exception as e:
                logger.error(f"Error discovering devices on switch {ip}: {e}", exc_info=True)
    
    def _apply_base_configurations(self) -> None:
        """
        Apply base configuration to switches in DISCOVERED state.
        
        This method applies the base configuration (VLAN setup, etc.)
        to switches that are in the DISCOVERED state.
        """
        logger.debug("Applying base configurations")
        
        # Get switches in DISCOVERED state
        discovered_switches = self.state_manager.get_switches_by_state(SwitchState.DISCOVERED)
        
        for ip, data in discovered_switches.items():
            try:
                metadata = data['metadata']
                
                logger.info(f"Applying base configuration to switch {ip}")
                
                # Create switch connection
                connection = SwitchConnection(
                    ip=ip,
                    username=metadata['username'],
                    password=metadata['password'],
                    preferred_password=metadata.get('preferred_password'),
                    debug=metadata.get('debug', False),
                    debug_callback=metadata.get('debug_callback')
                )
                
                # Connect to switch
                if not connection.connect():
                    logger.error(f"Failed to connect to switch {ip} for base configuration")
                    continue
                
                # Create configuration instance
                config = SwitchConfiguration(connection)
                
                # Apply base configuration
                success = config.apply_base_config(self.base_config)
                
                # Disconnect from switch
                connection.disconnect()
                
                if success:
                    logger.info(f"Successfully applied base configuration to switch {ip}")
                    
                    # Transition to next state
                    self.state_manager.transition_to(
                        ip=ip,
                        new_state=SwitchState.BASE_CONFIG_APPLIED,
                        reason="Base configuration applied successfully"
                    )
                    
                    # Update inventory for backward compatibility
                    self.inventory['switches'][ip]['base_config_applied'] = True
                else:
                    logger.error(f"Failed to apply base configuration to switch {ip}")
                    
                    # Transition to error state
                    self.state_manager.transition_to(
                        ip=ip,
                        new_state=SwitchState.ERROR,
                        reason="Failed to apply base configuration"
                    )
                
            except Exception as e:
                logger.error(f"Error applying base configuration to switch {ip}: {e}", exc_info=True)
                
                # Transition to error state
                self.state_manager.transition_to(
                    ip=ip,
                    new_state=SwitchState.ERROR,
                    reason=f"Error applying base configuration: {str(e)}"
                )
    
    def _configure_management_interfaces(self) -> None:
        """
        Configure management interfaces on switches in BASE_CONFIG_APPLIED state.
        
        This method configures management IP addresses, hostnames, etc.
        on switches that already have the base configuration applied.
        """
        logger.debug("Configuring management interfaces")
        
        # Get switches in BASE_CONFIG_APPLIED state
        base_configured_switches = self.state_manager.get_switches_by_state(SwitchState.BASE_CONFIG_APPLIED)
        
        for ip, data in base_configured_switches.items():
            try:
                metadata = data['metadata']
                
                logger.info(f"Configuring management interface on switch {ip}")
                
                # Create switch connection
                connection = SwitchConnection(
                    ip=ip,
                    username=metadata['username'],
                    password=metadata['password'],
                    preferred_password=metadata.get('preferred_password'),
                    debug=metadata.get('debug', False),
                    debug_callback=metadata.get('debug_callback')
                )
                
                # Connect to switch
                if not connection.connect():
                    logger.error(f"Failed to connect to switch {ip} for management configuration")
                    continue
                
                # Create configuration instance
                config = SwitchConfiguration(connection)
                
                # Get model and serial
                model = metadata.get('model') or connection.model
                serial = metadata.get('serial') or connection.serial
                hostname = metadata.get('hostname') or f"{model}-{serial}"
                
                # Generate management IP from pool
                try:
                    # Parse the IP pool
                    network = ipaddress.IPv4Network(self.ip_pool)
                    mgmt_mask = str(network.netmask)
                    
                    # Calculate the next available IP
                    mgmt_ip = str(network.network_address + self.next_ip_index)
                    
                    # Check if IP is valid (not network or broadcast)
                    if (network.network_address + self.next_ip_index) not in [network.network_address, network.broadcast_address]:
                        # Increment counter for next device
                        self.next_ip_index += 1
                        logger.info(f"Assigned management IP {mgmt_ip} from pool to switch {ip}")
                    else:
                        # If invalid, use a default approach
                        logger.warning(f"IP pool exhausted, using existing IP {ip} for management")
                        mgmt_ip = ip
                except Exception as e:
                    # Fallback to existing IP if there's any error with the pool
                    logger.error(f"Error allocating IP from pool: {e}. Using existing IP {ip}")
                    mgmt_ip = ip
                    mgmt_mask = "255.255.255.0"  # Default mask
                
                # Configure basic switch settings
                success = config.configure_switch_basic(
                    hostname=hostname,
                    mgmt_vlan=self.mgmt_vlan,
                    mgmt_ip=mgmt_ip,
                    mgmt_mask=mgmt_mask
                )
                
                # Disconnect from switch
                connection.disconnect()
                
                if success:
                    logger.info(f"Successfully configured management interface on switch {ip}")
                    
                    # Update metadata
                    self.state_manager.update_metadata(ip, 'mgmt_ip', mgmt_ip)
                    self.state_manager.update_metadata(ip, 'mgmt_mask', mgmt_mask)
                    
                    # Transition to next state
                    self.state_manager.transition_to(
                        ip=ip,
                        new_state=SwitchState.MANAGEMENT_CONFIGURED,
                        reason="Management interface configured successfully"
                    )
                    
                    # Update inventory for backward compatibility
                    self.inventory['switches'][ip]['configured'] = True
                    self.inventory['switches'][ip]['status'] = 'Configured'
                else:
                    logger.error(f"Failed to configure management interface on switch {ip}")
                    
                    # Transition to error state
                    self.state_manager.transition_to(
                        ip=ip,
                        new_state=SwitchState.ERROR,
                        reason="Failed to configure management interface"
                    )
                
            except Exception as e:
                logger.error(f"Error configuring management interface on switch {ip}: {e}", exc_info=True)
                
                # Transition to error state
                self.state_manager.transition_to(
                    ip=ip,
                    new_state=SwitchState.ERROR,
                    reason=f"Error configuring management interface: {str(e)}"
                )
    
    def _configure_ports(self) -> None:
        """
        Configure ports on switches in MANAGEMENT_CONFIGURED state.
        
        This method configures ports for interswitch connections and AP connections
        on switches that already have management interfaces configured.
        """
        logger.debug("Configuring switch ports")
        
        # Get switches in MANAGEMENT_CONFIGURED state
        mgmt_configured_switches = self.state_manager.get_switches_by_state(SwitchState.MANAGEMENT_CONFIGURED)
        
        for ip, data in mgmt_configured_switches.items():
            try:
                metadata = data['metadata']
                neighbors = metadata.get('neighbors', {})
                
                logger.info(f"Configuring ports on switch {ip}")
                
                # Create switch connection
                connection = SwitchConnection(
                    ip=ip,
                    username=metadata['username'],
                    password=metadata['password'],
                    preferred_password=metadata.get('preferred_password'),
                    debug=metadata.get('debug', False),
                    debug_callback=metadata.get('debug_callback')
                )
                
                # Connect to switch
                if not connection.connect():
                    logger.error(f"Failed to connect to switch {ip} for port configuration")
                    continue
                
                # Create configuration instance
                config = SwitchConfiguration(connection)
                
                # Configure switch ports based on LLDP neighbors
                all_ports_configured = True
                
                for port, neighbor in neighbors.items():
                    try:
                        # Skip already configured ports
                        if metadata.get('ports', {}).get(port, {}).get('configured', False):
                            continue
                        
                        # Configure port based on neighbor type
                        if neighbor['type'] == 'switch':
                            # Configure switch port - tag all VLANs
                            success = config.configure_switch_port(port)
                            
                            if success:
                                logger.info(f"Configured port {port} on switch {ip} as trunk for neighbor switch")
                                
                                # Store port configuration in metadata
                                ports = metadata.get('ports', {})
                                ports[port] = {
                                    'type': 'switch',
                                    'device_ip': neighbor.get('mgmt_address'),
                                    'configured': True
                                }
                                self.state_manager.update_metadata(ip, 'ports', ports)
                            else:
                                logger.error(f"Failed to configure port {port} on switch {ip} as trunk")
                                all_ports_configured = False
                                
                        elif neighbor['type'] == 'ap':
                            # Configure AP port - tag wireless VLANs
                            success = config.configure_ap_port(
                                port=port,
                                wireless_vlans=self.wireless_vlans,
                                management_vlan=self.mgmt_vlan
                            )
                            
                            if success:
                                logger.info(f"Configured port {port} on switch {ip} for AP")
                                
                                # Store port configuration in metadata
                                ports = metadata.get('ports', {})
                                ports[port] = {
                                    'type': 'ap',
                                    'device_ip': neighbor.get('mgmt_address'),
                                    'configured': True
                                }
                                self.state_manager.update_metadata(ip, 'ports', ports)
                                
                                # Update AP status in inventory
                                ap_ip = neighbor.get('mgmt_address')
                                if ap_ip and ap_ip in self.inventory['aps']:
                                    self.inventory['aps'][ap_ip]['status'] = 'Configured'
                            else:
                                logger.error(f"Failed to configure port {port} on switch {ip} for AP")
                                all_ports_configured = False
                    
                    except Exception as e:
                        logger.error(f"Error configuring port {port} on switch {ip}: {e}", exc_info=True)
                        all_ports_configured = False
                
                # Disconnect from switch
                connection.disconnect()
                
                # If all ports were successfully configured, transition to fully configured state
                if all_ports_configured:
                    logger.info(f"All ports successfully configured on switch {ip}")
                    
                    # Transition to next state
                    self.state_manager.transition_to(
                        ip=ip,
                        new_state=SwitchState.FULLY_CONFIGURED,
                        reason="All ports configured successfully"
                    )
                else:
                    logger.warning(f"Some ports could not be configured on switch {ip}")
                    
                    # Stay in current state to retry configuration in next cycle
                
            except Exception as e:
                logger.error(f"Error configuring ports on switch {ip}: {e}", exc_info=True)
                
                # Don't transition to error state - we'll retry in the next cycle
    
    def _update_inventory(self) -> None:
        """
        Update the inventory for backward compatibility.
        
        This method updates the inventory dictionary based on the state manager
        to maintain backward compatibility with existing code.
        """
        # Update switch inventory
        for ip, data in self.state_manager.switches.items():
            state = data['state']
            metadata = data['metadata']
            
            # Skip switches already in inventory
            if ip in self.inventory['switches']:
                # Update status based on state
                if state == SwitchState.FULLY_CONFIGURED:
                    self.inventory['switches'][ip]['status'] = 'Configured'
                    self.inventory['switches'][ip]['configured'] = True
                elif state == SwitchState.ERROR:
                    self.inventory['switches'][ip]['status'] = 'Error'
                else:
                    self.inventory['switches'][ip]['status'] = state.value
                
                # Update base config applied flag
                if state in [SwitchState.BASE_CONFIG_APPLIED, SwitchState.MANAGEMENT_CONFIGURED, SwitchState.FULLY_CONFIGURED]:
                    self.inventory['switches'][ip]['base_config_applied'] = True
                
                # Update neighbors
                if 'neighbors' in metadata:
                    self.inventory['switches'][ip]['neighbors'] = metadata['neighbors']
                
                # Update ports
                if 'ports' in metadata:
                    self.inventory['switches'][ip]['ports'] = metadata['ports']
            else:
                # Add to inventory
                self.inventory['switches'][ip] = {
                    'ip': ip,
                    'username': metadata.get('username'),
                    'password': metadata.get('password'),
                    'preferred_password': metadata.get('preferred_password'),
                    'model': metadata.get('model'),
                    'serial': metadata.get('serial'),
                    'hostname': metadata.get('hostname'),
                    'status': state.value,
                    'configured': state == SwitchState.FULLY_CONFIGURED,
                    'base_config_applied': state in [SwitchState.BASE_CONFIG_APPLIED, SwitchState.MANAGEMENT_CONFIGURED, SwitchState.FULLY_CONFIGURED],
                    'neighbors': metadata.get('neighbors', {}),
                    'ports': metadata.get('ports', {})
                }
