"""
CLI framework for ZTP Agent with network engineer-friendly interface
"""
import cmd2
import os
import sys
import re
from cmd2 import with_argparser, with_category
import argparse
from typing import List, Dict, Any, Optional
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

# Define command categories
CMD_CATEGORY_CONFIG = "Configuration Commands"
CMD_CATEGORY_SHOW = "Show Commands"
CMD_CATEGORY_ZTP = "ZTP Commands"
CMD_CATEGORY_CHAT = "Chat Interface Commands"


class ZTPAgentCLI(cmd2.Cmd):
    """ZTP Agent Command Line Interface"""
    
    prompt = "ztp-agent> "
    intro = """
    ====================================
     RUCKUS ZTP Agent CLI
    ====================================
    Type 'help' or '?' for available commands.
    """
    
    def __init__(self):
        # History file in user's home directory
        history_file = os.path.expanduser('~/.ztp_agent_history')
        super().__init__(allow_cli_args=False, allow_redirection=False, 
                         persistent_history_file=history_file)
        
        # Disable some default commands we don't need
        try:
            # For newer versions of cmd2
            self.remove_command('edit')
            self.remove_command('macro')
            self.remove_command('shell')
        except (AttributeError, TypeError):
            # For older versions of cmd2
            # Just hide them in the help
            if hasattr(self, 'hidden_commands'):
                self.hidden_commands.extend(['edit', 'macro', 'shell'])
            else:
                self.hidden_commands = ['edit', 'macro', 'shell']
        
        # Set up agent and ZTP components
        self.ztp_enabled = False
        self.switches = {}  # Will store discovered switches
        self.aps = {}       # Will store discovered APs
        
        # Initialize agent (to be implemented)
        self.agent = None
        
        # Configure command settings
        self.default_category = 'General Commands'

    #
    # Configuration Commands
    #
    config_parser = argparse.ArgumentParser(description='Configure ZTP agent')
    config_subparsers = config_parser.add_subparsers(dest='config_command')
    
    # Switch config subcommand
    switch_parser = config_subparsers.add_parser('switch', help='Configure switch')
    switch_parser.add_argument('ip', help='Switch IP address')
    switch_parser.add_argument('username', help='Switch username')
    switch_parser.add_argument('password', help='Switch password')
    
    @with_category(CMD_CATEGORY_CONFIG)
    @with_argparser(config_parser)
    def do_config(self, args):
        """Configure ZTP agent settings"""
        if not args.config_command:
            self.do_help('config')
            return
            
        if args.config_command == 'switch':
            self._add_switch(args.ip, args.username, args.password)
    
    def _add_switch(self, ip: str, username: str, password: str):
        """Add a switch to the inventory"""
        # Validate IP address
        if not self._validate_ip(ip):
            self.perror(f"Invalid IP address: {ip}")
            return
            
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

    #
    # ZTP Commands
    #
    ztp_parser = argparse.ArgumentParser(description='ZTP operations')
    ztp_subparsers = ztp_parser.add_subparsers(dest='ztp_command')
    
    # ZTP enable/disable commands
    ztp_subparsers.add_parser('enable', help='Enable ZTP process')
    ztp_subparsers.add_parser('disable', help='Disable ZTP process')
    
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

    #
    # Show Commands
    #
    show_parser = argparse.ArgumentParser(description='Show information')
    show_subparsers = show_parser.add_subparsers(dest='show_command')
    
    # Show subcommands
    show_subparsers.add_parser('switches', help='Show configured switches')
    show_subparsers.add_parser('aps', help='Show discovered APs')
    show_subparsers.add_parser('ztp', help='Show ZTP status')
    
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
    
    def _show_switches(self):
        """Show configured switches"""
        if not self.switches:
            self.poutput("No switches configured")
            return
            
        # Create a formatted table
        self.poutput("\nConfigured Switches:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"{'IP Address':<15} {'Status':<12} {'Configured':<10}")
        self.poutput("--------------------------------------------------")
        
        for ip, switch in self.switches.items():
            self.poutput(
                f"{ip:<15} {switch['status']:<12} {'Yes' if switch['configured'] else 'No':<10}"
            )
        self.poutput("--------------------------------------------------\n")
    
    def _show_aps(self):
        """Show discovered APs"""
        if not self.aps:
            self.poutput("No APs discovered")
            return
            
        # Create a formatted table
        self.poutput("\nDiscovered Access Points:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"{'MAC Address':<17} {'IP Address':<15} {'Status':<12}")
        self.poutput("--------------------------------------------------")
        
        for mac, ap in self.aps.items():
            self.poutput(
                f"{mac:<17} {ap.get('ip', 'Unknown'):<15} {ap.get('status', 'Unknown'):<12}"
            )
        self.poutput("--------------------------------------------------\n")
    
    def _show_ztp_status(self):
        """Show ZTP status"""
        self.poutput("\nZTP Status:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"ZTP Enabled: {'Yes' if self.ztp_enabled else 'No'}")
        self.poutput(f"Configured Switches: {len(self.switches)}")
        self.poutput(f"Discovered APs: {len(self.aps)}")
        # Add more status information as needed
        self.poutput("--------------------------------------------------\n")

    #
    # Chat Interface Commands
    #
    @with_category(CMD_CATEGORY_CHAT)
    def do_chat(self, _):
        """Enter chat interface with AI agent"""
        self.poutput("\nEntering chat interface. Type 'exit' to return to CLI.")
        
        # Simple chat loop
        while True:
            user_input = input("You: ")
            if user_input.lower() in ('exit', 'quit'):
                break
                
            # Here you would pass the input to your agent
            # For now, just echo back
            print(f"Agent: I received: {user_input}")
        
        self.poutput("Exiting chat interface\n")

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


def main():
    """Main entry point for the CLI"""
    cli = ZTPAgentCLI()
    sys.exit(cli.cmdloop())


if __name__ == "__main__":
    main()
