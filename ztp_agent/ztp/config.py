"""
Configuration handling for ZTP Agent.
"""
import os
import configparser
import logging
import ipaddress
from typing import Dict, List, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from file.
    
    Args:
        config_path: Path to configuration file.
        
    Returns:
        Configuration dictionary.
    """
    # Default configuration
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
            
            # Validate IP pool and gateway
            _validate_ip_config(config['network'])
            
            logger.info(f"Loaded configuration from {config_path}")
            return config
        
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default configuration")
    else:
        logger.warning(f"Configuration file {config_path} not found, using default configuration")
    
    return config

def _validate_ip_config(network_config: Dict[str, Any]) -> None:
    """
    Validate IP configuration.
    
    Args:
        network_config: Network configuration dictionary.
        
    Raises:
        ValueError: If IP configuration is invalid.
    """
    # Validate IP pool
    ip_pool = network_config.get('ip_pool', '192.168.10.0/24')
    try:
        ipaddress.IPv4Network(ip_pool)
    except ValueError:
        logger.error(f"Invalid IP pool: {ip_pool}")
        network_config['ip_pool'] = '192.168.10.0/24'
    
    # Validate gateway
    gateway = network_config.get('gateway', '192.168.10.1')
    try:
        gateway_ip = ipaddress.IPv4Address(gateway)
        
        # Check if gateway is in IP pool
        network = ipaddress.IPv4Network(network_config['ip_pool'])
        if gateway_ip not in network:
            logger.warning(f"Gateway {gateway} is not in IP pool {network}")
    except ValueError:
        logger.error(f"Invalid gateway: {gateway}")
        network_config['gateway'] = '192.168.10.1'
