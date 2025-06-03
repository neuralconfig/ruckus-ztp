# SSH Proxy Design for Raspberry Pi

## Overview

This document outlines the design for an SSH proxy application that runs on a Raspberry Pi (aarch64) to enable remote SSH access to network devices through the RUCKUS ZTP backend server. The proxy allows the web UI and iOS app to perform SSH operations on devices located on the Pi's local network without requiring inbound firewall rules.

## Problem Statement

- SSH communication through web browsers and mobile apps is challenging
- Network devices (RUCKUS switches) are often on isolated networks
- Firewall rules should not be required for inbound connections to the Pi
- Need simple installation and operation on Raspberry Pi

## Architecture

### Core Design Principles

1. **Outbound-only connections**: Pi initiates all connections to backend
2. **Sequential operations**: One SSH session at a time (matching current ZTP pattern)
3. **Stateless proxy**: No persistent SSH sessions on Pi (initially)
4. **Simple deployment**: Single Python application with minimal dependencies

### Components

```
[Web UI/iOS App] → [Backend Server] → [WebSocket] → [Pi SSH Proxy] → [Network Devices]
```

1. **Pi SSH Proxy**: Python application running on Raspberry Pi
2. **Backend Integration**: WebSocket endpoint in existing FastAPI server
3. **Frontend Integration**: Pi selection in web UI and iOS app

## Implementation Approach

### Option A: Stateless Command Proxy (Recommended)

**How it works:**
- Pi maintains persistent WebSocket connection to backend
- Backend sends SSH commands as JSON messages
- Pi creates temporary SSH connection per command
- Pi returns command output via WebSocket
- No persistent SSH sessions maintained on Pi

**Benefits:**
- Simple state management
- Matches current ZTP sequential pattern
- Easy error handling and recovery
- Minimal memory footprint
- Natural cleanup on connection failures

### Current ZTP SSH Analysis

Based on codebase analysis, the existing ZTP agent:
- Uses **sequential, one-at-a-time** SSH connections
- Each `SwitchOperation` creates dedicated SSH connection
- No connection pooling or concurrent sessions
- Uses paramiko with interactive shell channels
- Proper cleanup and state tracking via inventory callbacks

This simplifies proxy design since we only need to handle one SSH session at a time.

## Protocol Design

### WebSocket Message Format

#### Pi → Backend Messages

**Registration:**
```json
{
    "type": "register",
    "pi_id": "uuid-generated-on-startup",
    "capabilities": ["ssh_proxy"],
    "network_info": {
        "subnet": "192.168.1.0/24",
        "hostname": "raspberrypi-001"
    },
    "version": "1.0.0"
}
```

**Command Response:**
```json
{
    "type": "command_result",
    "request_id": "req-uuid",
    "success": true,
    "output": "ICX7150-24P Switch\nSoftware Version: 08.0.95...",
    "error": null,
    "execution_time_ms": 1250
}
```

**Status Updates:**
```json
{
    "type": "status",
    "pi_id": "uuid",
    "status": "online|busy|error",
    "last_seen": "2024-01-01T12:00:00Z"
}
```

#### Backend → Pi Messages

**SSH Command:**
```json
{
    "type": "ssh_command",
    "request_id": "req-uuid",
    "target_ip": "192.168.1.100",
    "username": "super",
    "password": "sp-admin",
    "command": "show version",
    "timeout": 30
}
```

**Health Check:**
```json
{
    "type": "ping",
    "timestamp": "2024-01-01T12:00:00Z"
}
```

### Authentication

**Recommended: Pre-shared Token**
- Pi starts with: `ssh-proxy --server wss://backend.com --token abc123`
- Backend validates token in WebSocket handshake header
- Simple, secure enough for private networks
- Token provided during Pi setup process

**Alternative Options:**
- Certificate-based authentication
- Dynamic registration with manual approval

## Implementation Details

### Pi SSH Proxy Application

**Technology Stack:**
- Python 3.8+ (matches existing codebase)
- `websockets` library for WebSocket client
- `paramiko` for SSH connections (reuse existing patterns)
- `asyncio` for event loop management

