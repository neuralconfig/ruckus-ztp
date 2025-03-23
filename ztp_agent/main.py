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
from ztp_agent.cli.base import (
    ZTPAgentCLI, DEFAULT_USERNAME, DEFAULT_PASSWORD, VLAN,
    VLAN_TYPE_MANAGEMENT, VLAN_TYPE_WIRELESS, VLAN_TYPE_OTHER
)
from ztp_agent.cli.commands.vlan_commands import VLAN_TYPE_DATA
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

# Import config loading function instead of defining it here
from ztp_agent.ztp.config import load_config

# Keep this as a backup reference but it's not used anymore
def _load_config_old(config_path: str) -> Dict[str, Any]:
    """
    DEPRECATED: Use ztp_agent.ztp.config.load_config instead.
    
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
            # Initialize with empty dicts to be filled from config
            'default_vlan': 1,
            'management_vlan': 10,
            'wireless_vlans': [20, 30, 40],
            'other_vlans': [50, 60],
            'vlans': {},  # Will store individual VLAN definitions
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
                    # Handle special cases for VLANs
                    if section == 'network' and key == 'wireless_vlans':
                        config[section]['wireless_vlans'] = [int(v.strip()) for v in value.split(',')]
                    elif section == 'network' and key == 'other_vlans':
                        config[section]['other_vlans'] = [int(v.strip()) for v in value.split(',')]
                    elif section == 'network' and key in ['default_vlan', 'management_vlan']:
                        config[section][key] = int(value)
                    # Handle individual VLAN definitions (format: vlan_ID_property)
                    elif section == 'network' and key.startswith('vlan_') and '_' in key[5:]:
                        try:
                            parts = key.split('_')
                            if len(parts) >= 3:
                                vlan_id = int(parts[1])
                                property_name = '_'.join(parts[2:])
                                
                                if vlan_id not in config[section]['vlans']:
                                    config[section]['vlans'][vlan_id] = {}
                                
                                config[section]['vlans'][vlan_id][property_name] = value
                        except (ValueError, IndexError) as e:
                            logging.warning(f"Invalid VLAN config key: {key} - {e}")
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
    parser.add_argument('--password', 
                        help='Set preferred password for super user')
    parser.add_argument('--seed-ip', 
                        help='IP address of seed switch to automatically add')
    parser.add_argument('--debug', action='store_true',
                        help='Enable debug mode to display all switch commands and responses')
    
    return parser.parse_args()

class EnhancedZTPAgentCLI(ZTPAgentCLI):
    """Enhanced CLI with ZTP and chat functionality with persistent configuration"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the CLI with configuration.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        
        # Save configuration
        self.config = config
        
        # Set preferred password if configured
        if config.get('switches', {}).get('preferred_password'):
            self.default_credentials['preferred_password'] = config['switches']['preferred_password']
            print(f"Using configured preferred password for '{DEFAULT_USERNAME}' user")
            
        # Set debug mode if configured
        if config.get('debug', {}).get('enabled', False):
            self.debug_mode = True
            print("Debug mode enabled - switch commands and responses will be displayed in yellow")
        
        # Load VLANs from config if present
        self._load_vlans_from_config(config)
        
        # Initialize ZTP process with debug callback if debug mode is enabled
        # Use the full config, not just the network section
        ztp_config = config.copy()  
        if self.debug_mode:
            ztp_config['debug'] = True
            ztp_config['debug_callback'] = self.debug_callback
            
        self.ztp_process = ZTPProcess(ztp_config)
        
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
        target_password = password
        
        # If using super user with first time login
        if username.lower() == DEFAULT_USERNAME.lower():
            # For first login, always use the default password
            if password != DEFAULT_PASSWORD:
                self.poutput(f"Using default password '{DEFAULT_PASSWORD}' for initial connection to {ip}")
                actual_password = DEFAULT_PASSWORD
                
                # If we have a preferred password configured, use that instead of the provided password
                if self.default_credentials['preferred_password']:
                    target_password = self.default_credentials['preferred_password']
                    self.poutput(f"Will change to your configured preferred password during first login")
                else:
                    self.poutput(f"Will change to your specified password '{password}' during first login")
        
        # Pass debug flag and callback if debug mode is enabled
        debug_params = {}
        if self.debug_mode:
            debug_params = {
                'debug': True,
                'debug_callback': self.debug_callback
            }
        
        success = self.ztp_process.add_switch(ip, username, actual_password, preferred_password=target_password, **debug_params)
        
        if success:
            # Get switch information from ZTP process, including hostname if available
            switch_info = self.ztp_process.get_switch_info(ip)
            
            # Update CLI switches dictionary
            self.switches[ip] = {
                'ip': ip,
                'username': username,
                'password': target_password,  # Store the target password (for future connections)
                'initial_password': actual_password,  # Store the initial password (for first connection)
                'status': 'Added',
                'configured': False,
                'hostname': switch_info.get('hostname', f"switch-{ip.replace('.', '-')}"),
                'model': switch_info.get('model'),
                'serial': switch_info.get('serial')
            }
            
            # Print switch information including model and serial if available
            self.poutput(f"Switch {ip} added to inventory")
            if switch_info.get('model') and switch_info.get('serial'):
                self.poutput(f"Model: {switch_info.get('model')}, Serial: {switch_info.get('serial')}")
                self.poutput(f"Hostname: {switch_info.get('hostname')}")
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
            
    def _set_preferred_password(self, password: str):
        """
        Override to save the preferred password to the config file.
        """
        # Call the parent class method to set the password in memory
        super()._set_preferred_password(password)
        
        # Now save it to the config file
        if 'switches' not in self.config:
            self.config['switches'] = {}
        
        self.config['switches']['preferred_password'] = password
        
        # Save the config file
        self._save_config()
        
        self.poutput("Preferred password saved to configuration file")
        
    def _load_vlans_from_csv(self, file_path: str):
        """
        Override to save VLANs to the config file after loading from CSV.
        """
        # Call the parent class method to load VLANs
        super()._load_vlans_from_csv(file_path)
        
        # Save to config
        self._save_vlans_to_config()
        
        self.poutput("VLANs saved to configuration file")
        
    def _add_vlan(self, vlan_id: int, name: str, vlan_type: str, description: str = ""):
        """
        Override to save VLANs to the config file after adding.
        """
        # Call the parent class method to add the VLAN
        super()._add_vlan(vlan_id, name, vlan_type, description)
        
        # Save to config
        self._save_vlans_to_config()
        
        self.poutput("VLAN configuration saved to configuration file")
        
    def _set_management_vlan(self, vlan_id: int):
        """
        Override to save the management VLAN ID to the config file.
        """
        # Call the parent class method to set the management VLAN
        super()._set_management_vlan(vlan_id)
        
        # Save to config
        self._save_vlans_to_config()
        
        self.poutput("Management VLAN saved to configuration file")
        
    def _load_vlans_from_config(self, config: Dict[str, Any]):
        """
        Load VLANs from the configuration.
        
        Args:
            config: Configuration dictionary.
        """
        try:
            # Reset VLANs to empty dictionary
            self.vlans = {}
            
            # Get network configuration
            network_config = config.get('network', {})
            
            # Get management VLAN ID
            if 'management_vlan' in network_config:
                self.default_management_vlan_id = int(network_config['management_vlan'])
            
            # Create default VLANs first
            default_vlan_id = network_config.get('default_vlan', 1)
            self.vlans[default_vlan_id] = VLAN(
                id=default_vlan_id,
                name="Default", 
                type=VLAN_TYPE_OTHER,
                description="Default VLAN"
            )
            
            # Management VLAN
            management_vlan_id = self.default_management_vlan_id
            self.vlans[management_vlan_id] = VLAN(
                id=management_vlan_id,
                name="Management", 
                type=VLAN_TYPE_MANAGEMENT,
                description="Management network (default)"
            )
            
            # Wireless VLANs
            if 'wireless_vlans' in network_config and network_config['wireless_vlans']:
                for vlan_id in network_config['wireless_vlans']:
                    if vlan_id not in self.vlans:
                        self.vlans[vlan_id] = VLAN(
                            id=vlan_id,
                            name=f"Wireless-{vlan_id}",
                            type=VLAN_TYPE_WIRELESS,
                            description=f"Wireless VLAN {vlan_id}"
                        )
            
            # Other VLANs
            if 'other_vlans' in network_config and network_config['other_vlans']:
                for vlan_id in network_config['other_vlans']:
                    if vlan_id not in self.vlans:
                        self.vlans[vlan_id] = VLAN(
                            id=vlan_id,
                            name=f"VLAN-{vlan_id}",
                            type=VLAN_TYPE_OTHER,
                            description=f"VLAN {vlan_id}"
                        )
            
            # Now check for specific VLAN overrides from vlans dictionary
            vlan_dict = network_config.get('vlans', {})
            if vlan_dict and isinstance(vlan_dict, dict):
                for vlan_id_str, vlan_data in vlan_dict.items():
                    try:
                        vlan_id = int(vlan_id_str)
                        
                        if vlan_id in self.vlans:
                            # Update existing VLAN if present
                            if 'name' in vlan_data:
                                self.vlans[vlan_id].name = vlan_data['name']
                            if 'type' in vlan_data:
                                self.vlans[vlan_id].type = vlan_data['type']
                            if 'description' in vlan_data:
                                self.vlans[vlan_id].description = vlan_data['description']
                        else:
                            # Create new VLAN
                            vlan = VLAN(
                                id=vlan_id,
                                name=vlan_data.get('name', f"VLAN-{vlan_id}"),
                                type=vlan_data.get('type', VLAN_TYPE_OTHER),
                                description=vlan_data.get('description', '')
                            )
                            self.vlans[vlan_id] = vlan
                    except (ValueError, TypeError) as e:
                        logging.warning(f"Invalid VLAN ID or data: {vlan_id_str} - {str(e)}")
            
            print(f"Loaded {len(self.vlans)} VLANs from configuration")
        
        except Exception as e:
            logging.error(f"Error loading VLANs from config: {str(e)}")
            # Set up basic VLANs
            self.vlans = {
                1: VLAN(id=1, name="Default", type=VLAN_TYPE_OTHER, description="Default VLAN"),
                10: VLAN(id=10, name="Management", type=VLAN_TYPE_MANAGEMENT, description="Management network")
            }
            self.default_management_vlan_id = 10
            print("Error loading VLANs from config. Using default VLANs.")
    
    def _save_vlans_to_config(self):
        """Save VLANs to the configuration file"""
        if 'network' not in self.config:
            self.config['network'] = {}
            
        # Save management VLAN ID
        self.config['network']['management_vlan'] = self.default_management_vlan_id
        
        # Save default VLAN ID
        default_vlans = [v.id for v in self.vlans.values() if v.type == VLAN_TYPE_OTHER and v.id == 1]
        if default_vlans:
            self.config['network']['default_vlan'] = default_vlans[0]
        
        # Save wireless VLANs
        wireless_vlans = [v.id for v in self.vlans.values() if v.type == VLAN_TYPE_WIRELESS]
        if wireless_vlans:
            self.config['network']['wireless_vlans'] = wireless_vlans
        
        # Save other VLANs (except default VLAN 1)
        other_vlans = [v.id for v in self.vlans.values() if v.type == VLAN_TYPE_OTHER and v.id != 1]
        if other_vlans:
            self.config['network']['other_vlans'] = other_vlans
            
        # Save individual VLAN details for customized VLANs
        vlan_dict = {}
        for vlan in self.vlans.values():
            # Only save customized VLANs with non-default names/descriptions
            if (vlan.type == VLAN_TYPE_MANAGEMENT and vlan.name != "Management") or \
               (vlan.type == VLAN_TYPE_OTHER and vlan.id == 1 and vlan.name != "Default") or \
               (vlan.type == VLAN_TYPE_WIRELESS and vlan.name != f"Wireless-{vlan.id}") or \
               (vlan.type == VLAN_TYPE_OTHER and vlan.id != 1 and vlan.name != f"VLAN-{vlan.id}"):
                vlan_dict[str(vlan.id)] = {
                    'name': vlan.name,
                    'type': vlan.type,
                    'description': vlan.description
                }
                
        if vlan_dict:
            self.config['network']['vlans'] = vlan_dict
        
        # Save the config file
        self._save_config()
    
    def _save_config(self):
        """Save the configuration to a file."""
        try:
            # Create a ConfigParser object
            config_parser = configparser.ConfigParser()
            
            # Add sections from our config dictionary
            for section, options in self.config.items():
                if section not in config_parser:
                    config_parser[section] = {}
                
                # Add options for this section
                for key, value in options.items():
                    # Special handling for VLANs
                    if section == 'network' and key == 'vlans':
                        # Save VLANs specially formatted
                        if isinstance(value, dict):
                            for vlan_id, vlan_data in value.items():
                                if isinstance(vlan_data, dict):
                                    config_parser[section][f"vlan_{vlan_id}_name"] = vlan_data.get('name', '')
                                    config_parser[section][f"vlan_{vlan_id}_type"] = vlan_data.get('type', '')
                                    config_parser[section][f"vlan_{vlan_id}_description"] = vlan_data.get('description', '')
                    # Handle different types of values
                    elif isinstance(value, dict):
                        # For nested dictionaries, flatten with key prefix
                        for subkey, subvalue in value.items():
                            config_parser[section][f"{key}_{subkey}"] = str(subvalue)
                    elif isinstance(value, list):
                        # For lists, join with commas
                        config_parser[section][key] = ", ".join(str(item) for item in value)
                    else:
                        # Regular values
                        config_parser[section][key] = str(value)
            
            # Write to file
            config_path = os.path.expanduser('~/.ztp_agent.cfg')
            with open(config_path, 'w') as configfile:
                config_parser.write(configfile)
                
            return True
            
        except Exception as e:
            self.perror(f"Error saving configuration: {e}")
            return False
    
    def _sync_inventory(self):
        """Sync inventory data between ZTP process and CLI"""
        # Sync switches
        for ip, switch in self.ztp_process.inventory['switches'].items():
            # Skip switches already in CLI inventory
            if ip in self.switches:
                continue
                
            # Add newly discovered switch to CLI inventory
            self.switches[ip] = {
                'ip': ip,
                'username': switch.get('username'),
                'password': switch.get('password'),
                'preferred_password': switch.get('preferred_password'),
                'status': switch.get('status', 'Discovered'),
                'configured': switch.get('configured', False),
                'hostname': switch.get('hostname', f"switch-{ip.replace('.', '-')}"),
                'model': switch.get('model'),
                'serial': switch.get('serial')
            }
            
        # Sync APs 
        for ip, ap in self.ztp_process.inventory['aps'].items():
            # Skip APs already in CLI inventory
            if ip in self.aps:
                continue
                
            self.aps[ip] = {
                'ip': ip,
                'mac': ap.get('mac'),
                'system_name': ap.get('hostname'),
                'status': ap.get('status', 'Discovered'),
                'connected_to': ap.get('connected_to', {})
            }
    
    def _show_ztp_status(self):
        """Show ZTP status"""
        # First sync inventory
        self._sync_inventory()
        
        # Get status
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
    
    # Handle command-line supplied password
    if args.password:
        if 'switches' not in config:
            config['switches'] = {}
        config['switches']['preferred_password'] = args.password
        logger.info(f"Using preferred password from command line")
    
    # Set debug mode in config
    if 'debug' not in config:
        config['debug'] = {}
    config['debug']['enabled'] = args.debug
    if args.debug:
        logger.info("Debug mode enabled - will display all switch commands and responses")
    
    try:
        # Initialize enhanced CLI
        cli = EnhancedZTPAgentCLI(config)
        
        # Handle seed switch if provided
        if args.seed_ip:
            logger.info(f"Adding seed switch: {args.seed_ip}")
            # Use default super user and the configured preferred password
            cli._add_switch(args.seed_ip, DEFAULT_USERNAME, 
                          cli.default_credentials.get('preferred_password', DEFAULT_PASSWORD))
        
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
