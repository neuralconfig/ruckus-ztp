"""
Miscellaneous commands for CLI.
"""
from cmd2 import with_category


class MiscCommandsMixin:
    """Miscellaneous commands for CLI"""
    
    #
    # Override special methods
    #
    def emptyline(self):
        """Do nothing on empty line"""
        pass
    
    def default(self, line):
        """Handle unknown command"""
        self.poutput(f"Unknown command: {line}")
        self.poutput("Type 'help' or '?' for available commands")
    
    def help_help(self):
        """Help for help command"""
        self.poutput("Show help for available commands")
        self.poutput("Usage: help [command]")
        self.poutput("       ? [command]")
    
    @with_category("General Commands")
    def do_quickhelp(self, _):
        """Show a quick summary of all available commands"""
        self.poutput("\nQuick Help for RUCKUS ZTP Agent CLI")
        self.poutput("=====================================")
        
        self.poutput("\nConfiguration Commands:")
        self.poutput("  config switch <ip>          - Add a switch to inventory (uses default credentials)")
        self.poutput("  config password <password>  - Set preferred password for 'super' user")
        self.poutput("  config hostname <ip>        - Set switch hostname based on model and serial number")
        
        self.poutput("\nZTP Commands:")
        self.poutput("  ztp enable           - Enable ZTP process")
        self.poutput("  ztp disable          - Disable ZTP process")
        self.poutput("  ztp discover <ip>    - Run discovery on a specific switch")
        
        self.poutput("\nVLAN Commands:")
        self.poutput("  vlan load <file_path>                - Load VLANs from CSV file")
        self.poutput("  vlan add <id> <n> <type>          - Add a single VLAN")
        self.poutput("  vlan set-management <id>             - Set management VLAN ID")
        
        self.poutput("\nShow Commands:")
        self.poutput("  show switches - Show configured switches")
        self.poutput("  show aps      - Show discovered APs")
        self.poutput("  show ztp      - Show ZTP status")
        self.poutput("  show vlans    - Show configured VLANs")
        
        self.poutput("\nChat Commands:")
        self.poutput("  chat - Enter AI-powered chat interface")
        
        self.poutput("\nGeneral Commands:")
        self.poutput("  quickhelp - Show this quick help summary")
        self.poutput("  help or ? - Show detailed help")
        self.poutput("  exit or quit - Exit the application")
        self.poutput("")