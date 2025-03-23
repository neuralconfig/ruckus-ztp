"""
CLI framework for ZTP Agent with network engineer-friendly interface
"""
import cmd2
import os
import sys
from dataclasses import dataclass
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

# Import command mixins
from ztp_agent.cli.commands.switch_commands import SwitchCommandsMixin, DEFAULT_USERNAME, DEFAULT_PASSWORD
from ztp_agent.cli.commands.vlan_commands import VlanCommandsMixin, VLAN_TYPE_MANAGEMENT, VLAN_TYPE_WIRELESS, VLAN_TYPE_OTHER
from ztp_agent.cli.commands.ztp_commands import ZTPCommandsMixin
from ztp_agent.cli.commands.show_commands import ShowCommandsMixin
from ztp_agent.cli.commands.chat_commands import ChatCommandsMixin
from ztp_agent.cli.commands.misc_commands import MiscCommandsMixin


@dataclass
class VLAN:
    """VLAN definition class"""
    id: int
    name: str
    type: str
    description: str = ""
    
    def __str__(self) -> str:
        return f"{self.id:<5} {self.name:<20} {self.type:<10} {self.description}"


class ZTPAgentCLI(cmd2.Cmd, 
                 SwitchCommandsMixin, 
                 VlanCommandsMixin, 
                 ZTPCommandsMixin,
                 ShowCommandsMixin,
                 ChatCommandsMixin,
                 MiscCommandsMixin):
    """ZTP Agent Command Line Interface"""
    
    prompt = "ztp-agent> "
    intro = """
    ====================================
     RUCKUS ZTP Agent CLI
    ====================================
    Type 'quickhelp' for a command summary.
    Type 'help' or '?' for detailed command information.
    """
    
    # Reference to VLAN class for the mixins to use
    VLAN = VLAN
    
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
        
        # Initialize credentials
        self.default_credentials = {
            'username': DEFAULT_USERNAME,
            'password': DEFAULT_PASSWORD,
            'preferred_password': None  # Will be set by the user
        }
        
        # Initialize VLAN management
        self.vlans = {}  # Dictionary of VLAN ID to VLAN object
        self.default_management_vlan_id = 10
        
        # Initialize agent (to be implemented)
        self.agent = None
        
        # Debug mode
        self.debug_mode = False
        
        # Configure command settings
        self.default_category = 'General Commands'
        
    def debug_callback(self, message: str, color: str = "yellow") -> None:
        """
        Callback for debug messages from switch operations
        
        Args:
            message: Message to display
            color: Color to use (default: yellow)
        """
        if not self.debug_mode:
            return
            
        # Use ANSI color codes
        colors = {
            "yellow": "\033[93m",  # Yellow
            "red": "\033[91m",     # Red
            "green": "\033[92m",   # Green
            "blue": "\033[94m",    # Blue
            "reset": "\033[0m"     # Reset
        }
        
        # Display the message with color
        self.poutput(f"{colors.get(color, colors['yellow'])}{message}{colors['reset']}")


def main():
    """Main entry point for the CLI"""
    cli = ZTPAgentCLI()
    sys.exit(cli.cmdloop())


if __name__ == "__main__":
    main()