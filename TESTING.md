# Testing the RUCKUS ZTP Agent

This document provides comprehensive guidance on testing the RUCKUS ZTP Agent, including both automated tests and manual testing with real hardware.

## Test Structure

The test suite is organized into several categories:

- **Unit Tests** (`tests/unit/`): Fast tests that don't require hardware
- **Integration Tests** (`tests/integration/`): Tests that require real RUCKUS switches
- **Installation Test**: Verifies the package is installed correctly

## Prerequisites

### For All Tests
- Python 3.8+ with virtual environment activated
- All dependencies installed (`pip install -r requirements.txt`)
- ZTP Agent package installed (`pip install -e .`)

### For Integration Tests
- RUCKUS ICX switch(es) with SSH access
- Network connectivity between your computer and the switch(es)
- Switch credentials (username/password)

## Quick Start

### 1. Installation Test
First, verify the package is installed correctly:
```bash
python test_installation.py
```

### 2. Unit Tests (No Hardware Required)
Run fast unit tests that use mocks:
```bash
python test_runner.py unit
```

### 3. Integration Tests (Real Hardware)
Test with your actual switch:
```bash
export SWITCH_IP=192.168.1.100
export SWITCH_USER=super  
export SWITCH_PASS=sp-admin
python test_runner.py integration
```

### 4. All Tests
Run everything (installation + unit + integration if switch available):
```bash
export SWITCH_IP=192.168.1.100
python test_runner.py all
```

## Detailed Testing Options

### Using pytest Directly

If you prefer using pytest directly:

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only (requires SWITCH_IP)
export SWITCH_IP=192.168.1.100
pytest tests/integration/ -v -m integration

# All tests
pytest tests/ -v

# Specific test file
pytest tests/unit/test_base_connection.py -v

# Specific test method
pytest tests/unit/test_base_connection.py::TestBaseConnection::test_connect_success -v
```

### Test Markers

Tests are marked with pytest markers:

- `@pytest.mark.integration`: Requires real hardware
- `@pytest.mark.slow`: Takes longer to run

Filter tests by marker:
```bash
# Run only integration tests
pytest -m integration

# Skip integration tests
pytest -m "not integration"

# Run only slow tests
pytest -m slow
```

## Environment Variables for Integration Tests

Set these environment variables when running integration tests:

| Variable | Description | Default |
|----------|-------------|---------|
| `SWITCH_IP` | IP address of test switch | Required |
| `SWITCH_USER` | SSH username | `super` |
| `SWITCH_PASS` | SSH password | `sp-admin` |
| `SWITCH_NEW_PASS` | Password to test changes | `sp-admin` |

Example:
```bash
export SWITCH_IP=192.168.1.100
export SWITCH_USER=super
export SWITCH_PASS=sp-admin
export SWITCH_NEW_PASS=myNewPassword123
```

## What Integration Tests Cover

### Connection Tests
- SSH connection establishment
- Authentication (including first-time password changes)
- Command execution
- Configuration mode entry/exit
- Context manager functionality

### Device Information Tests
- Model detection
- Serial number retrieval
- Firmware version detection
- System uptime

### Discovery Tests
- LLDP neighbor discovery
- L2 trace for switch discovery
- Device type identification (switches vs APs)

### Configuration Tests
- Port status get/set operations
- PoE control (if supported)
- VLAN configuration
- Base configuration application

### ZTP Process Tests
- Adding seed switches
- Discovery process execution
- Status reporting
- Short-duration ZTP runs

## Safety Considerations

Integration tests are designed to be **safe** and **non-destructive**:

1. **Read-only operations** when possible
2. **Temporary changes** that are immediately reverted
3. **Test interfaces** (like loopback 99) for configuration tests
4. **No permanent configuration** saved to the switch
5. **Graceful cleanup** even if tests fail

### What Tests DON'T Do
- ❌ Save permanent configuration changes
- ❌ Modify production VLANs or ports
- ❌ Change switch passwords permanently
- ❌ Disrupt network connectivity
- ❌ Modify spanning tree or critical settings

## Manual Testing Workflow

For comprehensive manual testing with real hardware:

### 1. Basic CLI Testing
```bash
# Start the agent
ztp-agent

# Add your switch
config switch 192.168.1.100 super sp-admin

# Test basic commands
show switches
show version
```

### 2. Discovery Testing
```bash
# Enable ZTP to test discovery
ztp enable

# Monitor the process
show ztp
show switches
show aps

# Check individual switch discovery
ztp discover 192.168.1.100
```

### 3. AI Chat Interface Testing
```bash
# Configure API key first
config agent openrouter_key YOUR_API_KEY

# Enter chat mode
chat

# Test natural language commands
You: What switches are available?
You: Check the status of port 1/1/1
You: Show me the LLDP neighbors
```

### 4. Configuration Testing
```bash
# Load VLANs from CSV
vlan load example_vlans.csv

# Show VLAN configuration
show vlans

# Test port operations (be careful!)
show port 1/1/1
```

## Troubleshooting Tests

### Common Issues

1. **Import Errors**
   ```bash
   # Reinstall the package
   pip install -e .
   ```

2. **Connection Timeouts**
   ```bash
   # Check network connectivity
   ping 192.168.1.100
   
   # Test SSH manually
   ssh super@192.168.1.100
   ```

3. **Authentication Failures**
   ```bash
   # Verify credentials
   export SWITCH_PASS=correct-password
   ```

4. **Permission Errors**
   ```bash
   # Check switch user privileges
   # 'super' user should have full access
   ```

### Debug Mode

Enable debug output for more verbose logging:

```bash
# For integration tests
pytest tests/integration/ -v -s

# For manual testing
ztp-agent --debug
```

## Continuous Integration

For automated testing in CI/CD:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest

# Install package
pip install -e .

# Run unit tests only (no hardware in CI)
pytest tests/unit/ -v

# Run installation test
python test_installation.py
```

## Performance Testing

For performance testing with multiple switches:

```bash
# Set longer timeouts for slow networks
export SWITCH_TIMEOUT=60

# Test with multiple switches
export SWITCH_IP1=192.168.1.100
export SWITCH_IP2=192.168.1.101
# ... run custom test scripts
```

## Writing New Tests

### Unit Test Template
```python
import pytest
from unittest.mock import Mock
from ztp_agent.network.switch.base.connection import BaseConnection

class TestMyNewFeature:
    def test_my_feature(self):
        # Arrange
        conn = BaseConnection("192.168.1.1", "user", "pass")
        
        # Act
        result = conn.my_new_method()
        
        # Assert
        assert result is True
```

### Integration Test Template
```python
import pytest
import os

@pytest.mark.skipif(not os.getenv('SWITCH_IP'), reason="No switch available")
class TestMyIntegration:
    @pytest.mark.integration
    def test_with_real_switch(self, switch_connection):
        # Test with real hardware
        success, output = switch_connection.run_command("show version")
        assert success is True
```

## Best Practices

1. **Run unit tests frequently** during development
2. **Run integration tests** before major releases
3. **Use descriptive test names** that explain what's being tested
4. **Mock external dependencies** in unit tests
5. **Clean up after integration tests** (disconnect, restore state)
6. **Test both success and failure scenarios**
7. **Use fixtures** for common setup/teardown
8. **Document any special test requirements**

## Test Coverage

Generate test coverage reports:

```bash
pip install pytest-cov
pytest tests/ --cov=ztp_agent --cov-report=html
open htmlcov/index.html
```

This will show which parts of the code are covered by tests and which need more testing.