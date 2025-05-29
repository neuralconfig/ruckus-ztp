"""
Unit tests for the DeviceInfo mixin class.
"""
import pytest
from unittest.mock import Mock

from ztp_agent.network.switch.base.device_info import DeviceInfo


class MockConnection(DeviceInfo):
    """Mock connection class that includes DeviceInfo mixin."""
    
    def __init__(self):
        self.ip = "192.168.1.1"
        self.model = None
        self.serial = None
    
    def run_command(self, command):
        """Mock run_command method."""
        return True, self._mock_output


class TestDeviceInfo:
    """Test cases for DeviceInfo mixin."""
    
    def test_get_model_success(self, sample_version_output):
        """Test successful model detection."""
        conn = MockConnection()
        conn._mock_output = sample_version_output
        
        model = conn.get_model()
        
        assert model == "ICX7250-48P"
        assert conn.model == "ICX7250-48P"
    
    def test_get_model_cached(self, sample_version_output):
        """Test that model is cached after first call."""
        conn = MockConnection()
        conn.model = "ICX7250-48P"  # Pre-set model
        
        model = conn.get_model()
        
        assert model == "ICX7250-48P"
        # run_command should not be called if model is cached
    
    def test_get_model_command_failure(self):
        """Test model detection when command fails."""
        conn = MockConnection()
        conn.run_command = Mock(return_value=(False, "Command failed"))
        
        model = conn.get_model()
        
        assert model is None
        assert conn.model is None
    
    def test_get_model_not_found(self):
        """Test model detection when pattern not found."""
        conn = MockConnection()
        conn._mock_output = "Some other output without model info"
        
        model = conn.get_model()
        
        assert model is None
    
    def test_get_model_alternative_pattern(self):
        """Test model detection with alternative pattern."""
        conn = MockConnection()
        conn._mock_output = "System Type: ICX8200-C08PF\nOther info"
        
        model = conn.get_model()
        
        assert model == "ICX8200-C08PF"
        assert conn.model == "ICX8200-C08PF"
    
    def test_get_serial_success(self, sample_version_output):
        """Test successful serial number detection."""
        conn = MockConnection()
        conn._mock_output = sample_version_output
        
        serial = conn.get_serial()
        
        assert serial == "ABC123456789"
        assert conn.serial == "ABC123456789"
    
    def test_get_serial_cached(self):
        """Test that serial is cached after first call."""
        conn = MockConnection()
        conn.serial = "ABC123456789"  # Pre-set serial
        
        serial = conn.get_serial()
        
        assert serial == "ABC123456789"
    
    def test_get_serial_command_failure(self):
        """Test serial detection when command fails."""
        conn = MockConnection()
        conn.run_command = Mock(return_value=(False, "Command failed"))
        
        serial = conn.get_serial()
        
        assert serial is None
        assert conn.serial is None
    
    def test_get_serial_not_found(self):
        """Test serial detection when pattern not found."""
        conn = MockConnection()
        conn._mock_output = "Some other output without serial info"
        
        serial = conn.get_serial()
        
        assert serial is None
    
    def test_get_serial_alternative_pattern(self):
        """Test serial detection with alternative pattern."""
        conn = MockConnection()
        conn._mock_output = "Serial #: XYZ987654321\nOther info"
        
        serial = conn.get_serial()
        
        assert serial == "XYZ987654321"
        assert conn.serial == "XYZ987654321"
    
    def test_get_firmware_version_success(self, sample_version_output):
        """Test successful firmware version detection."""
        conn = MockConnection()
        conn._mock_output = sample_version_output
        
        version = conn.get_firmware_version()
        
        assert version == "08.0.95hT213"
    
    def test_get_firmware_version_alternative_pattern(self):
        """Test firmware version with alternative pattern."""
        conn = MockConnection()
        conn._mock_output = "Software Version: 09.0.10cT211\nOther info"
        
        version = conn.get_firmware_version()
        
        assert version == "09.0.10cT211"
    
    def test_get_uptime_success(self, sample_version_output):
        """Test successful uptime detection."""
        conn = MockConnection()
        conn._mock_output = sample_version_output
        
        uptime = conn.get_uptime()
        
        assert uptime == "2 days 3 hours 45 minutes"
    
    def test_get_uptime_not_found(self):
        """Test uptime detection when pattern not found."""
        conn = MockConnection()
        conn._mock_output = "Some other output without uptime info"
        
        uptime = conn.get_uptime()
        
        assert uptime is None