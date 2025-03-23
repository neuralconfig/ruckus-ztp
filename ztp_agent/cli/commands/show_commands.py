"""
Show commands for the CLI.
"""
import argparse
from cmd2 import with_category, with_argparser

# Define command categories
CMD_CATEGORY_SHOW = "Show Commands"


class ShowCommandsMixin:
    """Show commands for the CLI"""
    
    #
    # Show Commands
    #
    show_parser = argparse.ArgumentParser(description='Show information')
    show_subparsers = show_parser.add_subparsers(dest='show_command')
    
    # Show subcommands
    show_subparsers.add_parser('switches', help='Show configured switches')
    show_subparsers.add_parser('aps', help='Show discovered APs')
    show_subparsers.add_parser('ztp', help='Show ZTP status')
    show_subparsers.add_parser('vlans', help='Show configured VLANs')
    
    @with_category(CMD_CATEGORY_SHOW)
    @with_argparser(show_parser)
    def do_show(self, args):
        """Show ZTP configuration and status"""
        if not args.show_command:
            self.do_help('show')
            return
            
        if args.show_command == 'switches':
            self._show_switches()
        elif args.show_command == 'aps':
            self._show_aps()
        elif args.show_command == 'ztp':
            self._show_ztp_status()
        elif args.show_command == 'vlans':
            self._show_vlans()
    
    def _show_aps(self):
        """Show discovered APs"""
        # Sync inventory if the method exists
        if hasattr(self, '_sync_inventory'):
            self._sync_inventory()
            
        if not self.aps:
            self.poutput("No APs discovered")
            return
            
        # Create a formatted table
        self.poutput("\nDiscovered Access Points:")
        self.poutput("---------------------------------------------------------------------------------")
        self.poutput(f"{'IP Address':<15} {'System Name':<15} {'MAC Address':<17} {'Status':<12} {'Connected To':<20}")
        self.poutput("---------------------------------------------------------------------------------")
        
        for ip, ap in self.aps.items():
            system_name = ap.get('system_name', 'Unknown')
            mac = ap.get('mac', 'Unknown')
            status = ap.get('status', 'Unknown')
            
            # Get connection info
            connected_to = ""
            if 'connected_to' in ap:
                switch_ip = ap['connected_to'].get('switch_ip', '')
                port = ap['connected_to'].get('port', '')
                connected_to = f"{switch_ip} ({port})"
            
            self.poutput(
                f"{ip:<15} {system_name[:15]:<15} {mac:<17} {status:<12} {connected_to[:20]:<20}"
            )
        self.poutput("---------------------------------------------------------------------------------\n")