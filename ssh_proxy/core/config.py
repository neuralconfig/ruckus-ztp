"""Configuration management for SSH proxy."""

import os
import configparser
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProxyConfig:
    """SSH proxy configuration."""
    
    # Server settings
    server_url: str
    auth_token: str
    
    # Proxy settings
    proxy_id: Optional[str] = None
    reconnect_interval: int = 30
    command_timeout: int = 60
    max_concurrent_commands: int = 1
    
    # Network info
    hostname: Optional[str] = None
    network_subnet: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    
    @classmethod
    def from_file(cls, config_path: str) -> 'ProxyConfig':
        """Load configuration from INI file."""
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        config = configparser.ConfigParser()
        config.read(config_path)
        
        # Required settings
        server_url = config.get('server', 'url')
        auth_token = config.get('server', 'token')
        
        # Optional settings with defaults
        kwargs = {
            'server_url': server_url,
            'auth_token': auth_token,
            'proxy_id': config.get('proxy', 'id', fallback=None),
            'reconnect_interval': config.getint('proxy', 'reconnect_interval', fallback=30),
            'command_timeout': config.getint('proxy', 'command_timeout', fallback=60),
            'max_concurrent_commands': config.getint('proxy', 'max_concurrent_commands', fallback=1),
            'log_level': config.get('logging', 'level', fallback='INFO'),
            'log_file': config.get('logging', 'file', fallback=None),
        }
        
        return cls(**kwargs)
    
    @classmethod
    def from_args(cls, **kwargs) -> 'ProxyConfig':
        """Create configuration from command line arguments."""
        return cls(**kwargs)
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            'server_url': self.server_url,
            'proxy_id': self.proxy_id,
            'reconnect_interval': self.reconnect_interval,
            'command_timeout': self.command_timeout,
            'max_concurrent_commands': self.max_concurrent_commands,
            'hostname': self.hostname,
            'network_subnet': self.network_subnet,
            'log_level': self.log_level,
            'log_file': self.log_file,
        }