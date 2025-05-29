"""
Integration tests using real RUCKUS ICX switches.

These tests require actual hardware and should be run with pytest markers:
    pytest -m "integration" tests/integration/test_real_switch.py

Environment variables required:
    SWITCH_IP: IP address of test switch
    SWITCH_USER: Username (default: super)
    SWITCH_PASS: Password (default: sp-admin)
    SWITCH_NEW_PASS: Preferred password for testing password changes
"""
import os
import pytest
from ztp_agent.network.switch import SwitchOperation

# Skip all tests if no switch IP provided
pytestmark = pytest.mark.skipif(
    not os.getenv('SWITCH_IP'),
    reason="SWITCH_IP environment variable not set. Set it to run integration tests."
)

@pytest.fixture(scope="module")
def switch_config():
    """Get switch configuration from environment variables."""
    return {
        'ip': os.getenv('SWITCH_IP'),
        'username': os.getenv('SWITCH_USER', 'super'),
        'password': os.getenv('SWITCH_PASS', 'sp-admin'),
        'preferred_password': os.getenv('SWITCH_NEW_PASS', 'sp-admin'),
        'timeout': 30,
        'debug': True
    }

@pytest.fixture(scope="module")
def switch_connection(switch_config):
    """Create a connection to the real switch."""
    switch = SwitchOperation(**switch_config)
    if switch.connect():
        yield switch
        switch.disconnect()
    else:
        pytest.fail(f"Could not connect to switch {switch_config['ip']}")

class TestRealSwitchConnection:
    """Test actual switch connectivity and basic operations."""
    
    @pytest.mark.integration
    def test_connection_establishment(self, switch_connection):
        """Test that we can establish a connection to the switch."""
        assert switch_connection.connected is True
        assert switch_connection.ssh_client is not None
        assert switch_connection.shell is not None
    
    @pytest.mark.integration
    def test_basic_command_execution(self, switch_connection):
        """Test basic command execution."""
        success, output = switch_connection.run_command("show version")
        
        assert success is True
        assert len(output) > 0
        assert "ICX" in output  # Should contain RUCKUS ICX model info
    
    @pytest.mark.integration
    def test_device_info_retrieval(self, switch_connection):
        """Test device information retrieval."""
        model = switch_connection.get_model()
        serial = switch_connection.get_serial()
        firmware = switch_connection.get_firmware_version()
        uptime = switch_connection.get_uptime()
        
        assert model is not None
        assert "ICX" in model
        assert serial is not None
        assert len(serial) > 0
        assert firmware is not None
        assert uptime is not None
    
    @pytest.mark.integration
    def test_config_mode_operations(self, switch_connection):
        """Test entering and exiting configuration mode."""
        # Enter config mode
        assert switch_connection.enter_config_mode() is True
        
        # Test a harmless config command (description on a test interface)
        success, output = switch_connection.run_command("interface loopback 99")
        assert success is True
        
        success, output = switch_connection.run_command("description Testing ZTP Agent")
        assert success is True
        
        success, output = switch_connection.run_command("exit")
        assert success is True
        
        # Exit config mode without saving (to avoid changing switch config)
        assert switch_connection.exit_config_mode(save=False) is True
    
    @pytest.mark.integration
    def test_lldp_neighbors_discovery(self, switch_connection):
        """Test LLDP neighbor discovery."""
        success, neighbors = switch_connection.get_lldp_neighbors()
        
        assert success is True
        assert isinstance(neighbors, dict)
        # neighbors might be empty if no LLDP neighbors are connected
        print(f"Found {len(neighbors)} LLDP neighbors")
    
    @pytest.mark.integration
    def test_l2_trace_discovery(self, switch_connection):
        """Test L2 trace discovery."""
        success, trace_data = switch_connection.get_l2_trace_data()
        
        assert success is True
        assert isinstance(trace_data, dict)
        print(f"L2 trace found {len(trace_data)} MAC-to-IP mappings")

class TestRealSwitchConfiguration:
    """Test configuration operations on real switch."""
    
    @pytest.mark.integration
    def test_port_status_operations(self, switch_connection):
        """Test port status get/set operations."""
        from ztp_agent.network.switch.enums import PortStatus
        
        # Test with a port that typically exists (1/1/1)
        test_port = "1/1/1"
        
        # Get current status
        current_status = switch_connection.get_port_status(test_port)
        if current_status is not None:
            print(f"Port {test_port} current status: {current_status}")
            
            # Test setting status (but restore it afterward)
            if current_status == PortStatus.ENABLE:
                # Temporarily disable then re-enable
                success = switch_connection.set_port_status(test_port, PortStatus.DISABLE)
                assert success is True
                
                # Verify change
                new_status = switch_connection.get_port_status(test_port)
                assert new_status == PortStatus.DISABLE
                
                # Restore original status
                success = switch_connection.set_port_status(test_port, PortStatus.ENABLE)
                assert success is True
            else:
                print(f"Port {test_port} is disabled, skipping status change test")
        else:
            print(f"Could not get status for port {test_port}")
    
    @pytest.mark.integration
    def test_poe_status_operations(self, switch_connection):
        """Test PoE status operations if switch supports PoE."""
        from ztp_agent.network.switch.enums import PoEStatus
        
        test_port = "1/1/1"
        
        # Get current PoE status
        current_poe = switch_connection.get_poe_status(test_port)
        if current_poe is not None:
            print(f"Port {test_port} PoE status: {current_poe}")
            
            # Test PoE toggle (if safe to do so)
            if current_poe == PoEStatus.ENABLED:
                # Temporarily disable then re-enable
                success = switch_connection.set_poe_status(test_port, PoEStatus.DISABLED)
                assert success is True
                
                # Restore original status
                success = switch_connection.set_poe_status(test_port, PoEStatus.ENABLED)
                assert success is True
        else:
            print(f"Port {test_port} does not support PoE or PoE is not available")

class TestRealSwitchContextManager:
    """Test context manager functionality with real switch."""
    
    @pytest.mark.integration
    def test_context_manager_success(self, switch_config):
        """Test using switch connection as context manager."""
        with SwitchOperation(**switch_config) as switch:
            assert switch.connected is True
            
            success, output = switch.run_command("show version")
            assert success is True
            assert len(output) > 0
        
        # Connection should be closed after context exit
        assert switch.connected is False
    
    @pytest.mark.integration
    def test_context_manager_with_exception(self, switch_config):
        """Test context manager cleanup when exception occurs."""
        try:
            with SwitchOperation(**switch_config) as switch:
                assert switch.connected is True
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # Connection should still be closed after exception
        assert switch.connected is False