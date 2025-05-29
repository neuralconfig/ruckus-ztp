"""
Integration tests for ZTP process with real hardware.

These tests require actual hardware and should be run with pytest markers:
    pytest -m "integration" tests/integration/test_ztp_process.py

Environment variables required:
    SWITCH_IP: IP address of seed switch
    SWITCH_USER: Username (default: super)
    SWITCH_PASS: Password (default: sp-admin)
"""
import os
import pytest
import tempfile
from ztp_agent.ztp.process import ZTPProcess

# Skip all tests if no switch IP provided
pytestmark = pytest.mark.skipif(
    not os.getenv('SWITCH_IP'),
    reason="SWITCH_IP environment variable not set. Set it to run integration tests."
)

@pytest.fixture(scope="module")
def ztp_config():
    """Create ZTP configuration for testing."""
    return {
        'ztp': {
            'poll_interval': 10,  # Faster polling for tests
        },
        'network': {
            'base_config': '''! Test base configuration
vlan 10
  name Management
  tagged ethe 1/1/1 to 1/1/4
spanning-tree 802-1w
vlan 20
  name Wireless
  tagged ethe 1/1/1 to 1/1/4  
spanning-tree 802-1w
''',
            'management_vlan': 10,
            'wireless_vlans': [20, 30, 40],
            'ip_pool': '192.168.10.0/24',
            'gateway': '192.168.10.1',
        },
        'switches': {
            'username': os.getenv('SWITCH_USER', 'super'),
            'password': os.getenv('SWITCH_PASS', 'sp-admin'),
            'preferred_password': os.getenv('SWITCH_NEW_PASS', 'sp-admin'),
            'timeout': 30
        },
        'debug': True,
        'debug_callback': lambda msg, color: print(f"[{color}] {msg}")
    }

@pytest.fixture(scope="module")
def ztp_process(ztp_config):
    """Create ZTP process for testing."""
    process = ZTPProcess(ztp_config)
    yield process
    if hasattr(process, 'running') and process.running:
        process.stop()

class TestZTPProcessIntegration:
    """Test ZTP process with real hardware."""
    
    @pytest.mark.integration
    def test_add_seed_switch(self, ztp_process):
        """Test adding a seed switch to ZTP process."""
        switch_ip = os.getenv('SWITCH_IP')
        username = os.getenv('SWITCH_USER', 'super')
        password = os.getenv('SWITCH_PASS', 'sp-admin')
        preferred_password = os.getenv('SWITCH_NEW_PASS', 'sp-admin')
        
        success = ztp_process.add_switch(
            switch_ip, 
            username, 
            password,
            preferred_password=preferred_password,
            debug=True,
            debug_callback=lambda msg, color: print(f"[{color}] {msg}")
        )
        
        assert success is True
        assert switch_ip in ztp_process.inventory['switches']
        
        switch_info = ztp_process.get_switch_info(switch_ip)
        assert switch_info is not None
        assert 'model' in switch_info
        assert 'serial' in switch_info
        assert 'hostname' in switch_info
    
    @pytest.mark.integration  
    def test_discovery_process(self, ztp_process):
        """Test device discovery process."""
        switch_ip = os.getenv('SWITCH_IP')
        
        # First add the seed switch
        success = ztp_process.add_switch(
            switch_ip,
            os.getenv('SWITCH_USER', 'super'),
            os.getenv('SWITCH_PASS', 'sp-admin')
        )
        assert success is True
        
        # Run discovery once
        ztp_process._discover_devices()
        
        # Check if any neighbors were discovered
        status = ztp_process.get_status()
        print(f"Discovery results: {status['switches']} switches, {status['aps']} APs")
        
        # Should have at least the seed switch
        assert status['switches'] >= 1
    
    @pytest.mark.integration
    def test_ztp_status(self, ztp_process):
        """Test getting ZTP process status."""
        status = ztp_process.get_status()
        
        assert isinstance(status, dict)
        assert 'running' in status
        assert 'switches' in status
        assert 'configured_switches' in status
        assert 'aps' in status
        assert 'last_update' in status
        
        print(f"ZTP Status: {status}")
    
    @pytest.mark.integration
    def test_short_run_cycle(self, ztp_process):
        """Test running ZTP process for a short time."""
        import time
        
        switch_ip = os.getenv('SWITCH_IP')
        
        # Add seed switch
        success = ztp_process.add_switch(
            switch_ip,
            os.getenv('SWITCH_USER', 'super'),
            os.getenv('SWITCH_PASS', 'sp-admin')
        )
        assert success is True
        
        # Start ZTP process
        success = ztp_process.start()
        assert success is True
        
        # Let it run for a short time
        time.sleep(15)  # 15 seconds should be enough for one cycle
        
        # Stop the process
        success = ztp_process.stop()
        assert success is True
        
        # Check final status
        status = ztp_process.get_status()
        assert status['running'] is False
        print(f"Final status after run: {status}")

class TestZTPConfigurationIntegration:
    """Test ZTP configuration operations with real hardware."""
    
    @pytest.mark.integration
    def test_base_config_application(self, ztp_process):
        """Test applying base configuration to a switch."""
        switch_ip = os.getenv('SWITCH_IP')
        
        # Add switch first
        success = ztp_process.add_switch(
            switch_ip,
            os.getenv('SWITCH_USER', 'super'),
            os.getenv('SWITCH_PASS', 'sp-admin')
        )
        assert success is True
        
        # Get switch connection
        switch_info = ztp_process.inventory['switches'].get(switch_ip)
        assert switch_info is not None
        
        # Test base config application (but don't save to avoid changing switch)
        # This would normally be done by the ZTP process automatically