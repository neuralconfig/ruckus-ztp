"""Unit tests for configuration module."""

import os
import tempfile
import unittest
from ztp_edge_agent.core.config import ProxyConfig


class TestProxyConfig(unittest.TestCase):
    """Test proxy configuration."""
    
    def test_from_args(self):
        """Test creating config from arguments."""
        config = ProxyConfig.from_args(
            server_url="wss://test.com",
            auth_token="test-token",
            proxy_id="test-proxy",
            reconnect_interval=45,
            command_timeout=120
        )
        
        self.assertEqual(config.server_url, "wss://test.com")
        self.assertEqual(config.auth_token, "test-token")
        self.assertEqual(config.proxy_id, "test-proxy")
        self.assertEqual(config.reconnect_interval, 45)
        self.assertEqual(config.command_timeout, 120)
    
    def test_from_file(self):
        """Test loading config from INI file."""
        config_content = """
[server]
url = wss://backend.example.com
token = secret-token

[proxy]
id = proxy-001
reconnect_interval = 60
command_timeout = 90

[logging]
level = DEBUG
file = /tmp/test.log
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as f:
            f.write(config_content)
            f.flush()
            
            try:
                config = ProxyConfig.from_file(f.name)
                
                self.assertEqual(config.server_url, "wss://backend.example.com")
                self.assertEqual(config.auth_token, "secret-token")
                self.assertEqual(config.proxy_id, "proxy-001")
                self.assertEqual(config.reconnect_interval, 60)
                self.assertEqual(config.command_timeout, 90)
                self.assertEqual(config.log_level, "DEBUG")
                self.assertEqual(config.log_file, "/tmp/test.log")
            finally:
                os.unlink(f.name)
    
    def test_from_file_missing(self):
        """Test loading config from missing file."""
        with self.assertRaises(FileNotFoundError):
            ProxyConfig.from_file("/nonexistent/config.ini")
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = ProxyConfig(
            server_url="wss://test.com",
            auth_token="token",
            proxy_id="test-id",
            hostname="test-host",
            network_subnet="192.168.1.0/24"
        )
        
        config_dict = config.to_dict()
        
        self.assertEqual(config_dict["server_url"], "wss://test.com")
        self.assertEqual(config_dict["proxy_id"], "test-id")
        self.assertEqual(config_dict["hostname"], "test-host")
        self.assertEqual(config_dict["network_subnet"], "192.168.1.0/24")
        self.assertNotIn("auth_token", config_dict)  # Token should not be in dict
    
    def test_defaults(self):
        """Test default values."""
        config = ProxyConfig(
            server_url="wss://test.com",
            auth_token="token"
        )
        
        self.assertIsNone(config.proxy_id)
        self.assertEqual(config.reconnect_interval, 30)
        self.assertEqual(config.command_timeout, 60)
        self.assertEqual(config.max_concurrent_commands, 1)
        self.assertEqual(config.log_level, "INFO")
        self.assertIsNone(config.log_file)


if __name__ == '__main__':
    unittest.main()