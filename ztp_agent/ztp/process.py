"""
ZTP (Zero Touch Provisioning) process implementation.
"""
import logging
import threading
import time
import re
import socket
import paramiko
from typing import Dict, List, Any, Optional, Callable
import ipaddress

# Set up logging
logger = logging.getLogger(__name__)

class ZTPProcess:
    """Handles the ZTP process for RUCKUS devices"""
    
    def __init__(self, config: Dict[str, Any], ssh_executor: Optional[Callable] = None):
        """
        Initialize the ZTP process.
        
        Args:
            config: Configuration dictionary.
            ssh_executor: Optional SSH executor function for proxy support.
        """
        self.config = config
        self.ssh_executor = ssh_executor
        self.running = False
        self.thread = None
        self.inventory = {
            'switches': {},  # Keyed by MAC address
            'aps': {},      # Keyed by MAC address
            'ip_to_mac': {}  # IP to MAC mapping for quick lookups
        }
        
        # Store credentials for later use in discovering switches
        self.available_credentials = config.get('credentials', [])
        
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
        
        proxy_mode = "proxy" if ssh_executor else "direct"
        logger.info(f"Initialized ZTP process with {proxy_mode} SSH mode")
    
    def _create_inventory_update_callback(self) -> Callable[[str, dict], None]:
        """
        Create a callback to update inventory with SSH activity status.
        
        Returns:
            Function that updates inventory when called with IP and updates dict.
        """
        def update_callback(ip: str, updates: dict) -> None:
            try:
                # Try to find the device by IP in the IP-to-MAC mapping
                mac = self.inventory['ip_to_mac'].get(ip)
                
                if mac:
                    # Update switch inventory by MAC
                    if mac in self.inventory['switches']:
                        self.inventory['switches'][mac].update(updates)
                        # Log SSH activity for debugging
                        if 'ssh_active' in updates:
                            action = "connected to" if updates['ssh_active'] else "disconnected from"
                            logger.debug(f"SSH {action} switch {ip} (MAC: {mac})")
                    # Update AP inventory by MAC
                    elif mac in self.inventory['aps']:
                        self.inventory['aps'][mac].update(updates)
                        if 'ssh_active' in updates:
                            action = "connected to" if updates['ssh_active'] else "disconnected from"
                            logger.debug(f"SSH {action} AP {ip} (MAC: {mac})")
                else:
                    # Fallback: try to find in switches by IP for compatibility
                    for switch_mac, switch_data in self.inventory['switches'].items():
                        if switch_data.get('ip') == ip:
                            switch_data.update(updates)
                            if 'ssh_active' in updates:
                                action = "connected to" if updates['ssh_active'] else "disconnected from"
                                logger.debug(f"SSH {action} switch {ip} (MAC: {switch_mac})")
                            break
                    else:
                        # Fallback: try to find in APs by IP for compatibility
                        for ap_mac, ap_data in self.inventory['aps'].items():
                            if ap_data.get('ip') == ip:
                                ap_data.update(updates)
                                if 'ssh_active' in updates:
                                    action = "connected to" if updates['ssh_active'] else "disconnected from"
                                    logger.debug(f"SSH {action} AP {ip} (MAC: {ap_mac})")
                                break
                                
            except Exception as e:
                logger.debug(f"Error updating inventory for {ip}: {e}")
                
        return update_callback
    
    def _set_device_configuring(self, ip: str, configuring: bool = True):
        """
        Mark a device as actively being configured.
        
        Args:
            ip: IP address of the device
            configuring: True if actively configuring, False otherwise
        """
        mac = self.inventory['ip_to_mac'].get(ip)
        if mac:
            if mac in self.inventory['switches']:
                self.inventory['switches'][mac]['configuring'] = configuring
            elif mac in self.inventory['aps']:
                self.inventory['aps'][mac]['configuring'] = configuring
        else:
            # Fallback lookup
            for switch_mac, switch_data in self.inventory['switches'].items():
                if switch_data.get('ip') == ip:
                    switch_data['configuring'] = configuring
                    break
            else:
                for ap_mac, ap_data in self.inventory['aps'].items():
                    if ap_data.get('ip') == ip:
                        ap_data['configuring'] = configuring
                        break
    
    def add_switch(self, ip: str, username: str, password: str, preferred_password: str = None, 
                  debug: bool = None, debug_callback = None, suppress_errors: bool = False) -> bool:
        """
        Add a switch to the inventory.
        
        Args:
            ip: IP address of the switch.
            username: Username for switch access.
            password: Password for switch access.
            preferred_password: Password to set during first-time login.
            debug: Whether to enable debug mode for this switch.
            debug_callback: Function to call with debug messages.
            suppress_errors: If True, don't log connection errors (for credential cycling).
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            # Import here to avoid circular imports
            if self.ssh_executor:
                from ztp_agent.network.switch.proxy_operation import ProxyAwareSwitchOperation
                SwitchOperationClass = ProxyAwareSwitchOperation
            else:
                from ztp_agent.network.switch import SwitchOperation
                SwitchOperationClass = SwitchOperation
            
            # Validate IP
            ipaddress.IPv4Address(ip)
            
            # Use module-level debug settings if not provided
            if debug is None:
                debug = self.debug
            if debug_callback is None and self.debug_callback:
                debug_callback = self.debug_callback
            
            # Create switch operation instance to test connection
            if self.ssh_executor:
                switch_op = SwitchOperationClass(
                    ip=ip,
                    username=username,
                    password=password,
                    timeout=30,
                    preferred_password=preferred_password,
                    debug=debug,
                    debug_callback=debug_callback,
                    inventory_update_callback=self._create_inventory_update_callback(),
                    ssh_executor=self.ssh_executor
                )
            else:
                switch_op = SwitchOperationClass(
                    ip=ip,
                    username=username,
                    password=password,
                    timeout=30,
                    preferred_password=preferred_password,
                    debug=debug,
                    debug_callback=debug_callback,
                    inventory_update_callback=self._create_inventory_update_callback()
                )
            
            # Test connection
            if not switch_op.connect():
                if not suppress_errors:
                    logger.error(f"Failed to connect to switch {ip}")
                return False
            
            # Get model, serial, MAC address, and hostname by calling the methods
            model = switch_op.get_model()
            serial = switch_op.get_serial()
            mac = switch_op.get_chassis_mac()
            hostname = switch_op.get_hostname()
            
            # If no hostname found during initial discovery, it will be generated during configuration
            if not hostname:
                logger.debug(f"No hostname found for {ip}, will be generated during configuration")
            
            # Check if we got a MAC address
            if not mac:
                logger.error(f"Could not get MAC address for switch {ip}")
                switch_op.disconnect()
                return False
            
            # Check if switch already exists by MAC
            if mac in self.inventory['switches']:
                existing_switch = self.inventory['switches'][mac]
                logger.info(f"Switch {ip} already in inventory with MAC {mac}, updating IP from {existing_switch.get('ip')} to {ip}")
                existing_switch['ip'] = ip
                self.inventory['ip_to_mac'][ip] = mac
                switch_op.disconnect()
                return True
            
            # Add to inventory by MAC
            self.inventory['switches'][mac] = {
                'mac': mac,
                'ip': ip,
                'username': username,
                'password': password,
                'preferred_password': preferred_password,
                'model': model,
                'serial': serial,
                'hostname': hostname,
                'status': 'Connected',
                'configured': False,
                'base_config_applied': False,  # Track if base config has been applied
                'neighbors': {},
                'ports': {},
                'is_seed': True,  # Mark as seed switch
                'ssh_active': False  # Track SSH activity
            }
            
            # Also maintain IP to MAC mapping
            self.inventory['ip_to_mac'][ip] = mac
            
            # Disconnect
            switch_op.disconnect()
            
            logger.info(f"Added switch {ip} to inventory (MAC: {mac}, Model: {model}, Serial: {serial})")
            return True
        
        except ValueError:
            if not suppress_errors:
                logger.error(f"Invalid IP address: {ip}")
            return False
        except paramiko.ssh_exception.AuthenticationException as e:
            if not suppress_errors:
                logger.error(f"Authentication failed for switch {ip}: {e}")
                logger.error(f"Verify that the username '{username}' and password are correct.")
                logger.error(f"For first-time login, try using default credentials.")
            return False
        except paramiko.ssh_exception.NoValidConnectionsError as e:
            if not suppress_errors:
                logger.error(f"Connection error to switch {ip}: {e}")
                logger.error(f"Make sure SSH (port 22) is enabled and accessible on the switch.")
            return False
        except paramiko.ssh_exception.SSHException as e:
            if not suppress_errors:
                logger.error(f"SSH error for switch {ip}: {e}")
            return False
        except socket.timeout as e:
            if not suppress_errors:
                logger.error(f"Connection timeout to switch {ip}: {e}")
                logger.error(f"Check if the switch is reachable and responsive.")
            return False
        except Exception as e:
            if not suppress_errors:
                logger.error(f"Error adding switch {ip}: {e}", exc_info=True)
            return False
            
    def get_switch_by_ip(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        Get switch data by IP address.
        
        Args:
            ip: IP address to look up.
            
        Returns:
            Switch data or None if not found.
        """
        mac = self.inventory['ip_to_mac'].get(ip)
        if mac:
            return self.inventory['switches'].get(mac)
        return None
    
    def get_switch_info(self, ip: str) -> Dict[str, Any]:
        """
        Get information about a switch.
        
        Args:
            ip: IP address of the switch.
            
        Returns:
            Dictionary with switch information.
        """
        switch = self.get_switch_by_ip(ip)
        if not switch:
            return {}
        
        return {
            'mac': switch.get('mac'),
            'ip': switch.get('ip'),
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
        for mac, switch in switches_to_check:
            ip = switch.get('ip')
            if not ip:
                logger.error(f"Switch {mac} has no IP address")
                continue
                
            try:
                logger.debug(f"Checking for neighbors on switch {ip} (MAC: {mac})")
                
                # Create switch operation instance
                switch_op = SwitchOperation(
                    ip=ip,
                    username=switch['username'],
                    password=switch['password'],
                    preferred_password=switch.get('preferred_password'),
                    debug=self.debug,
                    debug_callback=self.debug_callback,
                    inventory_update_callback=self._create_inventory_update_callback()
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
                        
                        # Log discovered switch for later processing in neighbor configuration
                        if ip_addr != 'Unknown IP' and ip_addr != '0.0.0.0' and ip_addr != ip:
                            # Check if already tracked by IP-to-MAC mapping
                            if ip_addr not in self.inventory.get('ip_to_mac', {}):
                                logger.info(f"Discovered switch {ip_addr}, will be processed in neighbor configuration phase")
                            
                    elif neighbor.get('type') == 'ap':
                        ip_addr = neighbor.get('mgmt_address', 'Unknown IP')
                        ap_mac = neighbor.get('chassis_id', '').lower()  # Normalize MAC to lowercase
                        logger.info(f"Discovered AP on port {port}: {neighbor.get('system_name', 'Unknown')} (MAC: {ap_mac}, IP: {ip_addr})")
                        
                        # Get the model and hostname if available
                        system_name = neighbor.get('system_name', '').strip('"')
                        
                        # Use extracted model from LLDP system description if available, otherwise fallback to system_name
                        ap_model = neighbor.get('model') or system_name or 'Unknown AP'
                        logger.debug(f"AP {ap_mac} model determination: neighbor.model='{neighbor.get('model')}', system_name='{system_name}', final_model='{ap_model}'")
                        
                        # Add to APs inventory if we have a valid MAC
                        if ap_mac:
                            # Check if AP already exists by MAC
                            if ap_mac in self.inventory['aps']:
                                existing_ap = self.inventory['aps'][ap_mac]
                                logger.info(f"AP {system_name} already in inventory with MAC {ap_mac}, updating IP from {existing_ap.get('ip')} to {ip_addr}")
                                existing_ap['ip'] = ip_addr
                                # Update model if we have a better one from LLDP
                                if neighbor.get('model'):
                                    existing_ap['model'] = neighbor.get('model')
                                if ip_addr and ip_addr not in ['Unknown IP', '0.0.0.0']:
                                    self.inventory['ip_to_mac'][ip_addr] = ap_mac
                            else:
                                logger.info(f"Adding discovered AP {ap_mac} to inventory with model {ap_model}")
                                
                                self.inventory['aps'][ap_mac] = {
                                    'mac': ap_mac,
                                    'ip': ip_addr,
                                    'model': ap_model,
                                    'hostname': system_name or f"ap-{ap_mac.replace(':', '-')}",
                                    'status': 'discovered',
                                    'switch_ip': ip,
                                    'switch_port': port,
                                    'ssh_active': False  # Track SSH activity
                                }
                                
                                # Also maintain IP to MAC mapping if we have a valid IP
                                if ip_addr and ip_addr not in ['Unknown IP', '0.0.0.0']:
                                    self.inventory['ip_to_mac'][ip_addr] = ap_mac
                
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
        for mac, switch in switches_to_configure:
            ip = switch.get('ip')
            if not ip:
                logger.error(f"Switch {mac} has no IP address")
                continue
                
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
        unconfigured_switches = [(mac, switch) for mac, switch in self.inventory['switches'].items() 
                                if not switch.get('configured', False)]
        
        for mac, switch in unconfigured_switches:
            ip = switch.get('ip')
            if not ip:
                logger.error(f"Switch {mac} has no IP address")
                continue
                
            logger.info(f"Performing basic configuration on switch {ip} (MAC: {mac})")
            
            try:
                # Try to connect with credential cycling
                connected = False
                switch_op = None
                
                # Build list of credentials to try (stored first, then default, then others)
                credentials_to_try = []
                
                # First try the stored credentials
                stored_cred = {"username": switch['username'], "password": switch['password']}
                credentials_to_try.append(stored_cred)
                
                # Then try default if not already tried
                if not (stored_cred['username'] == 'super' and stored_cred['password'] == 'sp-admin'):
                    credentials_to_try.append({"username": "super", "password": "sp-admin"})
                
                # Then try any other credentials
                for cred in self.available_credentials:
                    # Skip if already in list
                    already_added = any(
                        c['username'] == cred.get('username') and c['password'] == cred.get('password')
                        for c in credentials_to_try
                    )
                    if not already_added:
                        credentials_to_try.append(cred)
                
                # Try each credential
                for cred in credentials_to_try:
                    username = cred['username']
                    password = cred['password']
                    
                    logger.debug(f"Trying to connect to switch {ip} for configuration with credentials {username}/{'*' * len(password)}")
                    
                    switch_op = SwitchOperation(
                        ip=ip,
                        username=username,
                        password=password,
                        preferred_password=switch.get('preferred_password'),
                        debug=self.debug,
                        debug_callback=self.debug_callback,
                        inventory_update_callback=self._create_inventory_update_callback()
                    )
                    
                    if switch_op.connect():
                        connected = True
                        # Update stored credentials if different
                        if username != switch['username'] or password != switch['password']:
                            logger.info(f"Updated working credentials for switch {ip}")
                            switch['username'] = username
                            switch['password'] = password
                        break
                
                if not connected:
                    logger.error(f"Failed to connect to switch {ip} for basic configuration with any available credentials")
                    continue
                
                # Determine hostname based on model and serial
                model = switch.get('model')
                serial = switch.get('serial')
                
                # Get fresh info if not already stored
                if not model:
                    model = switch_op.get_model()
                    if model:
                        switch['model'] = model
                        
                if not serial:
                    serial = switch_op.get_serial()
                    if serial:
                        switch['serial'] = serial
                        
                # Always generate hostname using {model}-{serial} format for consistency
                hostname = f"{model}-{serial}"
                
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
                
                # STEP 1: Apply base configuration (which includes VLAN creation with spanning tree) if not already applied
                if not switch.get('base_config_applied', False):
                    self._set_device_configuring(ip, True)
                    logger.info(f"Sending base config to switch (length: {len(self.base_config)})")
                    success = switch_op.apply_base_config(self.base_config)
                    
                    if not success:
                        logger.error(f"Failed to configure VLANs on switch {ip}")
                        self._set_device_configuring(ip, False)
                        switch_op.disconnect()
                        continue
                    
                    # Mark as base config applied
                    switch['base_config_applied'] = True
                    self.inventory['switches'][mac]['base_config_applied'] = True
                else:
                    logger.info(f"Base configuration already applied to switch {ip}, skipping")
                
                # STEP 2: Now perform basic configuration for management
                logger.info(f"Configuring basic switch settings for {ip}")
                success = switch_op.configure_switch_basic(
                    hostname=hostname,
                    mgmt_vlan=mgmt_vlan,
                    mgmt_ip=mgmt_ip,
                    mgmt_mask=mgmt_mask
                )
                
                # Note: Password change is handled during first-time login connection
                # RUCKUS ICX switches automatically save the new password during first login
                
                self._set_device_configuring(ip, False)
                
                # Disconnect from switch
                switch_op.disconnect()
                
                if success:
                    logger.info(f"Successfully configured switch {ip} with basic settings")
                    # Mark as configured
                    self.inventory['switches'][mac]['configured'] = True
                    self.inventory['switches'][mac]['status'] = 'Configured'
                    # Update the hostname in inventory to match what was set on the switch
                    self.inventory['switches'][mac]['hostname'] = hostname
                    logger.info(f"Updated inventory hostname for switch {ip} to {hostname}")
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
            
        # Check if this switch is already in our inventory by MAC or IP
        neighbor_mac = chassis_id.lower() if chassis_id != 'unknown' else None
        already_exists = False
        
        if neighbor_mac and neighbor_mac in self.inventory['switches']:
            logger.info(f"Switch {system_name} (MAC: {neighbor_mac}) is already in the inventory")
            already_exists = True
        elif neighbor_ip in self.inventory.get('ip_to_mac', {}):
            existing_mac = self.inventory['ip_to_mac'][neighbor_ip]
            logger.info(f"Switch {system_name} ({neighbor_ip}) is already in the inventory with MAC {existing_mac}")
            already_exists = True
            
        if already_exists:
            return
            
        # Add the switch to our inventory
        # Default to same username/password as the parent switch
        # Find parent switch by IP
        parent_switch = None
        for mac, switch_data in self.inventory['switches'].items():
            if switch_data.get('ip') == switch_ip:
                parent_switch = switch_data
                break
                
        if not parent_switch:
            logger.error(f"Could not find parent switch {switch_ip} in inventory")
            return
        
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
                debug_callback=self.debug_callback,
                inventory_update_callback=self._create_inventory_update_callback()
            )
            
            # Connect to parent switch
            if switch_op.connect():
                # Check if we need to apply base configuration (only if not already configured)
                if not parent_switch.get('base_config_applied', False):
                    logger.info(f"Applying base configuration to switch {switch_ip}")
                    success = switch_op.apply_base_config(self.base_config)
                    
                    if not success:
                        logger.error(f"Failed to configure VLANs on switch {switch_ip}")
                        switch_op.disconnect()
                        return
                    
                    # Mark as base config applied
                    parent_switch['base_config_applied'] = True
                else:
                    logger.info(f"Base configuration already applied to switch {switch_ip}, skipping")
                
                # Configure the port as a switch trunk with all-tagged                
                success = switch_op.configure_switch_port(port)
                if success:
                    logger.info(f"Configured port {port} on switch {switch_ip} as trunk for neighbor switch")
                else:
                    logger.error(f"Failed to configure port {port} on switch {switch_ip} as trunk")
                
                # Disconnect from parent switch
                switch_op.disconnect()
                
                # Try to connect to the new switch with credential cycling
                successfully_connected = False
                working_username = None
                working_password = None
                
                # Build list of credentials to try (default first, then user-added)
                credentials_to_try = [{"username": "super", "password": "sp-admin"}]  # Default first
                
                # Add credentials from the stored list
                for cred in self.available_credentials:
                    # Skip if it's the same as default
                    if not (cred.get('username') == 'super' and cred.get('password') == 'sp-admin'):
                        credentials_to_try.append(cred)
                
                # Try each credential
                for cred in credentials_to_try:
                    username = cred['username']
                    password = cred['password']
                    
                    logger.info(f"Trying to connect to discovered switch {neighbor_ip} with credentials {username}/{'*' * len(password)}")
                    
                    new_switch_op = SwitchOperation(
                        ip=neighbor_ip,
                        username=username,
                        password=password,
                        preferred_password=parent_switch.get('preferred_password'),
                        debug=self.debug,
                        debug_callback=self.debug_callback,
                        inventory_update_callback=self._create_inventory_update_callback()
                    )
                    
                    if new_switch_op.connect():
                        # Successfully connected
                        successfully_connected = True
                        working_username = username
                        working_password = password
                        
                        # Get device info by calling the methods
                        model = new_switch_op.get_model()
                        serial = new_switch_op.get_serial()
                        new_switch_mac = new_switch_op.get_chassis_mac()
                        hostname = new_switch_op.get_hostname()
                        
                        # Check if we got a MAC address for the new switch
                        if not new_switch_mac:
                            logger.error(f"Could not get MAC address for discovered switch {neighbor_ip}")
                            new_switch_op.disconnect()
                            continue
                        
                        # Add the new switch to the inventory by MAC
                        self.inventory['switches'][new_switch_mac] = {
                            'mac': new_switch_mac,
                            'ip': neighbor_ip,
                            'username': working_username,
                            'password': working_password,
                            'preferred_password': parent_switch.get('preferred_password'),
                            'model': model,
                            'serial': serial,
                            'hostname': hostname,
                            'status': 'Discovered',  # Start with Discovered status
                            'configured': False,     # Mark as not configured so it will be configured in next cycle
                            'base_config_applied': False,  # Track if base config has been applied
                            'neighbors': {},
                            'ssh_active': False,
                            'discovered_from': {
                                'switch_ip': switch_ip,
                                'port': port
                            }
                        }
                        
                        # Also maintain IP to MAC mapping
                        self.inventory['ip_to_mac'][neighbor_ip] = new_switch_mac
                        
                        # Update the parent switch's neighbors to ensure bidirectional connection
                        # This ensures the topology shows the connection correctly
                        parent_mac = self.inventory['ip_to_mac'].get(switch_ip)
                        if parent_mac and parent_mac in self.inventory['switches']:
                            parent_switch_data = self.inventory['switches'][parent_mac]
                            if 'neighbors' not in parent_switch_data:
                                parent_switch_data['neighbors'] = {}
                            
                            # Ensure the neighbor entry exists and has the correct IP
                            if port in parent_switch_data['neighbors']:
                                parent_switch_data['neighbors'][port]['mgmt_address'] = neighbor_ip
                                logger.info(f"Updated neighbor IP for port {port} on parent switch {switch_ip}")
                        
                        # Disconnect from new switch
                        new_switch_op.disconnect()
                        
                        logger.info(f"Successfully connected to discovered switch {system_name} (IP: {neighbor_ip}, Model: {model}, Serial: {serial}) with credentials {working_username}/{'*' * len(working_password)}")
                        break
                    else:
                        # Connection failed with these credentials
                        logger.debug(f"Failed to connect to discovered switch {neighbor_ip} with credentials {username}/{'*' * len(password)}")
                
                if not successfully_connected:
                    logger.warning(f"Could not connect to discovered switch {system_name} ({neighbor_ip}) with any available credentials")
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
        
        # Check if this AP is already in our inventory by MAC
        if chassis_id:
            ap_mac = chassis_id.lower()  # Normalize MAC
            if ap_mac in self.inventory['aps']:
                logger.info(f"AP {system_name} (MAC: {ap_mac}) is already in the inventory")
                # Update IP if it changed
                if ap_ip and ap_ip not in ['0.0.0.0', 'Unknown IP']:
                    self.inventory['aps'][ap_mac]['ip'] = ap_ip
                    self.inventory['ip_to_mac'][ap_ip] = ap_mac
        
        # Configure the port for the AP
        # Find parent switch by IP
        parent_switch = None
        for mac, switch_data in self.inventory['switches'].items():
            if switch_data.get('ip') == switch_ip:
                parent_switch = switch_data
                break
                
        if not parent_switch:
            logger.error(f"Could not find parent switch {switch_ip} in inventory")
            return
        
        # Import here to avoid circular imports
        from ztp_agent.network.switch import SwitchOperation
        
        try:
            # Try to connect with credential cycling
            connected = False
            switch_op = None
            
            # Build list of credentials to try (stored first, then default, then others)
            credentials_to_try = []
            
            # First try the stored credentials
            stored_cred = {"username": parent_switch['username'], "password": parent_switch['password']}
            credentials_to_try.append(stored_cred)
            
            # Then try default if not already tried
            if not (stored_cred['username'] == 'super' and stored_cred['password'] == 'sp-admin'):
                credentials_to_try.append({"username": "super", "password": "sp-admin"})
            
            # Then try any other credentials
            for cred in self.available_credentials:
                # Skip if already in list
                already_added = any(
                    c['username'] == cred.get('username') and c['password'] == cred.get('password')
                    for c in credentials_to_try
                )
                if not already_added:
                    credentials_to_try.append(cred)
            
            # Try each credential
            for cred in credentials_to_try:
                username = cred['username']
                password = cred['password']
                
                logger.debug(f"Trying to connect to switch {switch_ip} for AP port config with credentials {username}/{'*' * len(password)}")
                
                switch_op = SwitchOperation(
                    ip=switch_ip,
                    username=username,
                    password=password,
                    preferred_password=parent_switch.get('preferred_password'),
                    debug=self.debug,
                    debug_callback=self.debug_callback,
                    inventory_update_callback=self._create_inventory_update_callback()
                )
                
                if switch_op.connect():
                    connected = True
                    # Update stored credentials if different
                    if username != parent_switch['username'] or password != parent_switch['password']:
                        logger.info(f"Updated working credentials for switch {switch_ip}")
                        parent_switch['username'] = username
                        parent_switch['password'] = password
                    break
            
            # Connect to switch
            if connected:
                # Get VLAN configuration for port config
                mgmt_vlan = self.mgmt_vlan
                wireless_vlans = self.wireless_vlans
                
                # Check if we need to apply base configuration (only if not already configured)
                if not parent_switch.get('base_config_applied', False):
                    logger.info(f"Applying base configuration to switch {switch_ip}")
                    success = switch_op.apply_base_config(self.base_config)
                    
                    if not success:
                        logger.error(f"Failed to configure VLANs on switch {switch_ip}")
                        switch_op.disconnect()
                        return
                    
                    # Mark as base config applied
                    parent_switch['base_config_applied'] = True
                else:
                    logger.info(f"Base configuration already applied to switch {switch_ip}, skipping")
                
                # STEP 2: Configure the port for AP with specific tagged VLANs
                self._set_device_configuring(switch_ip, True)
                logger.info(f"Configuring port {port} on switch {switch_ip} for AP {system_name}")
                success = switch_op.configure_ap_port(port, wireless_vlans, mgmt_vlan)
                self._set_device_configuring(switch_ip, False)
                
                if success:
                    logger.info(f"Configured port {port} on switch {switch_ip} for AP {system_name}")
                else:
                    logger.error(f"Failed to configure port {port} on switch {switch_ip} for AP")
                
                # Disconnect from switch
                switch_op.disconnect()
                
                # Add the AP to our inventory if we have a MAC
                if chassis_id:
                    ap_mac = chassis_id.lower()  # Normalize MAC
                    
                    # Get existing model from discovery if available
                    existing_model = None
                    if ap_mac in self.inventory['aps']:
                        existing_model = self.inventory['aps'][ap_mac].get('model')
                    
                    self.inventory['aps'][ap_mac] = {
                        'mac': ap_mac,
                        'ip': ap_ip or 'Unknown IP',
                        'model': existing_model or 'Unknown AP',  # Preserve the model from discovery
                        'hostname': system_name,
                        'status': 'configured',
                        'configured': True,  # Add boolean configured field
                        'switch_ip': switch_ip,
                        'switch_port': port,
                        'ssh_active': False
                    }
                    # Also maintain IP to MAC mapping if we have a valid IP
                    if ap_ip and ap_ip not in ['0.0.0.0', 'Unknown IP']:
                        self.inventory['ip_to_mac'][ap_ip] = ap_mac
                    logger.info(f"Added AP {system_name} (MAC: {ap_mac}, IP: {ap_ip}) to inventory with model {existing_model or 'Unknown AP'}")
            else:
                logger.error(f"Failed to connect to switch {switch_ip} for AP port configuration with any available credentials")
        
        except Exception as e:
            logger.error(f"Error configuring AP port for {system_name} on switch {switch_ip}: {e}", exc_info=True)
