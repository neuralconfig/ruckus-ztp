"""Unit tests for SSH handler."""

import unittest
from unittest.mock import Mock, patch, MagicMock
import asyncio
from ztp_edge_agent.handlers.ssh_handler import SSHHandler


class TestSSHHandler(unittest.TestCase):
    """Test SSH command handler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.handler = SSHHandler(command_timeout=30)
    
    def tearDown(self):
        """Clean up after tests."""
        if hasattr(self.handler, '_executor'):
            self.handler._executor.shutdown(wait=False)
    
    @patch('ztp_edge_agent.handlers.ssh_handler.paramiko.SSHClient')
    def test_execute_ssh_command_success(self, mock_ssh_class):
        """Test successful SSH command execution."""
        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_class.return_value = mock_ssh
        
        # Mock command execution
        mock_stdout = Mock()
        mock_stdout.read.return_value = b"Command output"
        mock_stderr = Mock()
        mock_stderr.read.return_value = b""
        
        mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        # Execute command
        result = self.handler._execute_ssh_command(
            host="192.168.1.100",
            username="admin",
            password="password",
            command="show version",
            timeout=30
        )
        
        # Verify
        self.assertEqual(result, "Command output")
        mock_ssh.connect.assert_called_once_with(
            hostname="192.168.1.100",
            username="admin",
            password="password",
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        mock_ssh.exec_command.assert_called_once_with("show version", timeout=30)
        mock_ssh.close.assert_called_once()
    
    @patch('ztp_edge_agent.handlers.ssh_handler.paramiko.SSHClient')
    def test_execute_ssh_command_with_stderr(self, mock_ssh_class):
        """Test SSH command with stderr output."""
        # Mock SSH client
        mock_ssh = Mock()
        mock_ssh_class.return_value = mock_ssh
        
        # Mock command execution with stderr
        mock_stdout = Mock()
        mock_stdout.read.return_value = b"Command output"
        mock_stderr = Mock()
        mock_stderr.read.return_value = b"Warning message"
        
        mock_ssh.exec_command.return_value = (None, mock_stdout, mock_stderr)
        
        # Execute command
        result = self.handler._execute_ssh_command(
            host="192.168.1.100",
            username="admin",
            password="password",
            command="show config",
            timeout=30
        )
        
        # Should still return stdout
        self.assertEqual(result, "Command output")
    
    @patch('ztp_edge_agent.handlers.ssh_handler.paramiko.SSHClient')
    def test_execute_ssh_command_connection_error(self, mock_ssh_class):
        """Test SSH connection error."""
        # Mock SSH client that fails to connect
        mock_ssh = Mock()
        mock_ssh_class.return_value = mock_ssh
        mock_ssh.connect.side_effect = Exception("Connection refused")
        
        # Execute command should raise exception
        with self.assertRaises(Exception) as context:
            self.handler._execute_ssh_command(
                host="192.168.1.100",
                username="admin",
                password="password",
                command="show version",
                timeout=30
            )
        
        self.assertIn("Connection refused", str(context.exception))
        mock_ssh.close.assert_called_once()
    
    def test_execute_command_async(self):
        """Test async command execution."""
        # Use asyncio to test async method
        async def run_test():
            with patch.object(self.handler, '_execute_ssh_command') as mock_execute:
                mock_execute.return_value = "Test output"
                
                result = await self.handler.execute_command(
                    host="192.168.1.100",
                    username="admin",
                    password="password",
                    command="show version",
                    timeout=30
                )
                
                self.assertEqual(result["output"], "Test output")
                self.assertIn("execution_time_ms", result)
                self.assertIsInstance(result["execution_time_ms"], int)
                
                mock_execute.assert_called_once_with(
                    "192.168.1.100", "admin", "password", "show version", 30
                )
        
        # Run async test
        asyncio.run(run_test())
    
    def test_execute_command_async_error(self):
        """Test async command execution with error."""
        async def run_test():
            with patch.object(self.handler, '_execute_ssh_command') as mock_execute:
                mock_execute.side_effect = Exception("SSH error")
                
                with self.assertRaises(Exception) as context:
                    await self.handler.execute_command(
                        host="192.168.1.100",
                        username="admin",
                        password="password",
                        command="show version"
                    )
                
                self.assertIn("SSH error", str(context.exception))
        
        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()