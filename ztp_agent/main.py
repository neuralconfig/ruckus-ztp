"""
Updated main module for ZTP Agent CLI application
"""
import os
import sys
import logging
import argparse
import configparser
from typing import Dict, List, Optional, Any

# Import our modules
from ztp_agent.cli.base import ZTPAgentCLI
from ztp_agent.ztp.process import ZTPProcess
from ztp_agent.agent.chat_interface import ChatInterface

# Setup logging
def setup_logging(log_level: str = "INFO"):
    """Set up logging configuration"""
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.expanduser('~/.ztp_agent.log'))
        ]
    )
    
    # Return logger for main module
    return logging.getLogger('ztp_agent')

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from file.
    
    Args:
        config_path: Path to configuration file.
        
    Returns:
        Configuration dictionary.
    """
    config = {
        'ztp': {
            'poll_interval': 60,
        },
        'network': {
            'vlans': {
                'default': 1,
                'management': 10,
                'wireless': [20, 30, 40]
            },
            'ip_pool': '192.168.10.0/24',
            'gateway': '192.168.10.1',
        },
        'agent': {
            'openrouter_api_key': '',
            'model': 'anthropic/claude-3-5-haiku',
        }
    }
    
    # Expand path
    config_path = os.path.expanduser(config_path)
    
    # If config file exists, load it
    if os.path.exists(config_path):
        try:
            parser = configparser.ConfigParser()
            parser.read(config_path)
            
            # Parse each section
            for section in parser.sections():
                if section not in config:
                    config[section] = {}
                
                for key, value in parser[section].items():
                    # Handle special cases
                    if section == 'network' and key == 'wireless_vlans':
                        config[section]['vlans']['wireless'] = [int(v.strip()) for v in value.split(',')]
                    elif section == 'network' and key in ['default_vlan', 'management_vlan']:
                        config[section]['vlans'][key.split('_')[0]] = int(value)
                    else:
                        # Try to convert to int if possible
                        try:
                            config[section][key] = int(value)
                        except ValueError:
                            config[section][key] = value
            
            return config
        
        except Exception as e:
            print(f"Error loading config from {config_path}: {e}")
            print("Using default configuration")
    
    return config

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='RUCKUS ZTP Agent CLI')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level')
    parser.add_argument('--config', default='~/.ztp_agent.cfg',
                        help='Path to configuration file')
    
    return parser.parse_args()

class EnhancedZTPAgentCLI(ZTPAgentCLI):
    """Enhanced CLI with ZTP and chat functionality"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the CLI with configuration.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        
        # Save configuration
        self.config = config
        
        # Initialize ZTP process
        self.ztp_process = ZTPProcess(config['network'])
        
        # Initialize chat interface (only if API key is provided)
        if config['agent'].get('openrouter_api_key'):
            self.chat_interface = ChatInterface(
                openrouter_api_key=config['agent']['openrouter_api_key'],
                model=config['agent']['model'],
                switches=self.switches
            )
        else:
            self.chat_interface = None
    
    # Override methods to use ZTP process
    def _add_switch(self, ip: str, username: str, password: str):
        """Add a switch to the inventory"""
        # Check for default credentials
        actual_password = password
        
        # If using super user with first time login, use default password
        if username.lower() == 'super' and password != 'sp-admin':
            self.poutput(f"Using default password 'sp-admin' for initial connection to {ip}")
            self.poutput(f"The password will be changed to your specified password during first login")
            # For the initial connection we use the default password, then change it
            actual_password = 'sp-admin'
        
        success = self.ztp_process.add_switch(ip, username, actual_password)
        
        if success:
            # Update CLI switches dictionary
            self.switches[ip] = {
                'ip': ip,
                'username': username,
                'password': password,  # Store the user-specified password
                'status': 'Added',
                'configured': False
            }
            
            self.poutput(f"Switch {ip} added to inventory")
        else:
            self.perror(f"Failed to add switch {ip}")
    
    def _enable_ztp(self):
        """Enable ZTP process"""
        if not self.switches:
            self.perror("No switches configured. Add at least one switch using 'config switch' command")
            return
        
        success = self.ztp_process.start()
        
        if success:
            self.ztp_enabled = True
            self.poutput("ZTP process enabled")
            self.poutput("Starting discovery process...")
        else:
            self.perror("Failed to start ZTP process")
    
    def _disable_ztp(self):
        """Disable ZTP process"""
        success = self.ztp_process.stop()
        
        if success:
            self.ztp_enabled = False
            self.poutput("ZTP process disabled")
        else:
            self.perror("Failed to stop ZTP process")
    
    def _show_ztp_status(self):
        """Show ZTP status"""
        status = self.ztp_process.get_status()
        
        self.poutput("\nZTP Status:")
        self.poutput("--------------------------------------------------")
        self.poutput(f"ZTP Enabled: {'Yes' if status['running'] else 'No'}")
        self.poutput(f"Configured Switches: {status['configured_switches']}/{status['switches']}")
        self.poutput(f"Discovered APs: {status['aps']}")
        self.poutput(f"Last Update: {status['last_update']}")
        self.poutput("--------------------------------------------------\n")
    
    def do_chat(self, _):
        """Enter chat interface with AI agent"""
        if not self.chat_interface:
            self.perror("Chat interface not available. Please configure OpenRouter API key.")
            self.poutput("Use 'config agent openrouter_key YOUR_API_KEY' to set the API key.")
            return
        
        self.poutput("\nEntering chat interface. Type 'exit' to return to CLI.")
        
        # Run interactive chat session
        self.chat_interface.run_interactive()
        
        self.poutput("Exiting chat interface\n")

def main():
    """Main entry point for the application"""
    # Parse command line arguments
    args = parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    logger.info("Starting RUCKUS ZTP Agent CLI")
    
    # Load configuration
    config = load_config(args.config)
    logger.debug(f"Loaded configuration: {config}")
    
    try:
        # Initialize and run enhanced CLI
        cli = EnhancedZTPAgentCLI(config)
        
        # Start the CLI loop
        return cli.cmdloop()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
        return 0
    except Exception as e:
        logger.exception(f"Unhandled exception: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
