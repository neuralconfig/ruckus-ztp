"""
Unit tests for the BaseConnection class.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import paramiko

from ztp_agent.network.switch.base.connection import BaseConnection


class TestBaseConnection:
    """Test cases for BaseConnection class."""
    
    def test_init(self, sample_switch_config):
        """Test BaseConnection initialization."""
        conn = BaseConnection(**sample_switch_config)
        
        assert conn.ip == '192.168.1.1'
        assert conn.username == 'super'
        assert conn.password == 'sp-admin'
        assert conn.preferred_password == 'newpassword'
        assert conn.timeout == 30
        assert conn.debug is False
        assert conn.connected is False
        assert conn.ssh_client is None
        assert conn.shell is None
    
    @patch('ztp_agent.network.switch.base.connection.paramiko.SSHClient')
    def test_connect_success(self, mock_ssh_class, sample_switch_config, mock_ssh_client):
        """Test successful connection."""
        mock_client, mock_shell = mock_ssh_client
        mock_ssh_class.return_value = mock_client
        
        # Configure successful connection
        mock_shell.recv.return_value = b"ICX7250-48P>\n"
        
        conn = BaseConnection(**sample_switch_config)
        result = conn.connect()
        
        assert result is True
        assert conn.connected is True
        mock_client.connect.assert_called_once()
        mock_client.invoke_shell.assert_called_once()
    
    @patch('ztp_agent.network.switch.base.connection.paramiko.SSHClient')
    def test_connect_failure(self, mock_ssh_class, sample_switch_config):
        """Test connection failure."""
        mock_client = Mock(spec=paramiko.SSHClient)
        mock_client.connect.side_effect = paramiko.AuthenticationException("Auth failed")
        mock_ssh_class.return_value = mock_client
        
        conn = BaseConnection(**sample_switch_config)
        result = conn.connect()
        
        assert result is False
        assert conn.connected is False
    
    def test_disconnect(self, sample_switch_config, mock_ssh_client):
        """Test disconnection."""
        mock_client, mock_shell = mock_ssh_client
        
        conn = BaseConnection(**sample_switch_config)
        conn.ssh_client = mock_client
        conn.shell = mock_shell
        conn.connected = True
        
        conn.disconnect()
        
        assert conn.connected is False
        assert conn.ssh_client is None
        assert conn.shell is None
        mock_shell.close.assert_called_once()
        mock_client.close.assert_called_once()
    
    def test_run_command_not_connected(self, sample_switch_config):
        """Test running command when not connected."""
        conn = BaseConnection(**sample_switch_config)
        
        success, output = conn.run_command("show version")
        
        assert success is False
        assert "Not connected" in output
    
    def test_run_command_success(self, sample_switch_config, mock_ssh_client):
        """Test successful command execution."""
        mock_client, mock_shell = mock_ssh_client
        mock_shell.recv.return_value = b"Command output\nICX7250-48P>\n"
        
        conn = BaseConnection(**sample_switch_config)
        conn.ssh_client = mock_client
        conn.shell = mock_shell
        conn.connected = True
        
        success, output = conn.run_command("show version")
        
        assert success is True
        assert "Command output" in output
        mock_shell.send.assert_called_with("show version\n")
    
    def test_enter_config_mode_success(self, sample_switch_config, mock_ssh_client):
        """Test entering configuration mode successfully."""
        mock_client, mock_shell = mock_ssh_client
        mock_shell.recv.return_value = b"Entering configuration mode\nICX7250-48P(config)>\n"
        
        conn = BaseConnection(**sample_switch_config)
        conn.ssh_client = mock_client
        conn.shell = mock_shell
        conn.connected = True
        
        result = conn.enter_config_mode()
        
        assert result is True
        mock_shell.send.assert_called_with("configure terminal\n")
    
    def test_exit_config_mode_with_save(self, sample_switch_config, mock_ssh_client):
        """Test exiting configuration mode with save."""
        mock_client, mock_shell = mock_ssh_client
        
        def mock_recv(size):
            # Simulate different responses for exit and write memory
            if mock_shell.send.call_count == 1:
                return b"Exiting configuration mode\nICX7250-48P>\n"
            else:
                return b"Configuration saved\nICX7250-48P>\n"
        
        mock_shell.recv.side_effect = mock_recv
        
        conn = BaseConnection(**sample_switch_config)
        conn.ssh_client = mock_client
        conn.shell = mock_shell
        conn.connected = True
        
        result = conn.exit_config_mode(save=True)
        
        assert result is True
        assert mock_shell.send.call_count == 2  # exit + write memory
    
    def test_context_manager(self, sample_switch_config, mock_ssh_client):
        """Test using BaseConnection as context manager."""
        mock_client, mock_shell = mock_ssh_client
        mock_shell.recv.return_value = b"ICX7250-48P>\n"
        
        with patch('ztp_agent.network.switch.base.connection.paramiko.SSHClient') as mock_ssh_class:
            mock_ssh_class.return_value = mock_client
            
            with BaseConnection(**sample_switch_config) as conn:
                assert conn.connected is True
            
            mock_shell.close.assert_called()
            mock_client.close.assert_called()
    
    def test_context_manager_connection_failure(self, sample_switch_config):
        """Test context manager when connection fails."""
        with patch('ztp_agent.network.switch.base.connection.paramiko.SSHClient') as mock_ssh_class:
            mock_client = Mock(spec=paramiko.SSHClient)
            mock_client.connect.side_effect = paramiko.AuthenticationException("Auth failed")
            mock_ssh_class.return_value = mock_client
            
            with pytest.raises(ConnectionError):
                with BaseConnection(**sample_switch_config):
                    pass