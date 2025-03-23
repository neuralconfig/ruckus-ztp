"""
ZTP (Zero Touch Provisioning) process implementation.
"""
import logging
import threading
import time
import re
from typing import Dict, List, Any, Optional
import ipaddress

# Set up logging
logger = logging.getLogger(__name__)

class ZTPProcess:
    """Handles the ZTP process for RUCKUS devices"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the ZTP process.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        self.running = False
        self.thread = None
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
        
        logger.info("Initialized ZTP process")
    
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
            # Import here to avoid circular imports
            from ztp_agent.network.switch import SwitchOperation
            
            # Validate IP
            ipaddress.IPv4Address(ip)
            
            # Use module-level debug settings if not provided
            if debug is None:
                debug = self.debug
            if debug_callback is None and self.debug_callback:
                debug_callback = self.debug_callback
            
            # Create switch operation instance to test connection
            switch_op = SwitchOperation(
                ip=ip,
                username=username,
                password=password,
                timeout=30,
                preferred_password=preferred_password,
                debug=debug,
                debug_callback=debug_callback
            )
            
            # Test connection
            if not switch_op.connect():
                logger.error(f"Failed to connect to switch {ip}")
                return False
            
            # Get model and serial number
            model = switch_op.model
            serial = switch_op.serial
            hostname = switch_op.hostname
            
            # Add to inventory
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
                'neighbors': {},
                'ports': {}
            }
            
            # Disconnect
            switch_op.disconnect()
            
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
        if ip not in self.inventory['switches']:
            return {}
        
        switch = self.inventory['switches'][ip]
        return {
            'ip': ip,
            'model': switch.get('model'),
            'serial': switch.get('serial'),
            'hostname': switch.get('hostname'),
            'status': switch.get('status'),
            'configured': switch.get('configured', False)
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
        if not self.inventory['switches']:
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
        return {
            'running': self.running,
            'switches': len(self.inventory['switches']),
            'aps': len(self.inventory['aps']),
            'configured_switches': sum(1 for s in self.inventory['switches'].values() if s.get('configured', False)),
            'last_update': time.strftime('%Y-%m-%d %H:%M:%S')
        }
    
    def _run_process(self) -> None:
        """
        Main ZTP process loop.
        
        This method runs in a separate thread.
        """
        logger.info("ZTP process thread started")
        
        poll_interval = self.config.get('poll_interval', 60)  # seconds
        
        try:
            while self.running:
                try:
                    # Process each unconfigured switch
                    self._discover_devices()
                    
                    # Configure newly discovered devices
                    self._configure_devices()
                    
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
        Discover devices using LLDP and trace-l2 for accurate IP discovery.
        
        This method connects to each configured switch and retrieves
        LLDP neighbors and trace-l2 data to discover new devices.
        """
        logger.debug("Running device discovery")
        
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        # Make a copy of the switches to avoid modifying during iteration
        switches_to_check = list(self.inventory['switches'].items())
        
        # For each configured switch in our copy
        for ip, switch in switches_to_check:
            try:
                logger.debug(f"Checking for neighbors on switch {ip}")
                
                # Create switch operation instance
                switch_op = SwitchOperation(
                    ip=ip,
                    username=switch['username'],
                    password=switch['password'],
                    preferred_password=switch.get('preferred_password'),
                    debug=self.debug,
                    debug_callback=self.debug_callback
                )
                
                # Connect to switch
                if not switch_op.connect():
                    logger.error(f"Failed to connect to switch {ip}")
                    continue
                
                # Get LLDP neighbors
                success, neighbors = switch_op.get_lldp_neighbors()
                
                # Disconnect from switch
                switch_op.disconnect()
                
                if not success:
                    logger.error(f"Failed to get LLDP neighbors from switch {ip}")
                    continue
                
                # Store neighbors in inventory
                switch['neighbors'] = {}
                for port, neighbor in neighbors.items():
                    switch['neighbors'][port] = neighbor
                    
                    # Log discovery and add to inventory if not already there
                    if neighbor.get('type') == 'switch':
                        ip_addr = neighbor.get('mgmt_address', 'Unknown IP')
                        logger.info(f"Discovered switch on port {port}: {neighbor.get('system_name', 'Unknown')} ({ip_addr})")
                        
                        # Add to inventory if we have a valid IP and it's not already in inventory
                        if ip_addr != 'Unknown IP' and ip_addr != '0.0.0.0':
                            if ip_addr not in self.inventory['switches']:
                                # Check if we actually want to add this switch (avoid circular references)
                                if ip_addr != ip:  # Don't add the switch back to itself
                                    logger.info(f"Adding discovered switch {ip_addr} to inventory")
                                    
                                    # Get the model and hostname if available
                                    system_name = neighbor.get('system_name', '').strip('"')
                                    system_description = neighbor.get('system_description', '').strip('"')
                                    
                                    # Extract model from system description if possible
                                    model = None
                                    if system_description:
                                        model_match = re.search(r'ICX\d+[a-zA-Z0-9\-]+(?:-POE)?', system_description)
                                        if model_match:
                                            model = model_match.group(0)
                                    
                                    # Use the same credentials as the parent switch
                                    self.inventory['switches'][ip_addr] = {
                                        'ip': ip_addr,
                                        'username': switch['username'],
                                        'password': switch['password'],
                                        'preferred_password': switch.get('preferred_password'),
                                        'model': model,
                                        'hostname': system_name or f"switch-{ip_addr.replace('.', '-')}",
                                        'status': 'Discovered',
                                        'configured': False,
                                        'neighbors': {},
                                        'ports': {}
                                    }
                            
                    elif neighbor.get('type') == 'ap':
                        ip_addr = neighbor.get('mgmt_address', 'Unknown IP')
                        logger.info(f"Discovered AP on port {port}: {neighbor.get('system_name', 'Unknown')} ({ip_addr})")
                        
                        # Add to APs inventory if we have a valid IP
                        if ip_addr != 'Unknown IP' and ip_addr != '0.0.0.0':
                            if ip_addr not in self.inventory['aps']:
                                logger.info(f"Adding discovered AP {ip_addr} to inventory")
                                
                                # Get the model and hostname if available
                                system_name = neighbor.get('system_name', '').strip('"')
                                
                                self.inventory['aps'][ip_addr] = {
                                    'ip': ip_addr,
                                    'model': system_name or 'Unknown AP',
                                    'hostname': system_name or f"ap-{ip_addr.replace('.', '-')}",
                                    'status': 'Discovered',
                                    'switch_ip': ip,
                                    'switch_port': port
                                }
                
                # Log total discoveries
                switch_count = sum(1 for n in neighbors.values() if n.get('type') == 'switch')
                ap_count = sum(1 for n in neighbors.values() if n.get('type') == 'ap')
                logger.info(f"Discovered {switch_count} switches and {ap_count} APs on switch {ip}")
                
            except Exception as e:
                logger.error(f"Error discovering devices on switch {ip}: {e}", exc_info=True)
    
    def _configure_devices(self) -> None:
        """
        Configure discovered devices.
        
        This method:
        1. Configures newly discovered devices (switch interfaces and AP ports)
        2. Performs basic configuration on newly discovered switches
        """
        logger.debug("Configuring discovered devices")
        
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        # PART 1: Configure ports for discovered neighbors
        # Make a copy of switches to avoid modifying during iteration
        switches_to_configure = list(self.inventory['switches'].items())
        
        # For each switch that has neighbors
        for ip, switch in switches_to_configure:
            if 'neighbors' not in switch:
                continue
            
            # Process each neighbor that hasn't been processed
            for port, neighbor in switch['neighbors'].items():
                # Skip already processed neighbors
                if neighbor.get('processed', False):
                    continue
                
                if neighbor['type'] == 'switch':
                    self._configure_neighbor_switch(ip, port, neighbor)
                elif neighbor['type'] == 'ap':
                    self._configure_ap_port(ip, port, neighbor)
                
                # Mark as processed
                neighbor['processed'] = True
        
        # PART 2: Configure basic settings on unconfigured switches
        # Get list of unconfigured switches
        unconfigured_switches = [(ip, switch) for ip, switch in self.inventory['switches'].items() 
                                if not switch.get('configured', False)]
        
        for ip, switch in unconfigured_switches:
            logger.info(f"Performing basic configuration on switch {ip}")
            
            try:
                # Create switch operation instance
                switch_op = SwitchOperation(
                    ip=ip,
                    username=switch['username'],
                    password=switch['password'],
                    preferred_password=switch.get('preferred_password'),
                    debug=self.debug,
                    debug_callback=self.debug_callback
                )
                
                # Connect to switch
                if not switch_op.connect():
                    logger.error(f"Failed to connect to switch {ip} for basic configuration")
                    continue
                
                # Determine hostname based on model and serial
                model = switch.get('model') or switch_op.model
                serial = switch.get('serial') or switch_op.serial
                hostname = switch.get('hostname') or f"{model}-{serial}"
                
                # Get the management VLAN for basic configuration
                mgmt_vlan = self.mgmt_vlan
                wireless_vlans = self.wireless_vlans
                
                # Generate new management IP from IP pool
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
                
                # STEP 1: Apply base configuration (which includes VLAN creation with spanning tree)
                logger.info(f"Sending base config to switch (length: {len(self.base_config)})")
                success = switch_op.apply_base_config(self.base_config)
                
                if not success:
                    logger.error(f"Failed to configure VLANs on switch {ip}")
                    switch_op.disconnect()
                    continue
                
                # STEP 2: Now perform basic configuration for management
                success = switch_op.configure_switch_basic(
                    hostname=hostname,
                    mgmt_vlan=mgmt_vlan,
                    mgmt_ip=mgmt_ip,
                    mgmt_mask=mgmt_mask
                )
                
                # Disconnect from switch
                switch_op.disconnect()
                
                if success:
                    logger.info(f"Successfully configured switch {ip} with basic settings")
                    # Mark as configured
                    self.inventory['switches'][ip]['configured'] = True
                    self.inventory['switches'][ip]['status'] = 'Configured'
                else:
                    logger.error(f"Failed to configure switch {ip} with basic settings")
            
            except Exception as e:
                logger.error(f"Error configuring switch {ip}: {e}", exc_info=True)
    
    def _configure_neighbor_switch(self, switch_ip: str, port: str, neighbor: Dict[str, Any]) -> None:
        """
        Configure a newly discovered neighbor switch.
        
        Args:
            switch_ip: IP of the currently configured switch.
            port: Port on which the neighbor was discovered.
            neighbor: Neighbor information.
        """
        logger.info(f"Configuring neighbor switch on {switch_ip} port {port}")
        
        # Get neighbor information
        chassis_id = neighbor.get('chassis_id', 'unknown')
        system_name = neighbor.get('system_name', 'Unknown')
        neighbor_ip = neighbor.get('mgmt_address')
        
        # Skip if we don't have an IP address
        if not neighbor_ip or neighbor_ip == '0.0.0.0':
            logger.warning(f"No valid IP address for switch {system_name} (MAC: {chassis_id}), skipping configuration")
            return
            
        # Check if this switch is already in our inventory
        if neighbor_ip in self.inventory['switches']:
            logger.info(f"Switch {system_name} ({neighbor_ip}) is already in the inventory")
            return
            
        # Add the switch to our inventory
        # Default to same username/password as the parent switch
        parent_switch = self.inventory['switches'][switch_ip]
        
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        try:
            # Configure the port on the current switch as a trunk
            switch_op = SwitchOperation(
                ip=switch_ip,
                username=parent_switch['username'],
                password=parent_switch['password'],
                preferred_password=parent_switch.get('preferred_password'),
                debug=self.debug,
                debug_callback=self.debug_callback
            )
            
            # Connect to parent switch
            if switch_op.connect():
                # STEP 1: First, apply the base configuration
                success = switch_op.apply_base_config(self.base_config)
                
                if not success:
                    logger.error(f"Failed to configure VLANs on switch {switch_ip}")
                    switch_op.disconnect()
                    return
                
                # STEP 2: Configure the port as a switch trunk with all-tagged                
                success = switch_op.configure_switch_port(port)
                if success:
                    logger.info(f"Configured port {port} on switch {switch_ip} as trunk for neighbor switch")
                else:
                    logger.error(f"Failed to configure port {port} on switch {switch_ip} as trunk")
                
                # Disconnect from parent switch
                switch_op.disconnect()
                
                # Try to connect to the new switch
                new_switch_op = SwitchOperation(
                    ip=neighbor_ip,
                    username=parent_switch['username'],
                    password=parent_switch['password'],
                    preferred_password=parent_switch.get('preferred_password'),
                    debug=self.debug,
                    debug_callback=self.debug_callback
                )
                
                if new_switch_op.connect():
                    # Successfully connected to the new switch
                    model = new_switch_op.model
                    serial = new_switch_op.serial
                    hostname = new_switch_op.hostname
                    
                    # Add the new switch to the inventory
                    self.inventory['switches'][neighbor_ip] = {
                        'ip': neighbor_ip,
                        'username': parent_switch['username'],
                        'password': parent_switch['password'],
                        'preferred_password': parent_switch.get('preferred_password'),
                        'model': model,
                        'serial': serial,
                        'hostname': hostname,
                        'status': 'Discovered',  # Start with Discovered status
                        'configured': False,     # Mark as not configured so it will be configured in next cycle
                        'neighbors': {},
                        'discovered_from': {
                            'switch_ip': switch_ip,
                            'port': port
                        }
                    }
                    
                    # Disconnect from new switch
                    new_switch_op.disconnect()
                    
                    logger.info(f"Added discovered switch {system_name} (IP: {neighbor_ip}, Model: {model}, Serial: {serial}) to inventory")
                else:
                    logger.warning(f"Discovered switch {system_name} ({neighbor_ip}) but could not connect to it")
            else:
                logger.error(f"Failed to connect to parent switch {switch_ip}")
        
        except Exception as e:
            logger.error(f"Error configuring neighbor switch {system_name} ({neighbor_ip}): {e}", exc_info=True)
    
    def _configure_ap_port(self, switch_ip: str, port: str, neighbor: Dict[str, Any]) -> None:
        """
        Configure a port for a newly discovered AP.
        
        Args:
            switch_ip: IP of the switch.
            port: Port on which the AP was discovered.
            neighbor: Neighbor information.
        """
        logger.info(f"Configuring AP port on {switch_ip} port {port}")
        
        # Get neighbor information
        chassis_id = neighbor.get('chassis_id', 'unknown')
        system_name = neighbor.get('system_name', 'Unknown')
        ap_ip = neighbor.get('mgmt_address')
        
        # Skip if we don't have an IP address
        if not ap_ip or ap_ip == '0.0.0.0':
            logger.warning(f"No valid IP address for AP {system_name} (MAC: {chassis_id}), configuring port anyway")
        else:
            # Check if this AP is already in our inventory
            if ap_ip in self.inventory['aps']:
                logger.info(f"AP {system_name} ({ap_ip}) is already in the inventory")
                # Continue with port configuration anyway
        
        # Configure the port for the AP
        parent_switch = self.inventory['switches'][switch_ip]
        
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        try:
            # Configure the port on the switch for AP
            switch_op = SwitchOperation(
                ip=switch_ip,
                username=parent_switch['username'],
                password=parent_switch['password'],
                preferred_password=parent_switch.get('preferred_password'),
                debug=self.debug,
                debug_callback=self.debug_callback
            )
            
            # Connect to switch
            if switch_op.connect():
                # Get VLAN configuration for port config
                mgmt_vlan = self.mgmt_vlan
                wireless_vlans = self.wireless_vlans
                
                # STEP 1: First, apply the base configuration
                success = switch_op.apply_base_config(self.base_config)
                
                if not success:
                    logger.error(f"Failed to configure VLANs on switch {switch_ip}")
                    switch_op.disconnect()
                    return
                
                # STEP 2: Configure the port for AP with specific tagged VLANs
                success = switch_op.configure_ap_port(port, wireless_vlans, mgmt_vlan)
                if success:
                    logger.info(f"Configured port {port} on switch {switch_ip} for AP {system_name}")
                else:
                    logger.error(f"Failed to configure port {port} on switch {switch_ip} for AP")
                
                # Disconnect from switch
                switch_op.disconnect()
                
                # Add the AP to our inventory if we have an IP
                if ap_ip and ap_ip != '0.0.0.0':
                    self.inventory['aps'][ap_ip] = {
                        'ip': ap_ip,
                        'mac': chassis_id,
                        'system_name': system_name,
                        'status': 'Configured',
                        'connected_to': {
                            'switch_ip': switch_ip,
                            'port': port
                        }
                    }
                    logger.info(f"Added AP {system_name} (IP: {ap_ip}, MAC: {chassis_id}) to inventory")
            else:
                logger.error(f"Failed to connect to switch {switch_ip}")
        
        except Exception as e:
            logger.error(f"Error configuring AP port for {system_name} on switch {switch_ip}: {e}", exc_info=True)
