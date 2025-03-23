"""
Zero Touch Provisioning commands for CLI.
"""
import logging
import argparse
from cmd2 import with_category, with_argparser

# Define command categories
CMD_CATEGORY_ZTP = "ZTP Commands"


class ZTPCommandsMixin:
    """ZTP command functionality for CLI"""
    
    #
    # ZTP Commands
    #
    ztp_parser = argparse.ArgumentParser(description='ZTP operations')
    ztp_subparsers = ztp_parser.add_subparsers(dest='ztp_command')
    
    # ZTP enable/disable commands
    ztp_subparsers.add_parser('enable', help='Enable ZTP process')
    ztp_subparsers.add_parser('disable', help='Disable ZTP process')
    
    # Discovery command
    discover_parser = ztp_subparsers.add_parser('discover', help='Run discovery on a specific switch')
    discover_parser.add_argument('ip', help='IP address of the switch to run discovery on')
    
    @with_category(CMD_CATEGORY_ZTP)
    @with_argparser(ztp_parser)
    def do_ztp(self, args):
        """Zero Touch Provisioning operations"""
        if not args.ztp_command:
            self.do_help('ztp')
            return
            
        if args.ztp_command == 'enable':
            self._enable_ztp()
        elif args.ztp_command == 'disable':
            self._disable_ztp()
        elif args.ztp_command == 'discover':
            self._discover_switch(args.ip)
    
    def _enable_ztp(self):
        """Enable ZTP process"""
        if not self.switches:
            self.perror("No switches configured. Add at least one switch using 'config switch' command")
            return
            
        self.ztp_enabled = True
        self.poutput("ZTP process enabled")
        self.poutput("Starting discovery process...")
        # Here you would start your actual ZTP process
    
    def _disable_ztp(self):
        """Disable ZTP process"""
        self.ztp_enabled = False
        self.poutput("ZTP process disabled")
        
    def _discover_switch(self, ip: str):
        """
        Run discovery on a specific switch to find connected devices.
        
        Args:
            ip: IP address of the switch to discover.
        """
        # Check if the switch exists in the inventory
        if ip not in self.switches:
            self.perror(f"Switch {ip} not found in inventory")
            return
            
        self.poutput(f"Running discovery on switch {ip}...")
        
        # Create SwitchOperation instance
        try:
            # Import here to avoid circular imports
            from ztp_agent.network.switch import SwitchOperation
            
            # Get switch info
            switch = self.switches[ip]
            
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
                
            # Get LLDP neighbors (this will now also run trace-l2)
            success, neighbors = switch_op.get_lldp_neighbors()
            
            # Disconnect from switch
            switch_op.disconnect()
            
            if not success:
                self.perror(f"Failed to get neighbor information from switch {ip}")
                return
                
            # Update switch neighbors in inventory
            self.switches[ip]['neighbors'] = neighbors
            
            # Count devices by type
            switch_count = sum(1 for n in neighbors.values() if n.get('type') == 'switch')
            ap_count = sum(1 for n in neighbors.values() if n.get('type') == 'ap')
            other_count = sum(1 for n in neighbors.values() if n.get('type') != 'switch' and n.get('type') != 'ap')
            
            # Show discovery results
            self.poutput(f"Discovery completed on switch {ip}")
            self.poutput(f"Found {switch_count} switches, {ap_count} APs, and {other_count} other devices")
            
            # Display discovered switches
            if switch_count > 0:
                self.poutput("\nDiscovered Switches:")
                self.poutput("---------------------------------------------------------------------------------")
                self.poutput(f"{'Port':<10} {'System Name':<20} {'IP Address':<15} {'MAC Address':<17}")
                self.poutput("---------------------------------------------------------------------------------")
                
                for port, neighbor in neighbors.items():
                    if neighbor.get('type') == 'switch':
                        system_name = neighbor.get('system_name', 'Unknown')
                        ip_addr = neighbor.get('mgmt_address', 'Unknown')
                        mac = neighbor.get('chassis_id', 'Unknown')
                        
                        self.poutput(f"{port:<10} {system_name[:20]:<20} {ip_addr:<15} {mac:<17}")
                
                self.poutput("---------------------------------------------------------------------------------")
            
            # Display discovered APs
            if ap_count > 0:
                self.poutput("\nDiscovered Access Points:")
                self.poutput("---------------------------------------------------------------------------------")
                self.poutput(f"{'Port':<10} {'System Name':<20} {'IP Address':<15} {'MAC Address':<17}")
                self.poutput("---------------------------------------------------------------------------------")
                
                for port, neighbor in neighbors.items():
                    if neighbor.get('type') == 'ap':
                        system_name = neighbor.get('system_name', 'Unknown')
                        ip_addr = neighbor.get('mgmt_address', 'Unknown')
                        mac = neighbor.get('chassis_id', 'Unknown')
                        
                        self.poutput(f"{port:<10} {system_name[:20]:<20} {ip_addr:<15} {mac:<17}")
                
                self.poutput("---------------------------------------------------------------------------------")
            
        except Exception as e:
            self.perror(f"Error during discovery on switch {ip}: {e}")
            
    def _show_ztp_status(self):
        """Show ZTP status"""
        self.poutput("\nZTP Status:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"ZTP Enabled: {'Yes' if self.ztp_enabled else 'No'}")
        self.poutput(f"Configured Switches: {len(self.switches)}")
        self.poutput(f"Discovered APs: {len(self.aps)}")
        self.poutput(f"Configured VLANs: {len(self.vlans)}")
        self.poutput(f"Management VLAN: {self.default_management_vlan_id}")
        # Add more status information as needed
        self.poutput("--------------------------------------------------\n")