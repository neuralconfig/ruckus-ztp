"""
Switch configuration and management commands for CLI.
"""
import re
import logging
import argparse
from cmd2 import with_category, with_argparser

# Define command categories
CMD_CATEGORY_CONFIG = "Configuration Commands"

# Default credentials for Ruckus ICX switches
DEFAULT_USERNAME = "super"
DEFAULT_PASSWORD = "sp-admin"


class SwitchCommandsMixin:
    """Switch configuration and management commands for CLI"""
    
    #
    # Configuration Commands
    #
    config_parser = argparse.ArgumentParser(description='Configure ZTP agent')
    config_subparsers = config_parser.add_subparsers(dest='config_command')
    
    # Switch config subcommand
    switch_parser = config_subparsers.add_parser('switch', help='Configure switch')
    switch_parser.add_argument('ip', help='Switch IP address (will use default credentials)')
    
    # Password config subcommand
    password_parser = config_subparsers.add_parser('password', help='Configure default password for "super" user')
    password_parser.add_argument('password', help='Preferred password for the super user')
    
    # Hostname config subcommand
    hostname_parser = config_subparsers.add_parser('hostname', help='Set hostname based on model and serial')
    hostname_parser.add_argument('ip', help='Switch IP address')
    
    @with_category(CMD_CATEGORY_CONFIG)
    @with_argparser(config_parser)
    def do_config(self, args):
        """Configure ZTP agent settings"""
        if not args.config_command:
            self.do_help('config')
            return
            
        if args.config_command == 'switch':
            # Use default super user and password
            self._add_switch(args.ip, DEFAULT_USERNAME, 
                            self.default_credentials.get('preferred_password', DEFAULT_PASSWORD))
        elif args.config_command == 'password':
            self._set_preferred_password(args.password)
        elif args.config_command == 'hostname':
            self._set_switch_hostname(args.ip)
    
    def _set_preferred_password(self, password: str):
        """Set the preferred password for the super user"""
        if not password or len(password) < 6:
            self.perror("Password must be at least 6 characters long")
            return
            
        self.default_credentials['preferred_password'] = password
        self.poutput(f"Preferred password for '{DEFAULT_USERNAME}' user has been set")
        self.poutput("This password will be used when changing the default password on new switches")
    
    def _set_switch_hostname(self, ip: str):
        """
        Set the hostname for a switch based on model and serial number.
        
        Args:
            ip: Switch IP address.
        """
        # Check if the switch exists in the inventory
        if ip not in self.switches:
            self.perror(f"Switch {ip} not found in inventory")
            return
        
        # Get switch data from inventory
        switch = self.switches[ip]
        
        # Create SwitchOperation instance
        try:
            # Import here to avoid circular imports
            from ztp_agent.network.switch import SwitchOperation
            
            # Set debug settings
            debug_params = {}
            if getattr(self, 'debug_mode', False):
                debug_params = {
                    'debug': True,
                    'debug_callback': self.debug_callback
                }
            
            # Create switch operation
            switch_op = SwitchOperation(
                ip=ip,
                username=switch['username'],
                password=switch['password'],
                debug=debug_params.get('debug', False),
                debug_callback=debug_params.get('debug_callback')
            )
            
            # Connect to switch
            if not switch_op.connect():
                self.perror(f"Failed to connect to switch {ip}")
                return
            
            # Set hostname
            if not switch_op.set_hostname():
                self.perror(f"Failed to set hostname for switch {ip}")
                switch_op.disconnect()
                return
            
            # Update switch data in inventory
            self.switches[ip]['hostname'] = switch_op.hostname
            self.switches[ip]['model'] = switch_op.model
            self.switches[ip]['serial'] = switch_op.serial
            
            # Disconnect
            switch_op.disconnect()
            
            self.poutput(f"Set hostname for switch {ip} to {switch_op.hostname}")
            
        except Exception as e:
            self.perror(f"Error setting hostname for switch {ip}: {e}")
            return
    
    def _add_switch(self, ip: str, username: str, password: str):
        """Add a switch to the inventory"""
        # Validate IP address
        if not self._validate_ip(ip):
            self.perror(f"Invalid IP address: {ip}")
            return
        
        # If username is the default one and preferred password is set, notify the user
        if username.lower() == DEFAULT_USERNAME.lower() and self.default_credentials['preferred_password']:
            self.poutput(f"Note: Will use default '{DEFAULT_PASSWORD}' for initial login and then change to your configured password")
            
        # Store switch info (would connect and validate in real implementation)
        self.switches[ip] = {
            'ip': ip,
            'username': username,
            'password': password,
            'status': 'Added',
            'configured': False
        }
        
        self.poutput(f"Switch {ip} added to inventory")
    
    def _validate_ip(self, ip: str) -> bool:
        """Validate IPv4 address format"""
        pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
        if not pattern.match(ip):
            return False
        
        # Check each octet is within range
        octets = ip.split('.')
        for octet in octets:
            if int(octet) > 255:
                return False
                
        return True
    
    def _show_switches(self):
        """Show configured switches"""
        # Sync inventory if the method exists
        if hasattr(self, '_sync_inventory'):
            self._sync_inventory()
            
        if not self.switches:
            self.poutput("No switches configured")
            return
            
        # Create a formatted table
        self.poutput("\nSwitches:")
        self.poutput("---------------------------------------------------------------------------------")
        self.poutput(f"{'IP Address':<15} {'Hostname':<20} {'Model':<12} {'Serial':<12} {'Status':<10}")
        self.poutput("---------------------------------------------------------------------------------")
        
        for ip, switch in self.switches.items():
            hostname = switch.get('hostname', f"switch-{ip.replace('.', '-')}")
            
            # Handle model - ensure it's a string and has a value
            model = switch.get('model')
            if model is None or not isinstance(model, str):
                model = 'Unknown'
                
            # Handle serial - ensure it's a string and has a value
            serial = switch.get('serial')
            if serial is None or not isinstance(serial, str):
                serial = 'Unknown'
                
            # Handle status
            status = switch.get('status', 'Unknown')
            
            # Use safe slicing to prevent errors
            hostname_display = hostname[:20] if isinstance(hostname, str) else 'Unknown'
            model_display = model[:12] if isinstance(model, str) else 'Unknown'
            serial_display = serial[:12] if isinstance(serial, str) else 'Unknown'
            
            self.poutput(
                f"{ip:<15} {hostname_display:<20} {model_display:<12} {serial_display:<12} {status:<10}"
            )
        self.poutput("---------------------------------------------------------------------------------\n")