**Core Components:**
1. **WebSocket Client**: Maintains connection to backend
2. **SSH Handler**: Executes commands using existing `SwitchOperation` patterns
3. **Registration Manager**: Handles Pi identification and capabilities
4. **Error Handler**: Manages reconnection and error recovery

**CLI Interface:**
```bash
# Basic usage
ssh-proxy --server wss://backend.example.com --token abc123

# With custom settings
ssh-proxy --server wss://backend.example.com --token abc123 --reconnect-interval 30 --debug
```

### Backend Integration

**New Components:**
1. **WebSocket Endpoint**: `/ws/ssh-proxy/{pi_id}`
2. **Pi Registry**: Track active proxy instances
3. **Request Router**: Route SSH commands to appropriate Pi
4. **API Endpoints**: Manage Pi registration and status

**Database Schema:**
```sql
-- Pi proxy registration table
CREATE TABLE ssh_proxies (
    id UUID PRIMARY KEY,
    hostname VARCHAR(255),
    ip_address INET,
    network_subnet CIDR,
    status VARCHAR(50),
    last_seen TIMESTAMP,
    capabilities JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Frontend Integration

**Web UI Changes:**
- Add Pi proxy selection dropdown
- Display Pi status and network information
- Show active proxy connections
- Pi management interface (enable/disable, view logs)

**iOS App Changes:**
- Pi proxy picker in connection settings
- Real-time status indicators
- Proxy health monitoring

## Deployment Strategy

### Installation Package
```bash
# Simple installation script
curl -sSL https://get.ruckus-ztp.com/pi-proxy | bash

# Or pip package
pip install ruckus-ztp-proxy
```

**Package Contents:**
- Python application with dependencies
- Systemd service file
- Configuration template
- Setup script for token generation

### Configuration
```ini
# /etc/ruckus-ztp-proxy/config.ini
[server]
url = wss://backend.example.com
token = abc123-def456-ghi789

[proxy]
reconnect_interval = 30
command_timeout = 60
max_concurrent_commands = 1

[logging]
level = INFO
file = /var/log/ruckus-ztp-proxy.log
```

### Service Management
```bash
# Install and start service
sudo systemctl enable ruckus-ztp-proxy
sudo systemctl start ruckus-ztp-proxy

# Check status
sudo systemctl status ruckus-ztp-proxy

# View logs
sudo journalctl -u ruckus-ztp-proxy -f
```

## Security Considerations

1. **Authentication**: Pre-shared tokens with secure generation
2. **Transport**: WSS (WebSocket Secure) for all communications
3. **Network**: Pi only makes outbound connections
4. **Isolation**: Pi processes one command at a time
5. **Logging**: Audit trail of all SSH commands executed
6. **Credentials**: SSH credentials transmitted over encrypted WebSocket

## Future Enhancements

### Phase 2: Session-Aware Proxy
- Persistent SSH sessions for configuration workflows
- Session state management
- Support for interactive configuration modes

### Phase 3: Advanced Features
- Multiple concurrent SSH sessions
- Device discovery integration
- Local caching of device information
- Automated Pi deployment and management

## Integration Points with Existing Codebase

1. **Reuse SSH Logic**: Extend existing `SwitchOperation` class
2. **WebSocket Integration**: Add to existing FastAPI backend
3. **UI Components**: Extend current device management interfaces
4. **Configuration**: Leverage existing configuration patterns
5. **Logging**: Use existing logger infrastructure

## Timeline and Milestones

1. **Phase 1**: Basic proxy implementation and backend integration
2. **Phase 2**: Frontend integration and testing
3. **Phase 3**: Deployment tooling and documentation
4. **Phase 4**: Production deployment and monitoring

## Testing Strategy

1. **Unit Tests**: Mock WebSocket and SSH connections
2. **Integration Tests**: Test with real Raspberry Pi and switches
3. **Load Testing**: Multiple Pi proxies with concurrent operations
4. **Security Testing**: Verify secure communication and authentication