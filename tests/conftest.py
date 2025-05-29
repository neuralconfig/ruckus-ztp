"""
Pytest configuration and fixtures for ZTP Agent tests.
"""
import pytest
from unittest.mock import Mock, MagicMock
import paramiko

@pytest.fixture
def mock_ssh_client():
    """Mock SSH client for testing without real connections."""
    mock_client = Mock(spec=paramiko.SSHClient)
    mock_shell = Mock(spec=paramiko.Channel)
    
    # Configure shell mock
    mock_shell.recv_ready.side_effect = [True, False]  # First call True, then False to exit loops
    mock_shell.recv.return_value = b"ICX7250-48P>test output\n"
    mock_shell.settimeout = Mock()
    mock_shell.send = Mock()
    mock_shell.close = Mock()
    
    # Configure client mock
    mock_client.connect = Mock()
    mock_client.invoke_shell.return_value = mock_shell
    mock_client.close = Mock()
    
    return mock_client, mock_shell

@pytest.fixture
def sample_switch_config():
    """Sample switch configuration for testing."""
    return {
        'ip': '192.168.1.1',
        'username': 'super',
        'password': 'sp-admin',
        'preferred_password': 'newpassword',
        'timeout': 30,
        'debug': False
    }

@pytest.fixture
def sample_lldp_output():
    """Sample LLDP neighbor output for testing discovery."""
    return """
Port  Neighbor         Port ID        Neighbor ID/Sys Name
1/1/1 192.168.1.2      1/1/2         ICX7250-48P-001
1/1/2 AP-001           eth0          RUCKUS-AP-001
    """

@pytest.fixture
def sample_version_output():
    """Sample version output for testing device info."""
    return """
RUCKUS ICX7250-48P Router
System Mode: Routing
System Type: ICX7250-48P
Burned In MAC Address: 00:11:22:33:44:55
Software Version: 08.0.95hT213
Serial Number: ABC123456789
System uptime is 2 days 3 hours 45 minutes
    """

@pytest.fixture
def mock_debug_callback():
    """Mock debug callback for testing."""
    return Mock()